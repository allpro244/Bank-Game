"""The turn engine: one turn = one business day.

Sequencing:
  * Daily: curve wiggle, interest accruals (loans, securities, deposits,
    borrowings), AFS marks, the bank-run model, overnight cash management,
    and the ledger audit (debits==credits or the game screams).
  * On the first business day of each month: the previous month is
    processed (macro step, regional economies, competitors, deposit flows,
    originations, credit rolls, opex, fraud, exams) and the books close.
  * Quarter ends add CECL, taxes, FDIC assessment, capital/PCA checks,
    dividends and a call report.

Blocking events stop multi-day advances so the clock never runs past
something that needs your decision.
"""

import datetime

from . import ledger as L
from . import rng as R
from . import economy, regions, competitors, deposits, loans, securities
from . import funding, operations, regulation, fraud, crises, statements

MAX_EVENT_LOG = 400

UNLOCKS = {
    "heloc":          (40_000_000_00, 150_000_00, "Home equity lines of credit"),
    "construction":   (30_000_000_00, 100_000_00, "Construction & development lending"),
    "sba":            (60_000_000_00, 250_000_00, "SBA lending desk"),
    "credit_card":    (100_000_000_00, 2_500_000_00, "Credit card issuing"),
    "treasury_mgmt":  (50_000_000_00, 250_000_00, "Treasury management services"),
    "trust_wealth":   (150_000_000_00, 1_200_000_00, "Trust & wealth management"),
    "insurance":      (75_000_000_00, 400_000_00, "Insurance agency"),
    "merchant":       (250_000_000_00, 800_000_00, "Merchant acquiring"),
    "correspondent":  (1_000_000_000_00, 2_000_000_00, "Correspondent banking"),
    "capital_markets": (10_000_000_000_00, 50_000_000_00, "Capital markets & investment banking"),
}


def _rng(state, stream):
    return R.Rng(state["rng"][stream])


def _date(state):
    return datetime.date.fromisoformat(state["time"]["date"])


def _next_business_day(d):
    nxt = d + datetime.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += datetime.timedelta(days=1)
    return nxt


def push_event(state, ev):
    ev = dict(ev)
    ev["id"] = state["events"]["next_id"]
    state["events"]["next_id"] += 1
    ev["date"] = state["time"]["date"]
    state["events"]["log"].append(ev)
    if len(state["events"]["log"]) > MAX_EVENT_LOG:
        del state["events"]["log"][:len(state["events"]["log"]) - MAX_EVENT_LOG]
    if ev.get("blocking") or ev.get("choices"):
        state["events"]["pending"].append(ev)
    return ev


def step_day(state):
    """Advance one business day. Returns list of newly pushed events."""
    if state["game_over"]:
        return []
    prev = _date(state)
    nxt = _next_business_day(prev)
    days_elapsed = (nxt - prev).days
    state["time"]["date"] = nxt.isoformat()
    state["time"]["day_index"] += 1
    raised = []

    if nxt.month != prev.month:
        raised += _process_month_boundary(state, prev)
        if state["game_over"]:
            return raised

    bank = state["bank"]
    economy.step_day(state["economy"], _rng(state, "econ"))
    deposits.step_day(state, days_elapsed)
    loans.step_day(state, days_elapsed)
    securities.accrue_day(state, days_elapsed)
    securities.revalue(state)
    funding.accrue_day(state, days_elapsed)

    for ev in crises.step_day(state, _rng(state, "crisis")):
        raised.append(push_event(state, ev))
    if state["regulation"]["seized"]:
        _game_over(state, "seized")
        return raised

    for ev in funding.manage_overnight(state):
        raised.append(push_event(state, ev))

    bank["cached_assets"] = L.total_assets(bank["ledger"])

    problems = L.audit(bank["ledger"])
    if problems:
        state["audit_alarm"] = {"date": state["time"]["date"], "problems": problems}
        raised.append(push_event(state, {
            "type": "audit_alarm", "blocking": True,
            "title": "INTERNAL AUDIT ALARM — BOOKS DO NOT BALANCE",
            "text": "The end-of-day audit found:\n" + "\n".join(problems) +
                    "\nThis is a simulation bug. Please report it (state is preserved)."}))
    return raised


