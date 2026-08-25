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
import math

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


def served_markets(state):
    """Markets where we have deposits, loans, or an open branch."""
    bank = state["bank"]
    mids = set()
    for b in bank["ops"]["branches"]:
        if b.get("open"):
            mids.add(b["market"])
    for mid, pools in bank["deposits"]["pools"].items():
        if any((pools.get(p) or {}).get("balance", 0) > 0 for p in pools):
            mids.add(mid)
    for p in bank["loans"]["pools"]:
        if p.get("balance", 0) > 0:
            mids.add(p["market"])
    for l in bank["loans"]["large"]:
        if l.get("status") not in ("paid", "defaulted") and l.get("balance", 0) > 0:
            mids.add(l["market"])
    return mids


def _inbox_worthy(state, ev):
    """News is signal: local shocks only if we serve the town; national
    headlines are capped separately."""
    et = ev.get("type")
    rid = ev.get("region")
    if et in ("region_shock", "region_shock_end"):
        return rid in served_markets(state)
    return True


def _national_headline(state, prev):
    """At most one national wire a month, and only if something moved."""
    econ = state["economy"]
    era = (state.get("meta") or {}).get("era", "sandbox")
    from . import goals as GOALS
    when = GOALS.display_date(state)

    if econ.get("in_bust", 0) > 0 and prev.get("in_bust", 0) == 0:
        return {"type": "national", "blocking": False,
                "title": "Credit crunch — %s" % when,
                "text": ("Wholesale markets just seized up. Credit stress is "
                         "%.0f%%. Construction and CRE will feel it first; "
                         "uninsured depositors will read the papers."
                         % (econ["credit_stress"] * 100))}
    if econ["recession"] and not prev.get("recession"):
        return {"type": "national", "blocking": False,
                "title": "Recession — %s" % when,
                "text": ("The expansion ended. Unemployment is %.1f%% and the "
                         "output gap is %.1f. Loan demand will shrink; watch "
                         "the vintages you wrote in the last two years."
                         % (econ["unemployment"], econ["output_gap"]))}
    move = econ["fed_funds"] - prev.get("fed_funds", econ["fed_funds"])
    if abs(move) >= 0.005:
        direction = "hiked" if move > 0 else "cut"
        extra = ""
        if era == "historical":
            year = int(state["time"]["date"][:4])
            if year >= 2022 and move > 0:
                extra = " Duration on the bond book just got more expensive."
            elif 2007 <= year <= 2009 and move < 0:
                extra = " This is crisis-fighting, not a gift."
        return {"type": "national", "blocking": False,
                "title": "The Fed %s %dbp — %s" % (direction, int(round(abs(move) * 10000)), when),
                "text": ("Fed funds is now %.2f%%.%s Deposit betas and loan "
                         "repricing will follow at their own speeds."
                         % (econ["fed_funds"] * 100, extra))}
    if econ["credit_stress"] - prev.get("credit_stress", 0) >= 0.12:
        return {"type": "national", "blocking": False,
                "title": "Credit stress jumped — %s" % when,
                "text": ("Stress is %.0f%%. Charge-offs lag this number by "
                         "months. Tighten construction and CRE before the "
                         "exam, not after." % (econ["credit_stress"] * 100))}
    return None


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
    pool_total = deposits.totals(bank["deposits"])["_total"]
    brokered = -bank["ledger"]["balances"]["2050"]
    if pool_total != L.total_deposits(bank["ledger"]) - brokered:
        problems.append("deposit pools %d != GL deposits-brokered %d"
                        % (pool_total, L.total_deposits(bank["ledger"]) - brokered))
    loans_total = loans.total_loans(bank["loans"])
    if loans_total != bank["ledger"]["balances"]["1300"]:
        problems.append("loan pools %d != GL 1300 %d"
                        % (loans_total, bank["ledger"]["balances"]["1300"]))
    htm_book = sum(l["book"] for l in bank["securities"]["lots"] if l["cls"] == "HTM")
    if bank["ledger"]["balances"]["1210"] != htm_book:
        problems.append("HTM lots %d != GL 1210 %d"
                        % (htm_book, bank["ledger"]["balances"]["1210"]))
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

    prev_econ = {
        "fed_funds": state["economy"]["fed_funds"],
        "recession": state["economy"]["recession"],
        "credit_stress": state["economy"]["credit_stress"],
        "in_bust": state["economy"].get("in_bust", 0),
    }
    era = (state.get("meta") or {}).get("era", "sandbox")
    economy.step_month(state["economy"], _rng(state, "econ"),
                       date=state["time"]["date"], era=era)
    national_used = False
    wire = _national_headline(state, prev_econ)
    if wire:
        raised.append(push_event(state, wire))
        national_used = True
    for ev in regions.step_month(state["regions"], state["economy"], _rng(state, "region")):
        if not _inbox_worthy(state, ev):
            continue
        if ev.get("type") in ("region_shock", "region_shock_end"):
            raised.append(push_event(state, ev))
            continue
        if not national_used:
            raised.append(push_event(state, ev))
            national_used = True
    for ev in competitors.step_month(state, _rng(state, "comp")):
        if ev.get("type") == "fdic_auction" and ev.get("franchise"):
            ev["proforma"] = fdic_proforma(state, ev["franchise"], 80)
            pf = ev["proforma"]
            my_a = max(1, state["bank"].get("cached_assets") or 1)
            mult = (ev["franchise"].get("deposits") or 0) / my_a
            ev["text"] = (ev.get("text") or "") + (
                "\n\nThis franchise is %.1f× your bank. "
                "Your books after an 80bp bid: CET1 %.1f%%, leverage %.1f%% "
                "(%s-capitalized).%s"
                % (mult, pf["cet1"] * 100, pf["leverage"] * 100, pf["pca"],
                   (" Cannot close: " + "; ".join(pf["blockers"]) + ".")
                   if pf["blockers"] else ""))
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
    for ev in _pipeline_month(state, _rng(state, "event")):
        raised.append(push_event(state, ev))

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
        stop_q = bool(bank.get("policies", {}).get("stop_on_quarter"))
        raised.append(push_event(state, {
            "type": "quarter_close", "blocking": stop_q,
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
               if rank.get(r["kind"], 4) <= cap
               and regions.market_unlocked(state, mid)]
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
        # Community-era deals stay smaller than you. Once regional, you
        # can see a larger book — still refused if pro-forma capital breaks.
        if assets >= 2_000_000_000_00:
            t_assets = int(assets * rng.uniform(0.25, 1.20))
        elif assets >= 400_000_000_00:
            t_assets = int(assets * rng.uniform(0.15, 0.55))
        else:
            t_assets = int(assets * rng.uniform(0.10, 0.35))
        if t_assets >= 2_000_000_00:
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
            rival = competitors.circling_rival(state, deal)
            if rival:
                deal["circling_id"] = rival["id"]
                deal["circling_name"] = rival["name"]
            choices = ["buy", "hold", "pass"]
            if state["bank"].get("listed"):
                choices = ["buy", "buy_stock", "hold", "pass"]
            if rival:
                threat = (
                    "\n\n%s is circling this book. Buy now, hold it in diligence "
                    "(about three months — they may close while you raise), or pass "
                    "and they likely take it this week." % rival["name"])
            else:
                threat = ("\n\nNo living rival can fund this book. Hold or pass "
                          "without losing it to the street.")
            close_note = (
                (" Cannot close: " + "; ".join(pf["blockers"]) + ".")
                if pf["blockers"] else
                " Regulatory approval still needs CAMELS 1-2, no orders, "
                "satisfactory CRA.")
            if state["bank"].get("listed"):
                close_note += " Listed: you can pay 40% in stock at the last print."
            events.append({
                "type": "bank_for_sale", "blocking": True,
                "choices": choices,
                "title": "Acquisition opportunity: %s" % name,
                "text": ("%s (assets $%sM, based in %s) is quietly for sale. "
                         "That is %.2f× your bank. Price: $%s "
                         "(%.2fx tangible book). Due diligence estimates a %d%% credit mark "
                         "on their loans and typical integration attrition of 5-12%% of "
                         "deposits.\n\nPro-forma after close: CET1 %.1f%%, leverage %.1f%% "
                         "(%s-capitalized).%s%s"
                         % (name, f"{t_assets // 100 // 1_000_000:,}",
                            state["regions"][target_mkt]["name"],
                            t_assets / max(1, assets),
                            f"{price // 100:,}",
                            mult, int(deal["credit_mark"] * 100),
                            pf["cet1"] * 100, pf["leverage"] * 100, pf["pca"],
                            close_note, threat)),
                "deal": deal,
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


def fdic_proforma(state, franchise, premium_bp=80):
    """Capital impact of winning an FDIC auction, without mutating state."""
    from .regulation import capital_ratios, pca_category
    r = capital_ratios(state)
    deposits_assumed = int(franchise.get("deposits") or 0)
    loans_gross = int(franchise.get("loans") or 0)
    mark = float(franchise.get("credit_mark") or 0.0)
    loans_net = min(int(loans_gross * (1 - mark)), deposits_assumed)
    premium = int(deposits_assumed * max(0, int(premium_bp)) / 10000)
    provision = int(loans_net * 0.02)
    new_assets = r["assets"] + deposits_assumed
    new_te = r["cet1"] - provision - premium
    lev = new_te / max(1, new_assets)
    new_rwa = r["rwa"] + loans_net
    cet1 = new_te / max(1, new_rwa)
    fake = dict(r)
    fake.update({"cet1_ratio": cet1, "leverage_ratio": lev,
                 "tang_equity_ratio": lev, "cet1": new_te,
                 "tier1_ratio": cet1, "total_ratio": cet1})
    pca = pca_category(fake)
    blockers = []
    if deposits_assumed > r["assets"] * 2:
        blockers.append(
            "the franchise is more than twice your bank — you would be the "
            "acquired, not the acquirer")
    if pca not in ("well", "adequate"):
        blockers.append("pro-forma capital would be %s-capitalized" % pca)
    if lev < 0.05:
        blockers.append("pro-forma leverage would be %.1f%%" % (lev * 100))
    return {
        "new_assets": new_assets, "new_te": new_te,
        "leverage": round(lev, 5), "cet1": round(cet1, 5),
        "pca": pca, "premium": premium, "deposits": deposits_assumed,
        "can_bid": not blockers, "blockers": blockers,
    }


def _resolve_fdic_bid(state, ev, premium_bp):
    """FDIC-assisted acquisition of a failed rival."""
    bank = state["bank"]
    reg = state["regulation"]
    fr = ev["franchise"]
    if reg["camels"]["composite"] > 3 or reg["pca"] not in ("well", "adequate"):
        return "The FDIC will not accept bids from banks in your condition."
    if reg["bsa"]["fined"]:
        return "Your BSA consent order disqualifies you from assisted transactions."
    pf = fdic_proforma(state, fr, premium_bp)
    if not pf["can_bid"]:
        return "The FDIC will not award you this franchise: " + "; ".join(pf["blockers"]) + "."
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


def _resolve_bank_purchase(state, ev, stock_frac=0.0):
    bank = state["bank"]
    deal = ev["deal"]
    pf = deal_proforma(state, deal)
    if not pf["can_buy"]:
        return "Cannot close: " + "; ".join(pf["blockers"]) + "."
    stock_frac = 0.40 if stock_frac else 0.0
    if stock_frac and not bank.get("listed"):
        return "stock as deal currency requires a listing"
    cash_part = int(deal["price"] * (1.0 - stock_frac))
    stock_part = deal["price"] - cash_part
    from .funding import ensure_cash, share_quote
    if ensure_cash(state, cash_part) < cash_part:
        return "Not enough cash for the purchase price ($%s)." % f"{cash_part // 100:,}"

    t_assets = deal["assets"]
    t_deposits = int(t_assets * 0.82)
    t_loans = int(t_assets * 0.65 * (1 - deal["credit_mark"]))
    t_sec = int(t_assets * 0.18)
    t_cash = t_assets - int(t_assets * 0.65) - t_sec
    net_assets = t_loans + t_sec + t_cash - t_deposits
    goodwill = max(0, deal["price"] - net_assets)
    lines = [["1300", t_loans, 0], ["1200", t_sec, 0], ["1000", t_cash, 0],
             ["1600", goodwill, 0], ["1000", 0, cash_part]]
    if stock_part > 0:
        lines.append(["3000", 0, stock_part])
    if goodwill == 0 and deal["price"] < net_assets:
        lines.append(["4150", 0, net_assets - deal["price"]])   # bargain purchase gain
    split = {"2000": 0.25, "2010": 0.10, "2020": 0.15, "2030": 0.28, "2040": 0.22}
    alloc = 0
    keys = sorted(split.keys())
    for i, acct in enumerate(keys):
        amt = t_deposits - alloc if i == len(keys) - 1 else int(t_deposits * split[acct])
        alloc += amt
        lines.append([acct, 0, amt])
    issued = 0
    if stock_part > 0:
        q = share_quote(state)
        issued = stock_part // max(1, q["px"])
        bank["shares"] += issued
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
    extra = ""
    if issued:
        extra = " Paid %s in new stock (%s shares)." % (
            f"${stock_part // 100:,}", f"{issued:,}")
    return {"message": "The deal closed. %s is now part of %s. Goodwill booked: $%s. "
                       "Expect deposit attrition during integration.%s"
                       % (deal["name"], bank["name"], f"{goodwill // 100:,}", extra)}


def _split_cents(total, weights):
    """Integer split that hands the leftover cents to the last bucket."""
    if not weights:
        return []
    wsum = sum(w for _, w in weights) or 1
    out = []
    alloc = 0
    for i, (key, w) in enumerate(weights):
        amt = total - alloc if i == len(weights) - 1 else int(total * w / wsum)
        alloc += amt
        out.append((key, amt))
    return out


def _absorb_franchise(state, markets, deposits_amt, loans_amt, n_branches, src_name):
    """Distribute acquired deposits/loans into pools; add branches."""
    bank = state["bank"]
    from .deposits import open_market, PRODUCTS as DP, MIX
    mkts = [m for m in markets if m in state["regions"]] or ["caprock"]
    dep_by_mkt = _split_cents(deposits_amt, [(m, 1) for m in mkts])
    for mid, share in dep_by_mkt:
        open_market(bank["deposits"], mid)
        bank["ops"]["brand"].setdefault(mid, 8.0)
        bank["ops"]["marketing"].setdefault(mid, 0)
        pools = bank["deposits"]["pools"][mid]
        for p, add in _split_cents(share, [(prod, MIX[prod]) for prod in DP]):
            pools[p]["balance"] += add
            if add > 0:
                pools[p]["accounts"] += max(1, add // 10_000_00)
            if p.startswith("cd_"):
                from .deposits import effective_rate
                pools[p]["wavg_rate"] = effective_rate(state, p)
    # loans: spread across ci/cre/mortgage/small_business in those markets
    year = state["time"]["date"][:4]
    split = [("ci", 0.3), ("cre", 0.35), ("mortgage", 0.2), ("small_business", 0.15)]
    loan_by_mkt = _split_cents(loans_amt, [(m, 1) for m in mkts])
    for mid, share in loan_by_mkt:
        for prod, amt in _split_cents(share, split):
            if amt > 0:
                rate = loans.offer_rate(state, prod, "B", mid)
                loans.book_flow(state, prod, mid, "B", year, amt, rate, 1.1)
    # A deal buys the books, not a window farm. Extra offices in one
    # town overlap the same catchment.
    per_b = max(1, min(3, n_branches // len(mkts)))
    for mid in mkts:
        for _ in range(per_b):
            bank["ops"]["branches"].append({
                "id": bank["ops"]["next_branch_id"], "market": mid, "open": True,
                "quality": 2, "monthly_cost": operations.BRANCH_MONTHLY,
                "opened": state["time"]["date"], "acquired_from": src_name})
            bank["ops"]["next_branch_id"] += 1


def pipeline(state):
    return state.setdefault("ma_pipeline", [])


def park_deal(state, ev):
    """Hold a private deal in diligence. Clock can run; a rival may close."""
    deal = ev.get("deal")
    if not deal:
        return "no deal to hold"
    pipe = pipeline(state)
    if any(x.get("deal", {}).get("name") == deal.get("name") for x in pipe):
        return "that book is already in diligence"
    if len(pipe) >= 2:
        return "you already have two books in diligence"
    rid = state.setdefault("next_pipeline_id", 1)
    state["next_pipeline_id"] = rid + 1
    item = {
        "id": rid,
        "deal": deal,
        "rival_id": deal.get("circling_id"),
        "rival_name": deal.get("circling_name"),
        "months_left": 3,
        "parked": state["time"]["date"],
    }
    pipe.append(item)
    return item


def rival_closes_deal(state, item):
    """A circling rival buys the packet. Player ledger unchanged."""
    deal = item.get("deal") or {}
    rival = competitors.find_rival(state, item.get("rival_id"))
    if rival is None or not rival.get("alive"):
        rival = competitors.circling_rival(state, deal)
    took = False
    if rival:
        took = competitors.rival_takes_packet(state, deal, rival)
    name = deal.get("name") or "the target"
    who = (rival or {}).get("name") or "A larger bank"
    town = state["regions"].get(deal.get("market"), {}).get("name", "")
    if took:
        title = "%s bought %s" % (who, name)
        text = ("%s closed the book you were sizing%s. That franchise "
                "is off the map. Next time, buy or pass — holding is a bet "
                "they wait."
                % (who, (" in %s" % town) if town else ""))
    else:
        title = "%s came off the market" % name
        text = "The seller walked. No living rival could fund the book either."
    return {
        "type": "deal_stolen", "blocking": True,
        "title": title, "text": text,
        "deal_name": name,
        "rival_name": who if took else None,
        "stolen": took,
    }


def _pipeline_month(state, rng):
    """Each month on the market raises the chance a rival closes."""
    events = []
    keep = []
    for item in list(pipeline(state)):
        item["months_left"] = int(item.get("months_left") or 0) - 1
        early = bool(item.get("rival_id")) and rng.chance(0.18)
        if item["months_left"] <= 0 or early:
            events.append(rival_closes_deal(state, item))
            continue
        keep.append(item)
    state["ma_pipeline"] = keep
    return events


def close_pipeline_deal(state, item_id, stock_frac=0.0):
    pipe = pipeline(state)
    item = next((x for x in pipe if x["id"] == item_id), None)
    if item is None:
        return "that deal is no longer on the market"
    item["deal"]["proforma"] = deal_proforma(state, item["deal"])
    res = _resolve_bank_purchase(state, {"deal": item["deal"]},
                                 stock_frac=stock_frac)
    if isinstance(res, str):
        return res
    pipe.remove(item)
    return res


def pass_private_deal(state, deal, force=None):
    """Walk away from a private book. A circling rival often takes it."""
    rival = competitors.find_rival(state, deal.get("circling_id")) \
        or competitors.circling_rival(state, deal)
    rng = _rng(state, "event")
    steal = force if force is not None else (bool(rival) and rng.chance(0.70))
    if steal and rival and competitors.rival_takes_packet(state, deal, rival):
        return {
            "message": "You passed. %s bought %s the same week."
                       % (rival["name"], deal.get("name") or "the bank"),
            "stolen": True, "rival_name": rival["name"],
        }
    return {"message": "You passed. The seller stayed independent.",
            "stolen": False}


def drop_pipeline_deal(state, item_id):
    pipe = pipeline(state)
    item = next((x for x in pipe if x["id"] == item_id), None)
    if item is None:
        return "that deal is no longer on the market"
    res = pass_private_deal(state, item.get("deal") or {})
    pipe.remove(item)
    return res


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
    fraud.prune_resolved_events(state)
    loans.apply_credit_box(state)
    if any(e.get("blocking") or e.get("choices") for e in state["events"]["pending"]):
        return True
    if state["bank"]["loans"]["queue"]:
        return True
    if any(c.get("status") == "open" for c in state["bank"]["fraud"]["cases"]):
        return True
    return False


def interrupt_reason(state):
    """Why Play until would stop right now. None if the clock can run."""
    if state.get("game_over"):
        return "game_over"
    fraud.prune_resolved_events(state)
    loans.apply_credit_box(state)
    if state["regulation"].get("seized"):
        return "seized"
    if any(e.get("blocking") for e in state["events"]["pending"]):
        return "blocking"
    if state["bank"]["loans"]["queue"]:
        return "credit"
    if any(c.get("status") == "open" for c in state["bank"]["fraud"]["cases"]):
        return "fraud"
    if state["regulation"]["pca"] not in ("well", "adequate"):
        return "pca"
    # Exam, run_start, and PCA already arrive as blocking events. Holding
    # the clock on the leftover rating / run flag made the next exam or
    # the run's end unreachable.
    return None


def advance(state, unit="day", skip_inbox=False, max_days=None):
    """unit: day | week | month | quarter | until.

    `until` is Play until: run day-by-day until an interrupt (or max_days).
    The credit box (if enabled) handles matching memos so they do not stop
    the clock. Quarter close is a log line unless policies.stop_on_quarter.
    Advisor never writes the box.
    """
    if unit == "until":
        n = int(max_days or 1260)
        watch_inbox = True
        skip_inbox = False
    else:
        n = {"day": 1, "week": 5, "month": 22, "quarter": 66}.get(unit, 1)
        watch_inbox = (not skip_inbox) and unit in ("week", "month", "quarter")
    if unit == "until":
        reason = interrupt_reason(state)
        if reason:
            return {"days": 0, "events": [], "date": state["time"]["date"],
                    "inbox": True, "stopped": reason}
    elif watch_inbox and inbox_waiting(state):
        return {"days": 0, "events": [], "date": state["time"]["date"],
                "inbox": True}
    all_events = []
    ran = 0
    stopped = None
    for _ in range(n):
        if state["game_over"]:
            stopped = "game_over"
            break
        evs = step_day(state)
        all_events.extend(evs)
        ran += 1
        if any(e.get("blocking") for e in evs):
            stopped = "blocking"
            break
        if unit == "until":
            reason = interrupt_reason(state)
            if reason:
                stopped = reason
                break
        elif watch_inbox and inbox_waiting(state):
            break
    return {"days": ran, "events": all_events, "date": state["time"]["date"],
            "inbox": watch_inbox and inbox_waiting(state),
            "stopped": stopped}


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

    if action in ("approve_loan", "decline_loan", "counter_loan", "participate_loan"):
        app_id = _num("app_id")
        q = bank["loans"]["queue"]
        app = next((a for a in q if a["id"] == app_id), None)
        if app is None:
            raise ActionError("application not found (may have expired)")
        q.remove(app)
        from .funding import ensure_cash
        if action == "approve_loan":
            if ensure_cash(state, app["amount"]) < app["amount"]:
                q.append(app)
                raise ActionError("not enough liquidity to fund this loan")
            loans.approve_application(state, app)
            bank["loans"]["stats"]["approved_apps"] += 1
            return {"message": "Funded %s for $%s." % (app["name"],
                                                       f"{app['amount'] // 100:,}")}
        if action == "decline_loan":
            loans.decline_application(state, app)
            bank["loans"]["stats"]["declined_apps"] += 1
            return {"message": "Declined %s." % app["name"]}
        if action == "counter_loan":
            extra_bp = int(p.get("extra_bp", 100) or 100)
            hold_frac = float(p.get("hold_frac", 0.70) or 0.70)
            terms = loans.counter_terms(app, extra_bp=extra_bp, hold_frac=hold_frac)
            if ensure_cash(state, terms["amount"]) < terms["amount"]:
                q.append(app)
                raise ActionError("not enough liquidity to fund the countered hold")
            res = loans.counter_application(state, app, _rng(state, "credit"),
                                            extra_bp=extra_bp, hold_frac=hold_frac)
            if res["accepted"]:
                bank["loans"]["stats"]["countered_apps"] = \
                    bank["loans"]["stats"].get("countered_apps", 0) + 1
                bank["loans"]["stats"]["approved_apps"] += 1
            else:
                bank["loans"]["stats"]["declined_apps"] += 1
            return {"message": res["message"], "accepted": res["accepted"]}
        hold_frac = float(p.get("hold_frac", 0.40) or 0.40)
        hold, _sold = loans.participate_hold(app, hold_frac)
        if ensure_cash(state, hold) < hold:
            q.append(app)
            raise ActionError("not enough liquidity to fund even a participation hold")
        res = loans.participate_application(state, app, hold_frac=hold_frac)
        bank["loans"]["stats"]["participated_apps"] = \
            bank["loans"]["stats"].get("participated_apps", 0) + 1
        bank["loans"]["stats"]["approved_apps"] += 1
        return {"message": res["message"], "hold": res["hold"], "sold": res["sold"]}

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

    if action == "preview_raise_common":
        res = funding.preview_raise_common(state, int(_num("amount", 1)))
        if isinstance(res, str):
            raise ActionError(res)
        return res

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

    if action == "preview_list_common":
        res = funding.listing_preview(state)
        if isinstance(res, str):
            raise ActionError(res)
        return res

    if action == "list_common":
        res = funding.list_common(state)
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "Listed at $%s a share (%.2fx book). Fees %s." % (
            f"{res['px'] // 100:,}", res["price_to_book"],
            f"${res['fees'] // 100:,}")}

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
        if ev in pend:
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

    if action == "preview_loan_stance":
        res = loans.preview_loan_stance(state, str(p.get("product") or ""),
                                        str(p.get("stance") or ""))
        if isinstance(res, str):
            raise ActionError(res)
        return res

    if action == "set_loan_stance":
        res = loans.set_loan_stance(state, str(p.get("product") or ""),
                                    str(p.get("stance") or ""))
        if isinstance(res, str):
            raise ActionError(res)
        return res

    if action == "sell_loans":
        res = loans.sell_loans(
            state,
            kind=str(p.get("kind") or "pool"),
            product=p.get("product"),
            market=p.get("market"),
            amount=p.get("amount"),
            loan_id=p.get("loan_id"),
        )
        if isinstance(res, str):
            raise ActionError(res)
        return res

    if action == "close_pipeline":
        stock = 0.40 if p.get("stock") else 0.0
        res = close_pipeline_deal(state, int(_num("pipeline_id")), stock_frac=stock)
        if isinstance(res, str):
            raise ActionError(res)
        return res

    if action == "drop_pipeline":
        res = drop_pipeline_deal(state, int(_num("pipeline_id")))
        if isinstance(res, str):
            raise ActionError(res)
        return res

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
            return pass_private_deal(state, ev.get("deal") or {})
        if choice == "hold":
            item = park_deal(state, ev)
            if isinstance(item, str):
                raise ActionError(item)
            who = (ev.get("deal") or {}).get("circling_name") or "a rival"
            return {"message": "The book is in diligence. %s is still circling. "
                               "You have about three months." % who,
                    "pipeline_id": item["id"]}
        stock = 0.40 if choice == "buy_stock" else 0.0
        res = _resolve_bank_purchase(state, ev, stock_frac=stock)
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
    import datetime
    need = int(ev.get("need") or 0)
    cash = state["bank"]["ledger"]["balances"]["1000"]
    if cash < 0:
        need = max(need, -cash)
    if choice == "wait":
        took = FUND.take_fed_funds(state, need,
                                   "Fed funds purchased (wait — penalty path)")
        leftover = need - took
        state["bank"]["funding"]["shrink_originations"] = True
        until = datetime.date.fromisoformat(state["time"]["date"]) + \
            datetime.timedelta(days=FUND.OVERNIGHT_WAIT_DAYS)
        state["bank"]["funding"]["overnight_wait_until"] = until.isoformat()
        state["bank"]["funding"]["overnight_wait_need"] = max(0, leftover)
        if leftover > 0:
            return {"message": "Fed-funds counterparties took $%s. The remaining "
                               "$%s stays as a penalty overdraft (fed funds + 150bp) "
                               "and we will not nag you every morning. "
                               "Originations shrink until cash recovers."
                               % (f"{took // 100:,}", f"{leftover // 100:,}")}
        return {"message": "Covered overnight with fed funds. Originations will "
                           "shrink until cash recovers. We will not re-ask for "
                           "three weeks unless the hole grows."}
    if choice == "fhlb":
        take = max(100_000_00, (need + 99_999_00) // 100_000_00 * 100_000_00)
        res = FUND.take_fhlb(state, take, FUND.OVERNIGHT_FHLB_MONTHS)
        if isinstance(res, str):
            raise ActionError(res)
        return {"message": "FHLB advance drawn to cover the overnight hole."}
    if choice == "fed_funds":
        took = FUND.take_fed_funds(state, need,
                                   "Fed funds purchased (overnight, player)")
        leftover = need - took
        if leftover > 0:
            L.post(state["bank"]["ledger"], state["time"]["date"],
                   "DISCOUNT WINDOW borrowing (fed-funds limit reached)",
                   [["1000", leftover, 0], ["2120", 0, leftover]], tag="fund")
            state["bank"]["funding"]["discount_window_uses"] += 1
            return {"message": "Counterparties would only take $%s overnight. "
                               "The remaining $%s went to the discount window."
                               % (f"{took // 100:,}", f"{leftover // 100:,}")}
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
    ("deposits.market_offsets_bp.", None, int, -300, 300),
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
    ("loans.credit_box.enabled", None, (True, False), None, None),
    ("loans.credit_box.max_hold", None, int, 100_000_00, 50_000_000_00),
    ("loans.credit_box.participate_over", None, (True, False), None, None),
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
    ("policies.stop_on_quarter", None, (True, False), None, None),
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
            if isinstance(value, float) and not math.isfinite(value):
                raise ActionError("not a valid number")
            value = int(value)
            if value < lo or value > hi:
                raise ActionError("value out of range [%s, %s]" % (lo, hi))
        elif typ is float:
            if not isinstance(value, (int, float)):
                raise ActionError("numeric value required")
            if isinstance(value, float) and not math.isfinite(value):
                raise ActionError("not a valid number")
            value = float(value)
            if value < lo or value > hi:
                raise ActionError("value out of range [%s, %s]" % (lo, hi))
        # apply
        if path.startswith("loans.credit_box."):
            loans.credit_box(state)
        parts = path.split(".")
        if path.startswith("deposits.market_offsets_bp."):
            if len(parts) != 4:
                raise ActionError("town offset path is deposits.market_offsets_bp.<market>.<product>")
            mid, prod = parts[2], parts[3]
            if mid not in state["regions"]:
                raise ActionError("unknown market")
            if prod not in deposits.PRODUCTS:
                raise ActionError("unknown product")
            book = state["bank"]["deposits"].setdefault("market_offsets_bp", {})
            town = book.setdefault(mid, {})
            town[prod] = value
            return {"path": path, "value": value}
        target = state["bank"] if parts[0] != "regulation" else state
        node = target
        for part in parts[:-1]:
            node = node[part]
        # marketing for unknown market: only allow existing regions
        if path.startswith("ops.marketing."):
            if parts[-1] not in state["regions"]:
                raise ActionError("unknown market")
        node[parts[-1]] = value
        if path == "fraud.threshold":
            state["bank"]["fraud"]["false_positive_drag"] = round(
                max(0.0, (value - 1) * 0.006), 4)
        return {"path": path, "value": value}
    raise ActionError("unknown or protected policy path: %s" % path)