def _process_month_boundary(state, prev_date):
    raised = []
    bank = state["bank"]
    month_label = prev_date.isoformat()[:7]
    quarter_end = prev_date.month in (3, 6, 9, 12)

    economy.step_month(state["economy"], _rng(state, "econ"))
    for ev in regions.step_month(state["regions"], state["economy"], _rng(state, "region")):
        raised.append(push_event(state, ev))
    for ev in competitors.step_month(state, _rng(state, "comp")):
        raised.append(push_event(state, ev))

    for ev in deposits.step_month(state, _rng(state, "deposit")):
        raised.append(push_event(state, ev))
    loans.collect_monthly_interest(state)
    for ev in loans.step_month_credit(state, _rng(state, "credit")):
        raised.append(push_event(state, ev))
    for ev in loans.originate_month(state, _rng(state, "credit")):
        raised.append(push_event(state, ev))
    securities.step_month(state, _rng(state, "misc"))
    for ev in funding.step_month(state, _rng(state, "misc")):
        raised.append(push_event(state, ev))
    funding.pay_accrued_monthly(state)
    for ev in operations.monthly_opex(state, _rng(state, "ops")):
        raised.append(push_event(state, ev))
    for ev in fraud.step_month(state, _rng(state, "fraud")):
        raised.append(push_event(state, ev))
    for ev in crises.step_month(state, _rng(state, "crisis")):
        raised.append(push_event(state, ev))
    _business_lines_month(state, _rng(state, "misc"))
    for ev in regulation.monthly_update(state, _rng(state, "misc")):
        raised.append(push_event(state, ev))
    _integration_month(state, _rng(state, "misc"))

    if quarter_end:
        loans.quarterly_cecl(state)
        _quarterly_taxes(state)
        for ev in regulation.quarterly_update(state, _rng(state, "misc")):
            raised.append(push_event(state, ev))
        if state["regulation"]["seized"]:
            _game_over(state, "seized")
            return raised

    # ---- close the books for the month ----
    L.close_month(bank["ledger"], month_label, state["time"]["date"])
    statements.record_metrics(state)
    bank["cached_assets"] = L.total_assets(bank["ledger"])
    from . import goals as GOALS
    GOALS.update_chronicle(state)
    digest = GOALS.compose_digest(state)
    state.setdefault("digests", []).append(digest)
    if len(state["digests"]) > 24:
        del state["digests"][:-24]
    win = GOALS.check_win(state)
    if win:
        raised.append(push_event(state, win))

    if quarter_end:
        last3 = bank["ledger"]["months"][-3:]
        bank["last_quarter_net_income"] = sum(m["net_income"] for m in last3)
        funding.pay_preferred_dividends(state)
        div = funding.pay_dividends(state)
        state["call_reports"].append(statements.call_report(state))
        if len(state["call_reports"]) > 120:
            del state["call_reports"][0]
        mt = state["metrics"][-1] if state["metrics"] else {}
        raised.append(push_event(state, {
            "type": "quarter_close", "blocking": True,
            "ni": bank["last_quarter_net_income"],
            "cet1": mt.get("cet1_ratio"),
            "ldr": mt.get("loan_to_deposit"),
            "title": "Quarter closed",
            "text": ("Net income $%s%s\nCore capital (CET1) %.1f%%\n"
                     "Loans vs deposits %.2f\n\nThe call report is on Reports."
                     % (f"{bank['last_quarter_net_income'] // 100:,}",
                        (", dividend $%s" % f"{div // 100:,}") if div else "",
                        (mt.get("cet1_ratio") or 0) * 100,
                        mt.get("loan_to_deposit") or 0))}))
        # solvency backstop between exams
        r = regulation.capital_ratios(state)
        if r["tang_equity_ratio"] <= 0.02:
            state["regulation"]["seized"] = True
            raised.append(push_event(state, {
                "type": "seizure", "blocking": True,
                "title": "SEIZED BY REGULATORS",
                "text": "Tangible equity fell to %.2f%% of assets. The FDIC has taken "
                        "receivership." % (r["tang_equity_ratio"] * 100)}))
            _game_over(state, "seized")
            return raised

    for ev in _ma_opportunities(state, _rng(state, "event")):
        raised.append(push_event(state, ev))
    return raised


def _game_over(state, kind):
    from . import goals as GOALS
    if kind == "seized" and state.get("meta", {}).get("goal") != "sell":
        state.setdefault("meta", {})["goal_failed"] = True
    state["game_over"] = GOALS.autopsy(state, kind)


def _quarterly_taxes(state):
    bank = state["bank"]
    months = bank["ledger"]["months"][-2:]   # two closed months of the quarter
    # plus the open month currently in the I/X accounts
    pretax_open = L.net_income_open(bank["ledger"]) + \
        L.display_balance(bank["ledger"], "5190")
    pretax = pretax_open
    for m in months:
        pretax += m["net_income"] + m["pl"].get("5190", 0)
    carry = bank["tax_loss_carry"]
    if pretax <= 0:
        bank["tax_loss_carry"] = carry + (-pretax)
        return
    usable = min(carry, pretax)
    bank["tax_loss_carry"] = carry - usable
    taxable = pretax - usable
    tax = int(taxable * 0.21)
    if tax > 0:
        L.post(bank["ledger"], state["time"]["date"], "Estimated income tax paid",
               [["5190", tax, 0], ["1000", 0, tax]], tag="tax")


def _business_lines_month(state, rng):
    bank = state["bank"]
    econ = state["economy"]
    date = state["time"]["date"]
    lines = bank["products_enabled"]
    assets = max(bank["cached_assets"], 20_000_000_00)

    if "trust_wealth" in lines:
        aum = bank.get("aum", 0)
        eq_ret = (econ["equity_index"] / econ.get("equity_peak", econ["equity_index"]) - 1) * 0.02
        brand_avg = (sum(bank["ops"]["brand"].values()) /
                     max(1, len(bank["ops"]["brand"])))
        flows = int(assets * 0.0008 * (0.5 + brand_avg / 100))
        aum = max(0, int(aum * (1 + 0.004 + eq_ret + rng.normal(0, 0.01))) + flows)
        bank["aum"] = aum
        rev = int(aum * 0.009 / 12)
        cost = int(rev * 0.62)
        if rev > 0:
            L.post(bank["ledger"], date, "Trust & wealth management",
                   [["1000", rev, 0], ["4130", 0, rev],
                    ["5170", cost, 0], ["1000", 0, cost]], tag="line")

    if "insurance" in lines:
        rev = int(assets * 0.00035 / 12)
        cost = int(rev * 0.55)
        L.post(bank["ledger"], date, "Insurance agency commissions",
               [["1000", rev, 0], ["4150", 0, rev],
                ["5170", cost, 0], ["1000", 0, cost]], tag="line")

    if "merchant" in lines:
        rev = int(L.total_deposits(bank["ledger"]) * 0.0005 / 12)
        cost = int(rev * 0.45)
        L.post(bank["ledger"], date, "Merchant acquiring",
               [["1000", rev, 0], ["4150", 0, rev],
                ["5170", cost, 0], ["1000", 0, cost]], tag="line")

    if "correspondent" in lines:
        rev = int(assets * 0.00012 / 12)
        cost = int(rev * 0.5)
        L.post(bank["ledger"], date, "Correspondent banking services",
               [["1000", rev, 0], ["4120", 0, rev],
                ["5170", cost, 0], ["1000", 0, cost]], tag="line")

    if "capital_markets" in lines:
        base = assets * 0.0006 / 12
        rev = int(base * rng.lognormal(0.0, 0.8))
        cost = int(base * 0.75)
        market_ok = econ["equity_drawdown"] < 0.15 and econ["credit_stress"] < 0.35
        if not market_ok:
            rev = int(rev * 0.25)
        L.post(bank["ledger"], date, "Capital markets & investment banking",
               [["1000", rev, 0], ["4170", 0, rev],
                ["5170", cost, 0], ["1000", 0, cost]], tag="line")


# ------------------------------------------------------------------- M&A

def _eligible_ma_markets(state):
    """Don't offer NYC to a $20M bank. Prefer markets you already serve."""
    rank = {"rural": 0, "small_metro": 1, "suburb": 2, "metro": 3, "money_center": 4}
    assets = state["bank"]["cached_assets"]
    if assets < 80_000_000_00:
        cap = 1
    elif assets < 400_000_000_00:
        cap = 2
    elif assets < 2_000_000_000_00:
        cap = 3
    else:
        cap = 4
    allowed = [mid for mid, r in state["regions"].items()
               if rank.get(r["kind"], 4) <= cap]
    served = [m for m in allowed if m in state["bank"]["deposits"]["pools"]]
    return served or allowed


def deal_proforma(state, deal):
    """Capital impact of buying `deal` without mutating state."""
    from .regulation import capital_ratios, pca_category
    bank = state["bank"]
    r = capital_ratios(state)
    t_assets = deal["assets"]
    t_deposits = int(t_assets * 0.82)
    t_loans = int(t_assets * 0.65 * (1 - deal.get("credit_mark", 0.05)))
    t_sec = int(t_assets * 0.18)
    t_cash = t_assets - int(t_assets * 0.65) - t_sec
    net_assets = t_loans + t_sec + t_cash - t_deposits
    goodwill = max(0, deal["price"] - net_assets)
    new_assets = r["assets"] + t_loans + t_sec + t_cash + goodwill
    # cash paid reduces assets; we already added t_cash
    new_assets -= deal["price"]
    te = r["cet1"] - deal["price"] + max(0, net_assets)
    # goodwill is not tangible
    te -= goodwill
    lev = te / max(1, new_assets)
    # RWA: acquired loans ~100% weight, secs ~0-20% — rough
    new_rwa = r["rwa"] + t_loans + int(t_sec * 0.2)
    cet1 = te / max(1, new_rwa)
    fake = dict(r)
    fake.update({"cet1_ratio": cet1, "leverage_ratio": lev,
                 "tang_equity_ratio": lev, "cet1": te,
                 "tier1_ratio": cet1, "total_ratio": cet1})
    pca = pca_category(fake)
    cash = (bank["ledger"]["balances"]["1000"]
            + bank["ledger"]["balances"]["1010"]
            + bank["ledger"]["balances"]["1100"])
    camels = state["regulation"]["camels"]["composite"]
    reasons = []
    if camels > 2:
        reasons.append("CAMELS above 2 — regulators will deny")
    if state["regulation"]["orders"]:
        reasons.append("enforcement actions block acquisitions")
    if state["regulation"]["cra"] == "Needs to Improve":
        reasons.append("CRA rating blocks approval")
    if cash < deal["price"]:
        reasons.append("not enough cash to close")
    if pca not in ("well", "adequate"):
        reasons.append("pro-forma capital would not be well-capitalized")
    return {
        "new_assets": new_assets, "new_te": te,
        "leverage": round(lev, 5), "cet1": round(cet1, 5),
        "pca": pca, "goodwill": goodwill,
        "can_buy": not reasons, "blockers": reasons,
    }


def _ma_opportunities(state, rng):
    """Occasionally: a bank comes up for sale, or someone wants to buy you."""
    events = []
    bank = state["bank"]
    econ = state["economy"]
    assets = bank["cached_assets"]

    already = any(e.get("type") == "bank_for_sale" for e in state["events"]["pending"])
    if (not already) and rng.chance(0.018):
        # a target for sale, sized relative to you — never a whale
        t_assets = int(assets * rng.uniform(0.10, 0.35))
        if t_assets > 8_000_000_00:
            mult = rng.uniform(1.25, 1.85)
            if econ["credit_stress"] > 0.35:
                mult = rng.uniform(0.6, 1.05)
            t_tbv = int(t_assets * rng.uniform(0.07, 0.10))
            price = int(t_tbv * mult)
            mkts = _eligible_ma_markets(state)
            if not mkts:
                mkts = ["caprock"]
            target_mkt = rng.choice(mkts)
            name = "%s %s" % (rng.choice(["Citizens", "Farmers", "Security", "Peoples",
                                          "Pioneer", "Heritage", "Frontier", "Cornerstone"]),
                              rng.choice(["State Bank", "National Bank", "Bank & Trust",
                                          "Bancorp", "Savings Bank"]))
            deal = {"name": name, "assets": t_assets, "price": price,
                    "market": target_mkt, "credit_mark": round(rng.uniform(0.02, 0.09), 3)}
            pf = deal_proforma(state, deal)
            deal["proforma"] = pf
            events.append({
                "type": "bank_for_sale", "blocking": True,
                "title": "Acquisition opportunity: %s" % name,
                "text": ("%s (assets $%sM, based in %s) is quietly for sale. Price: $%s "
                         "(%.2fx tangible book). Due diligence estimates a %d%% credit mark "
                         "on their loans and typical integration attrition of 5-12%% of "
                         "deposits.\n\nPro-forma after close: CET1 %.1f%%, leverage %.1f%% "
                         "(%s-capitalized).%s"
                         % (name, f"{t_assets // 100 // 1_000_000:,}",
                            state["regions"][target_mkt]["name"], f"{price // 100:,}",
                            mult, int(deal["credit_mark"] * 100),
                            pf["cet1"] * 100, pf["leverage"] * 100, pf["pca"],
                            (" Cannot close: " + "; ".join(pf["blockers"]) + ".")
                            if pf["blockers"] else
                            " Regulatory approval still needs CAMELS 1-2, no orders, "
                            "satisfactory CRA.")),
                "deal": deal,
                "choices": ["buy", "pass"],
            })

    if assets > 100_000_000_00 and rng.chance(0.02) and \
            state["regulation"]["camels"]["composite"] <= 2:
        equity = L.total_equity(bank["ledger"])
        tbv = equity - bank["ledger"]["balances"]["1600"]
        offer = int(tbv * rng.uniform(1.35, 1.95))
        events.append({
            "type": "buyout_offer", "blocking": True,
            "title": "Someone wants to buy YOUR bank",
            "text": ("A larger institution has approached the board with an all-cash offer "
                     "of $%s (%.2fx tangible book, $%.2f per share). Accepting ends the "
                     "game with a sale. The board will follow your recommendation.")
                    % (f"{offer // 100:,}", offer / max(1, tbv),
                       offer / 100 / max(1, bank["shares"])),
            "offer": offer, "choices": ["accept", "decline"],
        })
    return events


def _resolve_fdic_bid(state, ev, premium_bp):
    """FDIC-assisted acquisition of a failed rival."""
    bank = state["bank"]
    reg = state["regulation"]
    fr = ev["franchise"]
    if reg["camels"]["composite"] > 3 or reg["pca"] not in ("well", "adequate"):
        return "The FDIC will not accept bids from banks in your condition."
    if reg["bsa"]["fined"]:
        return "Your BSA consent order disqualifies you from assisted transactions."
    if premium_bp <= fr["rival_bid_bp"]:
        return {"lost": True,
                "message": "You bid %dbp; a rival bid %dbp and won the franchise."
                           % (premium_bp, fr["rival_bid_bp"])}
    deposits_assumed = fr["deposits"]
    loans_net = int(fr["loans"] * (1 - fr["credit_mark"]))
    loans_net = min(loans_net, deposits_assumed)   # FDIC keeps the excess
    premium = int(deposits_assumed * premium_bp / 10000)
    fdic_cash = deposits_assumed - loans_net - premium
    lines = [["1300", loans_net, 0]]
    if fdic_cash >= 0:
        lines.append(["1000", fdic_cash, 0])
    else:
        lines.append(["1000", 0, -fdic_cash])
    if premium > 0:
        lines.append(["1600", premium, 0])
    # deposits distributed to account types
    split = {"2000": 0.25, "2010": 0.10, "2020": 0.15, "2030": 0.28, "2040": 0.22}
    alloc = 0
    keys = sorted(split.keys())
    for i, acct in enumerate(keys):
        amt = deposits_assumed - alloc if i == len(keys) - 1 \
            else int(deposits_assumed * split[acct])
        alloc += amt
        lines.append([acct, 0, amt])
    L.post(bank["ledger"], state["time"]["date"],
           "FDIC-assisted acquisition of %s" % ev["bank_name"], lines, tag="ma")

    _absorb_franchise(state, fr["markets"], deposits_assumed, loans_net,
                      fr["branches"], ev["bank_name"])
    prov = int(loans_net * 0.02)
    L.post(bank["ledger"], state["time"]["date"],
           "Day-1 reserve on acquired loans",
           [["5150", prov, 0], ["1350", 0, prov]], tag="ma")
    return {"lost": False,
            "message": "You won the auction at %dbp. Overnight, $%sM of deposits, %d "
                       "branches and a loan book joined the bank."
                       % (premium_bp, f"{deposits_assumed // 100 // 1_000_000:,}",
                          fr["branches"])}


def _resolve_bank_purchase(state, ev):
    bank = state["bank"]
    deal = ev["deal"]
    pf = deal_proforma(state, deal)
    if not pf["can_buy"]:
        return "Cannot close: " + "; ".join(pf["blockers"]) + "."
    from .funding import ensure_cash
    if ensure_cash(state, deal["price"]) < deal["price"]:
        return "Not enough cash for the purchase price ($%s)." % f"{deal['price'] // 100:,}"

    t_assets = deal["assets"]
    t_deposits = int(t_assets * 0.82)
    t_loans = int(t_assets * 0.65 * (1 - deal["credit_mark"]))
    t_sec = int(t_assets * 0.18)
    t_cash = t_assets - int(t_assets * 0.65) - t_sec
    net_assets = t_loans + t_sec + t_cash - t_deposits
    goodwill = max(0, deal["price"] - net_assets)
    lines = [["1300", t_loans, 0], ["1200", t_sec, 0], ["1000", t_cash, 0],
             ["1600", goodwill, 0], ["1000", 0, deal["price"]]]
    if goodwill == 0 and deal["price"] < net_assets:
        lines.append(["4150", 0, net_assets - deal["price"]])   # bargain purchase gain
    split = {"2000": 0.25, "2010": 0.10, "2020": 0.15, "2030": 0.28, "2040": 0.22}
    alloc = 0
    keys = sorted(split.keys())
    for i, acct in enumerate(keys):
        amt = t_deposits - alloc if i == len(keys) - 1 else int(t_deposits * split[acct])
        alloc += amt
        lines.append([acct, 0, amt])
    L.post(bank["ledger"], state["time"]["date"],
           "Acquisition of %s" % deal["name"], lines, tag="ma")
    # acquired securities become AFS treasuries of medium tenor
    if t_sec > 0:
        econ = state["economy"]
        coupon = securities.type_yield(econ, "treasury", 4.0)
        book = bank["securities"]
        book["lots"].append({"id": book["next_id"], "type": "treasury", "tenor0": 4.0,
                             "maturity_m": 48, "coupon": coupon, "par": t_sec,
                             "book": t_sec, "cls": "AFS", "mv": t_sec,
                             "bought": state["time"]["date"]})
        book["next_id"] += 1
    branches = max(1, int((t_assets / 100 / 1_000_000) ** 0.5 / 3))
    _absorb_franchise(state, [deal["market"]], t_deposits, t_loans, branches, deal["name"])
    bank["acquisitions"].append({"name": deal["name"], "date": state["time"]["date"],
                                 "price": deal["price"], "attrition_months": 9})
    return {"message": "The deal closed. %s is now part of %s. Goodwill booked: $%s. "
                       "Expect deposit attrition during integration."
                       % (deal["name"], bank["name"], f"{goodwill // 100:,}")}


def _absorb_franchise(state, markets, deposits_amt, loans_amt, n_branches, src_name):
    """Distribute acquired deposits/loans into pools; add branches."""
    bank = state["bank"]
    from .deposits import open_market, PRODUCTS as DP, MIX
    mkts = [m for m in markets if m in state["regions"]] or ["caprock"]
    per_mkt = deposits_amt // len(mkts)
    for mid in mkts:
        open_market(bank["deposits"], mid)
        bank["ops"]["brand"].setdefault(mid, 8.0)
        bank["ops"]["marketing"].setdefault(mid, 0)
        pools = bank["deposits"]["pools"][mid]
        for p in DP:
            add = int(per_mkt * MIX[p])
            pools[p]["balance"] += add
            pools[p]["accounts"] += max(1, add // 10_000_00)
            if p.startswith("cd_"):
                from .deposits import effective_rate
                pools[p]["wavg_rate"] = effective_rate(state, p)
    # loans: spread across ci/cre/mortgage/small_business in those markets
    year = state["time"]["date"][:4]
    split = [("ci", 0.3), ("cre", 0.35), ("mortgage", 0.2), ("small_business", 0.15)]
    per_mkt_l = loans_amt // len(mkts)
    for mid in mkts:
        for prod, frac in split:
            amt = int(per_mkt_l * frac)
            if amt > 0:
                rate = loans.offer_rate(state, prod, "B", mid)
                loans.add_to_pool(bank["loans"], prod, mid, "B", year, amt, rate, 1.1)
    per_b = max(1, n_branches // len(mkts))
    for mid in mkts:
        for _ in range(per_b):
            bank["ops"]["branches"].append({
                "id": bank["ops"]["next_branch_id"], "market": mid, "open": True,
                "quality": 2, "monthly_cost": operations.BRANCH_MONTHLY,
                "opened": state["time"]["date"], "acquired_from": src_name})
            bank["ops"]["next_branch_id"] += 1


def _integration_month(state, rng):
    """Deposit attrition and one-time costs after acquisitions."""
    bank = state["bank"]
    for acq in bank["acquisitions"]:
        if acq["attrition_months"] <= 0:
            continue
        acq["attrition_months"] -= 1
        # 0.5-1.5% of deposits walk each month during integration
        frac = rng.uniform(0.004, 0.012)
        total_dep = L.total_deposits(bank["ledger"])
        out = int(total_dep * frac * 0.3)
        if out > 0:
            crises._execute_outflow(state, out)
        cost = rng.randint(20_000_00, 90_000_00)
        L.post(bank["ledger"], state["time"]["date"],
               "Integration costs: %s" % acq["name"],
               [["5170", cost, 0], ["1000", 0, cost]], tag="ma")
        if rng.chance(0.06):
            push_event(state, {
                "type": "integration_trouble", "blocking": False,
                "title": "Integration trouble at %s" % acq["name"],
                "text": "A botched systems conversion weekend doubled attrition this month. "
                        "Acquired customers are testing the competition."})


# --------------------------------------------------------------- advance

def inbox_waiting(state):
    """Decisions that should stop a multi-day advance."""
    if any(e.get("blocking") or e.get("choices") for e in state["events"]["pending"]):
        return True
    if state["bank"]["loans"]["queue"]:
        return True
    if any(c.get("status") == "open" for c in state["bank"]["fraud"]["cases"]):
        return True
    return False


def advance(state, unit="day", skip_inbox=False):
    """unit: day | week | month | quarter. Stops early on blocking events
    and (for week/month/quarter) on inbox items the player has not seen."""
    n = {"day": 1, "week": 5, "month": 22, "quarter": 66}.get(unit, 1)
    watch_inbox = (not skip_inbox) and unit in ("week", "month", "quarter")
    if watch_inbox and inbox_waiting(state):
        return {"days": 0, "events": [], "date": state["time"]["date"],
                "inbox": True}
    all_events = []
    ran = 0
    for _ in range(n):
        if state["game_over"]:
            break
        evs = step_day(state)
        all_events.extend(evs)
        ran += 1
        if any(e.get("blocking") for e in evs):
            break
        if watch_inbox and inbox_waiting(state):
            break
    return {"days": ran, "events": all_events, "date": state["time"]["date"],
            "inbox": watch_inbox and inbox_waiting(state)}


# ---------------------------------------------------------------- actions

class ActionError(Exception):
    pass


def perform_action(state, action, payload):
    """All player actions funnel through here. Returns a result dict;
    raises ActionError with a human-readable message on refusal."""
    if state["game_over"] and action not in ("dismiss_event",):
        raise ActionError("The game is over.")
    bank = state["bank"]
    p = payload or {}

    def _num(key, lo=None, hi=None):
        v = p.get(key)
        if not isinstance(v, (int, float)):
            raise ActionError("missing/invalid %s" % key)
        if lo is not None and v < lo:
            raise ActionError("%s below minimum" % key)
        if hi is not None and v > hi:
            raise ActionError("%s above maximum" % key)
        return v

    if action == "approve_loan" or action == "decline_loan":
        app_id = _num("app_id")
        q = bank["loans"]["queue"]
        app = next((a for a in q if a["id"] == app_id), None)
        if app is None:
            raise ActionError("application not found (may have expired)")
        q.remove(app)
        if action == "approve_loan":
            from .funding import ensure_cash
            if ensure_cash(state, app["amount"]) < app["amount"]:
                q.append(app)
                raise ActionError("not enough liquidity to fund this loan")
            loans.approve_application(state, app)
            bank["loans"]["stats"]["approved_apps"] += 1
            return {"message": "Funded %s for $%s." % (app["name"],
                                                       f"{app['amount'] // 100:,}")}
        bank["loans"]["stats"]["declined_apps"] += 1
        return {"message": "Declined %s." % app["name"]}

    if action == "buy_security":
        res = securities.buy(state, p.get("type"), float(_num("tenor", 0.25, 30)),
                             int(_num("par", 1)), p.get("cls", "AFS"))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Bought $%s %s at %.2f%% (%s)." % (
            f"{res['par'] // 100:,}", res["type"].upper(), res["coupon"] * 100, res["cls"])}

    if action == "sell_security":
        res = securities.sell(state, int(_num("lot_id")), p.get("par"))
        if isinstance(res, str):
            raise ActionError(res)
        for ev in res.get("events", []):
            push_event(state, ev)
        gl = res["gain_loss"]
        return {"message": "Sold for $%s (%s of $%s)." % (
            f"{res['proceeds'] // 100:,}", "gain" if gl >= 0 else "LOSS",
            f"{abs(gl) // 100:,}")}

    if action == "add_hedge":
        res = securities.add_hedge(state, p.get("kind"), int(_num("notional", 1)),
                                   float(_num("tenor", 0.5, 10)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Hedge added."}

    if action == "take_fhlb":
        res = funding.take_fhlb(state, int(_num("amount", 1)), int(_num("term", 1, 120)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Advance drawn at %.2f%%." % (res["rate"] * 100)}

    if action == "issue_brokered":
        res = funding.issue_brokered(state, int(_num("amount", 1)), int(_num("term", 1, 60)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Brokered CDs issued at %.2f%%." % (res["rate"] * 100)}

    if action == "issue_subdebt":
        res = funding.issue_subdebt(state, int(_num("amount", 1)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Sub debt issued at %.2f%%." % (res["rate"] * 100)}

    if action == "repay_funding":
        res = funding.repay(state, p.get("kind"), int(_num("item_id")))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Repaid."}

    if action == "raise_common":
        res = funding.raise_common(state, int(_num("amount", 1)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Raised at %.2fx book (%s new shares)." % (
            res["price_to_book"], f"{res['shares_issued']:,}")}

    if action == "issue_preferred":
        res = funding.issue_preferred(state, int(_num("amount", 1)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Preferred issued at %.2f%%." % (res["rate"] * 100)}

    if action == "buyback":
        res = funding.buyback(state, int(_num("amount", 1)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Bought back %s shares." % f"{res['shares_bought']:,}"}

    if action == "open_branch":
        res = operations.open_branch(state, p.get("market"), int(p.get("quality", 2)))
        if isinstance(res, str):
            raise ActionError(res)
        mid = p.get("market")
        home = (state.get("meta") or {}).get("home", "caprock")
        if mid and mid != home:
            chron = state.get("chronicle")
            if not isinstance(chron, dict):
                chron = {"notable": []}
                state["chronicle"] = chron
            notes = chron.setdefault("notable", [])
            label = "Opened a branch in %s." % state["regions"].get(mid, {}).get("name", mid)
            if label not in notes:
                notes.append(label)
        return {"message": "Branch opened."}

    if action == "close_branch":
        res = operations.close_branch(state, int(_num("branch_id")))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Branch closed."}

    if action == "hire":
        res = operations.hire(state, p.get("role"), int(_num("count", 1, 50)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Hired."}

    if action == "fire":
        res = operations.fire(state, p.get("role"), int(_num("count", 1, 50)))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Done."}

    if action == "train":
        res = operations.train(state, p.get("role"))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Training complete (skill %.2f)." % res["skill"]}

    if action == "invest_digital":
        res = operations.invest_digital(state)
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Digital level is now %d." % res["level"]}

    if action == "upgrade_core":
        res = operations.upgrade_core(state)
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Core system replaced. Age reset."}

    if action == "resolve_fraud_case":
        res = fraud.resolve_case(state, int(_num("case_id")), p.get("choice", "act"),
                                 _rng(state, "fraud"))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": res["message"]}

    if action == "unlock_product":
        prod = p.get("product")
        if prod not in UNLOCKS:
            raise ActionError("unknown product")
        if prod in bank["products_enabled"]:
            raise ActionError("already offered")
        min_assets, cost, label = UNLOCKS[prod]
        if bank["cached_assets"] < min_assets:
            raise ActionError("requires $%sM in assets" % f"{min_assets // 100 // 1_000_000:,}")
        from .funding import ensure_cash
        if ensure_cash(state, cost) < cost:
            raise ActionError("not enough cash ($%s setup cost)" % f"{cost // 100:,}")
        L.post(bank["ledger"], state["time"]["date"], "Launch: %s" % label,
               [["5170", cost, 0], ["1000", 0, cost]], tag="line")
        bank["products_enabled"].append(prod)
        return {"message": "%s launched." % label}

    if action == "event_choice":
        ev_id = _num("event_id")
        choice = p.get("choice")
        pend = state["events"]["pending"]
        ev = next((e for e in pend if e["id"] == ev_id), None)
        if ev is None:
            raise ActionError("event not found")
        result = _handle_event_choice(state, ev, choice, p)
        pend.remove(ev)
        return result

    if action == "dismiss_event":
        ev_id = _num("event_id")
        pend = state["events"]["pending"]
        ev = next((e for e in pend if e["id"] == ev_id), None)
        if ev is not None:
            pend.remove(ev)
        return {"message": "ok"}

    if action == "advisor_dismiss":
        from . import advisor
        advisor.dismiss(state, str(p.get("card_id", "")))
        return {"message": "ok"}

    if action == "tutorial_ack":
        from . import advisor
        advisor.ack_step(state, str(p.get("step_id", "")))
        return {"message": "ok"}

    if action == "tutorial_off":
        from . import advisor
        advisor.tutorial_off(state)
        return {"message": "Tour dismissed. It won't come back."}

    if action == "retire":
        _game_over(state, "retired")
        return {"message": "You retired. See the epilogue."}

    raise ActionError("unknown action: %s" % action)


def _handle_event_choice(state, ev, choice, payload):
    if ev["type"] == "fdic_auction":
        if choice == "pass":
            return {"message": "You passed. The franchise went to another bidder."}
        bp = payload.get("premium_bp")
        if not isinstance(bp, (int, float)) or bp < 0 or bp > 1000:
            raise ActionError("premium_bp must be 0-1000")
        res = _resolve_fdic_bid(state, ev, int(bp))
        if isinstance(res, str):
            raise ActionError(res)
        return res

    if ev["type"] == "bank_for_sale":
        if choice == "pass":
            return {"message": "You passed on the deal."}
        res = _resolve_bank_purchase(state, ev)
        if isinstance(res, str):
            raise ActionError(res)
        return res

    if ev["type"] == "buyout_offer":
        if choice == "accept":
            from . import goals as GOALS
            equity = L.total_equity(state["bank"]["ledger"])
            tbv = max(1, equity - state["bank"]["ledger"]["balances"]["1600"])
            GOALS.record_sale(state, ev["offer"], tbv)
            win = GOALS.check_win(state)
            _game_over(state, "sold")
            if win:
                state["game_over"]["goal"] = GOALS.progress(state)
            return {"message": "The bank is sold. See the epilogue."}
        state.setdefault("chronicle", {}).setdefault("declined_buyouts", 0)
        state["chronicle"]["declined_buyouts"] = (
            state["chronicle"].get("declined_buyouts", 0) + 1)
        return {"message": "The board declined the offer."}

    if ev["type"] == "goal_won":
        if choice == "retire":
            _game_over(state, "retired")
            return {"message": "You retired. The square will remember the name."}
        return {"message": "The sandbox stays open. Play on."}

    if ev["type"] == "fraud_case":
        res = fraud.resolve_case(state, ev["case_id"],
                                 "act" if choice == "act" else "monitor",
                                 _rng(state, "fraud"))
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": res["message"]}

    if ev["type"] == "overnight_shortfall":
        return _resolve_overnight_choice(state, ev, choice)

    # generic acknowledge
    return {"message": "Acknowledged."}


def _resolve_overnight_choice(state, ev, choice):
    """Player covers (or declines to cover) an ask-policy cash hole."""
    from . import funding as FUND
    need = int(ev.get("need") or 0)
    cash = state["bank"]["ledger"]["balances"]["1000"]
    if cash < 0:
        need = max(need, -cash)
    if choice == "wait":
        return {"message": "You left the hole open. Cover it from Treasury, or "
                           "the clock will stop again tomorrow."}
    if choice == "fhlb":
        take = max(100_000_00, (need + 99_999_00) // 100_000_00 * 100_000_00)
        res = FUND.take_fhlb(state, take, 1)
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "FHLB advance drawn to cover the overnight hole."}
    if choice == "fed_funds":
        take = max(1, need)
        L.post(state["bank"]["ledger"], state["time"]["date"],
               "Fed funds purchased (overnight, player)",
               [["1000", take, 0], ["2110", 0, take]], tag="fund")
        return {"message": "Borrowed fed funds overnight."}
    if choice == "window":
        take = max(1, need)
        L.post(state["bank"]["ledger"], state["time"]["date"],
               "DISCOUNT WINDOW borrowing",
               [["1000", take, 0], ["2120", 0, take]], tag="fund")
        state["bank"]["funding"]["discount_window_uses"] += 1
        return {"message": "Discount window drawn. Examiners will count this one."}
    raise ActionError("unknown overnight choice")


# ----------------------------------------------------------------- policy

POLICY_SPECS = [
    # (prefix, keys-or-None, type, lo, hi)
    ("deposits.offsets_bp.", list(deposits.PRODUCTS), int, -300, 300),
    ("deposits.promo_cd_bonus", None, float, 0.0, 0.03),
    ("deposits.fees.monthly_fee", None, int, 0, 50_00),
    ("deposits.fees.overdraft_fee", None, int, 0, 75_00),
    ("deposits.fees.nsf_fee", None, int, 0, 75_00),
    ("deposits.fees.atm_fee", None, int, 0, 10_00),
    ("deposits.fees.wire_fee", None, int, 0, 100_00),
    ("deposits.fees.foreign_txn_pct", None, int, 0, 500),
    ("deposits.fees.safe_deposit_annual", None, int, 0, 500_00),
    ("loans.spreads.", list(loans.PRODUCTS), int, -300, 500),
    ("loans.standards.", list(loans.PRODUCTS), int, 0, 4),
    ("loans.limits.", list(loans.PRODUCTS), int, 0, 100),
    ("loans.approval_threshold", None, int, 100_000_00, 100_000_000_00),
    ("loans.auto_policy", None, ("queue", "approve_ab", "decline"), None, None),
    ("loans.mortgage_sale_frac", None, float, 0.0, 0.9),
    ("ops.salary_multiplier", None, float, 0.7, 2.0),
    ("ops.auto_backfill", None, (True, False), None, None),
    ("ops.cyber_spend", None, int, 0, 100_000_000_00),
    ("ops.audit_spend", None, int, 0, 100_000_000_00),
    ("ops.marketing.", None, int, 0, 1_000_000_000_00),   # any market id
    ("fraud.prevention_spend", None, int, 0, 100_000_000_00),
    ("fraud.threshold", None, int, 0, 4),
    ("regulation.bsa.program_spend", None, int, 0, 100_000_000_00),
    ("policies.dividend_payout", None, int, 0, 100),
    ("funding.overnight_policy", None, ("ask", "auto"), None, None),
]


def set_policy(state, path, value):
    for prefix, keys, typ, lo, hi in POLICY_SPECS:
        matched = False
        key = None
        if prefix.endswith("."):
            if path.startswith(prefix):
                key = path[len(prefix):]
                if keys is None or key in keys:
                    matched = True
        elif path == prefix:
            matched = True
        if not matched:
            continue
        # validate value
        if isinstance(typ, tuple):
            if value not in typ:
                raise ActionError("value must be one of %s" % (typ,))
        elif typ is int:
            if not isinstance(value, (int, float)):
                raise ActionError("numeric value required")
            value = int(value)
            if value < lo or value > hi:
                raise ActionError("value out of range [%s, %s]" % (lo, hi))
        elif typ is float:
            if not isinstance(value, (int, float)):
                raise ActionError("numeric value required")
            value = float(value)
            if value < lo or value > hi:
                raise ActionError("value out of range [%s, %s]" % (lo, hi))
        # apply
        parts = path.split(".")
        target = state["bank"] if parts[0] != "regulation" else state
        node = target
        for part in parts[:-1]:
            node = node[part]
        # marketing for unknown market: only allow existing regions
        if path.startswith("ops.marketing."):
            if parts[-1] not in state["regions"]:
                raise ActionError("unknown market")
        node[parts[-1]] = value
        return {"path": path, "value": value}
    raise ActionError("unknown or protected policy path: %s" % path)
