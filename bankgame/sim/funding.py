"""Wholesale funding and capital actions.

Funding stack: core deposits (deposits.py), brokered CDs, FHLB advances,
fed funds purchased, discount window, subordinated debt. Overnight
borrowing: redeem your own fed-funds-sold first; then, depending on
`overnight_policy` (`ask` or `auto`), either stop the clock or cover
with FHLB / fed funds purchased / the discount window (which
regulators notice).

Capital: common raises, preferred issuance, dividends, buybacks.
"""

from . import ledger as L
from .economy import yield_at

# Overnight "Draw FHLB" is a short advance, not a 30-day roll that
# comes due on the same morning as next month's originations.
OVERNIGHT_FHLB_MONTHS = 3

# Market capacity: a $20M courthouse bank cannot place $1T of paper.
# Multiples are of today's book, so a real raise still fits ($5M on ~$2.5M TBV).
MAX_COMMON_RAISE_MULT = 3.0          # single common issue vs tangible book
MAX_PREFERRED_VS_CET1 = 1.0          # preferred outstanding vs CET1
MAX_SUBDEBT_VS_CET1 = 1.0            # subdebt outstanding vs CET1
MAX_BROKERED_VS_CORE = 0.30          # brokered outstanding vs core deposits
OVERNIGHT_WAIT_DAYS = 21
OVERDRAFT_PENALTY_BP = 0.015         # fed funds + 150bp on a negative vault


def new_funding():
    return {
        "fhlb": [],          # [{id, amount, rate, months_left}]
        "brokered": [],      # [{id, amount, rate, months_left}]
        "subdebt": [],       # [{id, amount, rate, months_left}]
        "next_id": 1,
        "discount_window_uses": 0,
        "ff_purchased_rate": 0.0,
        "overnight_policy": "ask",   # ask | auto
    }


def ensure_cash(state, amount):
    """Make at least `amount` available in operating cash (1000), redeeming
    fed funds sold first. Returns the cash now available."""
    led = state["bank"]["ledger"]
    for acct, memo in (("1100", "Fed funds sold redeemed for settlement"),
                       ("1010", "Fed balances drawn for settlement")):
        cash = led["balances"]["1000"]
        if cash >= amount:
            break
        take = min(led["balances"][acct], amount - cash)
        if take > 0:
            L.post(led, state["time"]["date"], memo,
                   [["1000", take, 0], [acct, 0, take]], tag="fund")
    return led["balances"]["1000"]


def fhlb_capacity(state):
    """Borrowing capacity: haircut advance against mortgage/CRE collateral
    and unpledged securities."""
    bank = state["bank"]
    from .loans import portfolio_stats
    stats = portfolio_stats(state)
    coll = 0
    for prod, hc in (("mortgage", 0.75), ("cre", 0.55), ("heloc", 0.50), ("ag", 0.45)):
        if prod in stats:
            coll += int(stats[prod]["balance"] * hc)
    secs = sum(l["mv"] for l in bank["securities"]["lots"]) * 0.9
    coll += int(secs)
    used = sum(a["amount"] for a in bank["funding"]["fhlb"])
    return max(0, coll - used)


def take_fhlb(state, amount, term_months):
    bank = state["bank"]
    f = bank["funding"]
    if amount < 100_000_00:
        return "minimum advance $100,000"
    if amount > fhlb_capacity(state):
        return "exceeds FHLB collateral capacity ($%s available)" % \
            f"{fhlb_capacity(state) // 100:,}"
    rate = round(yield_at(state["economy"], max(0.25, term_months / 12.0)) + 0.0025, 5)
    f["fhlb"].append({"id": f["next_id"], "amount": amount, "rate": rate,
                      "months_left": term_months})
    f["next_id"] += 1
    L.post(bank["ledger"], state["time"]["date"],
           "FHLB advance drawn ($%s, %dm @ %.2f%%)" % (f"{amount // 100:,}",
               term_months, rate * 100),
           [["1000", amount, 0], ["2100", 0, amount]], tag="fund")
    return {"rate": rate}


def _core_deposits(state):
    led = state["bank"]["ledger"]
    return max(0, L.total_deposits(led) + led["balances"]["2050"])


def brokered_room(state):
    outstanding = sum(a["amount"] for a in state["bank"]["funding"]["brokered"])
    cap = int(_core_deposits(state) * MAX_BROKERED_VS_CORE)
    return max(0, cap - outstanding)


def issue_brokered(state, amount, term_months):
    bank = state["bank"]
    reg = state["regulation"]
    if reg["pca"] not in ("well", "adequate"):
        return "brokered deposits prohibited below adequately-capitalized"
    if reg["pca"] == "adequate":
        return "adequately-capitalized banks need an FDIC waiver for brokered deposits (not granted)"
    if amount < 250_000_00:
        return "minimum brokered issuance $250,000"
    room = brokered_room(state)
    if amount > room:
        return "brokered book would exceed 30%% of core deposits ($%s room)" % \
            f"{room // 100:,}"
    f = bank["funding"]
    rate = round(yield_at(state["economy"], max(0.25, term_months / 12.0)) + 0.0040, 5)
    f["brokered"].append({"id": f["next_id"], "amount": amount, "rate": rate,
                          "months_left": term_months})
    f["next_id"] += 1
    L.post(bank["ledger"], state["time"]["date"],
           "Brokered CDs issued ($%s, %dm @ %.2f%%)" % (f"{amount // 100:,}",
               term_months, rate * 100),
           [["1000", amount, 0], ["2050", 0, amount]], tag="fund")
    return {"rate": rate}


def _cet1(state):
    from .regulation import capital_ratios
    return max(1, capital_ratios(state)["cet1"])


def issue_subdebt(state, amount, term_years=10):
    bank = state["bank"]
    econ = state["economy"]
    if amount < 1_000_000_00:
        return "minimum subordinated debt issue $1,000,000"
    outstanding = sum(a["amount"] for a in bank["funding"]["subdebt"])
    room = max(0, int(_cet1(state) * MAX_SUBDEBT_VS_CET1) - outstanding)
    if amount > room:
        return "subordinated debt would exceed common equity ($%s room)" % \
            f"{room // 100:,}"
    cost = int(amount * 0.015)   # underwriting
    equity = L.total_equity(bank["ledger"])
    if cost >= max(1, equity):
        return "underwriting fee would wipe out equity"
    health_spread = 0.02 + state["regulation"]["camels"]["composite"] * 0.006 \
        + econ["credit_stress"] * 0.03
    rate = round(yield_at(econ, term_years) + health_spread, 5)
    f = bank["funding"]
    f["subdebt"].append({"id": f["next_id"], "amount": amount, "rate": rate,
                         "months_left": term_years * 12})
    f["next_id"] += 1
    L.post(bank["ledger"], state["time"]["date"],
           "Subordinated debt issued ($%s @ %.2f%%)" % (f"{amount // 100:,}", rate * 100),
           [["1000", amount - cost, 0], ["5170", cost, 0], ["2200", 0, amount]], tag="fund")
    return {"rate": rate}


def repay(state, kind, item_id):
    bank = state["bank"]
    f = bank["funding"]
    accts = {"fhlb": "2100", "brokered": "2050", "subdebt": "2200"}
    if kind not in accts:
        return "unknown funding kind"
    acct = accts[kind]
    for item in f[kind]:
        if item["id"] == item_id:
            if ensure_cash(state, item["amount"]) < item["amount"]:
                return "not enough cash to repay"
            L.post(bank["ledger"], state["time"]["date"],
                   "Early repayment of %s ($%s)" % (kind, f"{item['amount'] // 100:,}"),
                   [[acct, item["amount"], 0], ["1000", 0, item["amount"]]], tag="fund")
            f[kind].remove(item)
            return {}
    return "item not found"


def accrue_day(state, days):
    """Daily interest on all wholesale funding + overnight borrowings."""
    bank = state["bank"]
    f = bank["funding"]
    econ = state["economy"]
    date = state["time"]["date"]
    ledger = bank["ledger"]

    borrow_int = 0
    for a in f["fhlb"]:
        borrow_int += int(round(a["amount"] * a["rate"] * days / 365.0))
    ffp = -ledger["balances"]["2110"]
    if ffp > 0:
        borrow_int += int(round(ffp * (econ["fed_funds"] + 0.0020) * days / 365.0))
    dw = -ledger["balances"]["2120"]
    if dw > 0:
        borrow_int += int(round(dw * (econ["fed_funds"] + 0.0100) * days / 365.0))
    if borrow_int > 0:
        L.post(ledger, date, "Interest on borrowings accrual",
               [["5010", borrow_int, 0], ["2300", 0, borrow_int]], tag="int")

    brok_int = 0
    for b in f["brokered"]:
        brok_int += int(round(b["amount"] * b["rate"] * days / 365.0))
    if brok_int > 0:
        L.post(ledger, date, "Brokered deposit interest accrual",
               [["5000", brok_int, 0], ["2300", 0, brok_int]], tag="int")

    sub_int = 0
    for s in f["subdebt"]:
        sub_int += int(round(s["amount"] * s["rate"] * days / 365.0))
    if sub_int > 0:
        L.post(ledger, date, "Subordinated debt interest accrual",
               [["5020", sub_int, 0], ["2300", 0, sub_int]], tag="int")

    # Uncovered vault overdraft (ask-policy "wait") is not free money.
    vault = ledger["balances"]["1000"]
    if vault < 0:
        od = int(round((-vault) * (econ["fed_funds"] + OVERDRAFT_PENALTY_BP)
                       * days / 365.0))
        if od > 0:
            L.post(ledger, date, "Daylight overdraft interest (vault)",
                   [["5010", od, 0], ["2300", 0, od]], tag="int")

    # interest on cash held at the Fed (IOR on balances parked in 1010)
    ior_bal = ledger["balances"]["1010"] + ledger["balances"]["1100"]
    if ior_bal > 0:
        inc = int(round(ior_bal * max(0.0, econ["fed_funds"] - 0.0010) * days / 365.0))
        if inc > 0:
            L.post(ledger, date, "Interest on Fed balances / fed funds sold",
                   [["1400", inc, 0], ["4020", 0, inc]], tag="int")


def pay_accrued_monthly(state):
    """Settle accrued interest payable in cash."""
    bank = state["bank"]
    ap = -bank["ledger"]["balances"]["2300"]
    if ap > 0:
        ensure_cash(state, ap)
        L.post(bank["ledger"], state["time"]["date"], "Accrued interest paid",
               [["2300", ap, 0], ["1000", 0, ap]], tag="int")


def step_month(state, rng):
    """Maturities roll off; sweep excess cash to fed funds sold."""
    bank = state["bank"]
    f = bank["funding"]
    date = state["time"]["date"]
    events = []
    for kind, acct in (("fhlb", "2100"), ("brokered", "2050"), ("subdebt", "2200")):
        done = []
        for item in f[kind]:
            item["months_left"] -= 1
            if item["months_left"] <= 0:
                ensure_cash(state, item["amount"])
                L.post(bank["ledger"], date,
                       "%s matured ($%s)" % (kind.upper(), f"{item['amount'] // 100:,}"),
                       [[acct, item["amount"], 0], ["1000", 0, item["amount"]]], tag="fund")
                done.append(item)
        for item in done:
            f[kind].remove(item)
    return events


def manage_overnight(state):
    """Called daily AFTER all flows: cover negative cash with overnight
    borrowings; sweep big surpluses into fed funds sold.

    Policy `ask` (default): after using your own cash/FFS, any window
    draw is a blocking event. Policy `auto`: FHLB, then FF purchased,
    then window — every window use is still logged.
    """
    bank = state["bank"]
    ledger = bank["ledger"]
    date = state["time"]["date"]
    events = []
    policy = bank["funding"].get("overnight_policy", "ask")

    # first: repay overnight borrowings with any available cash
    cash = ledger["balances"]["1000"]
    for acct in ("2120", "2110"):    # repay discount window first
        owed = -ledger["balances"][acct]
        if owed > 0 and cash > 0:
            pay = min(owed, cash)
            L.post(ledger, date, "Overnight borrowing repaid",
                   [[acct, pay, 0], ["1000", 0, pay]], tag="fund")
            cash -= pay

    cash = ledger["balances"]["1000"]
    target_cash = _target_cash(state)
    # Own money first: vault, then fed-funds-sold, then Fed balances.
    # Do not ask the player to borrow while $800k is still sitting at the Fed.
    if cash < 0:
        ensure_cash(state, 0)
        cash = ledger["balances"]["1000"]
    if cash < 0:
        need = -cash
        used_window = 0
        used_fhlb = 0
        # FHLB / fed-funds purchased: auto covers; ask leaves the hole
        # for the player (window is never silent).
        if policy == "auto" and need >= 100_000_00:
            cap = fhlb_capacity(state)
            take = min(need, cap)
            take = (take // 10_000_00) * 10_000_00
            if take >= 100_000_00:
                res = take_fhlb(state, take, OVERNIGHT_FHLB_MONTHS)
                if not isinstance(res, str):
                    used_fhlb = take
                    need -= take
        if policy == "auto" and need > 0:
            take = take_fed_funds(state, need)
            need -= take
        if need > 0 and policy != "auto":
            already = any(e.get("type") == "overnight_shortfall"
                          for e in state["events"]["pending"])
            wait_until = bank["funding"].get("overnight_wait_until")
            last_need = int(bank["funding"].get("overnight_wait_need") or 0)
            waiting = bool(wait_until and date <= wait_until
                           and need <= int(last_need * 1.5) + 50_000_00)
            if not already and not waiting:
                events.append({
                    "type": "overnight_shortfall",
                    "blocking": True,
                    "need": need,
                    "title": "Overnight cash shortfall",
                    "text": ("We are short $%s overnight after using vault cash, "
                             "fed-funds-sold, and balances at the Fed. The clock "
                             "stops so you can choose: draw a 3-month FHLB advance, "
                             "borrow fed funds (capped by counterparties), use the "
                             "discount window, or wait — wait covers what the "
                             "fed-funds market will take, charges a penalty on any "
                             "leftover overdraft, shrinks originations, and will "
                             "not nag you every morning.\n\n"
                             "The window is not drawn until you pick it. Examiners "
                             "count every use."
                             % f"{need // 100:,}"),
                    "choices": ["fhlb", "fed_funds", "window", "wait"],
                })
        elif need > 0:
            # auto: last resort — books stay non-negative, every use is logged
            L.post(ledger, date, "DISCOUNT WINDOW borrowing",
                   [["1000", need, 0], ["2120", 0, need]], tag="fund")
            state["bank"]["funding"]["discount_window_uses"] += 1
            used_window = need
            events.append({
                "type": "liquidity",
                "blocking": False,
                "title": "Discount window used",
                "text": ("Auto overnight policy borrowed at the Fed's discount "
                         "window to cover a cash shortfall ($%s). Lifetime "
                         "window uses: %d."
                         % (f"{used_window // 100:,}",
                            state["bank"]["funding"]["discount_window_uses"]))})
    cash = ledger["balances"]["1000"]
    if cash >= 0:
        if cash < target_cash:
            ensure_cash(state, target_cash)
            cash = ledger["balances"]["1000"]
        surplus = cash - target_cash
        if surplus > 500_000_00:
            L.post(ledger, date, "Excess cash swept to fed funds sold",
                   [["1100", surplus, 0], ["1000", 0, surplus]], tag="fund")
    return events


def _target_cash(state):
    dep = L.total_deposits(state["bank"]["ledger"])
    return int(dep * 0.025) + 500_000_00


def _ff_purchase_limit(state):
    """Counterparties lend overnight only to banks they trust."""
    bank = state["bank"]
    assets = bank["cached_assets"]
    reg = state["regulation"]
    base = int(assets * 0.06)
    if reg["pca"] in ("under", "significant", "critical"):
        base = int(base * 0.15)
    elif reg["camels"]["composite"] >= 4:
        base = int(base * 0.4)
    return base


def take_fed_funds(state, amount, memo="Fed funds purchased (overnight)"):
    """Borrow overnight FF up to the counterparty limit. Returns amount taken."""
    if amount <= 0:
        return 0
    ledger = state["bank"]["ledger"]
    already = -ledger["balances"]["2110"]
    take = max(0, min(amount, _ff_purchase_limit(state) - already))
    if take <= 0:
        return 0
    L.post(ledger, state["time"]["date"], memo,
           [["1000", take, 0], ["2110", 0, take]], tag="fund")
    return take


# --------------------------------------------------------------- capital

def raise_common(state, amount):
    bank = state["bank"]
    reg = state["regulation"]
    if amount < 500_000_00:
        return "minimum raise $500,000"
    equity = L.total_equity(bank["ledger"])
    tbv = max(1, equity - bank["ledger"]["balances"]["1600"])
    cap = int(tbv * MAX_COMMON_RAISE_MULT)
    if amount > cap:
        return "investors will not take a raise above %.0fx tangible book ($%s cap)" % (
            MAX_COMMON_RAISE_MULT, f"{cap // 100:,}")
    # pricing: healthy banks raise near/above book; sick banks deeply dilutive
    health = 1.0
    if reg["camels"]["composite"] >= 4:
        health = 0.55
    elif reg["camels"]["composite"] == 3:
        health = 0.8
    if state["economy"]["credit_stress"] > 0.4:
        health *= 0.8
    # A raise that is large vs book clears at a worse price.
    size_hit = min(1.0, 0.55 + 0.45 * (tbv / max(1, amount)))
    price_to_book = max(0.3, min(2.2, 1.15 * health * (1.0 + bank.get("roe_ttm", 0.08)) * size_hit))
    shares_out = bank["shares"]
    px = max(1, int(tbv / shares_out * price_to_book))
    new_shares = amount // px
    fees = int(amount * 0.05)
    if fees >= max(1, equity):
        return "underwriting fee would wipe out equity"
    L.post(bank["ledger"], state["time"]["date"],
           "Common equity raised ($%s at %.2fx book)" % (f"{amount // 100:,}", price_to_book),
           [["1000", amount - fees, 0], ["5170", fees, 0], ["3000", 0, amount]], tag="cap")
    bank["shares"] += new_shares
    return {"shares_issued": new_shares, "price_to_book": round(price_to_book, 2)}


def issue_preferred(state, amount):
    bank = state["bank"]
    if amount < 1_000_000_00:
        return "minimum preferred issue $1,000,000"
    outstanding = -bank["ledger"]["balances"]["3050"]
    room = max(0, int(_cet1(state) * MAX_PREFERRED_VS_CET1) - outstanding)
    if amount > room:
        return "preferred would exceed common equity ($%s room)" % f"{room // 100:,}"
    fees = int(amount * 0.03)
    if fees >= max(1, L.total_equity(bank["ledger"])):
        return "underwriting fee would wipe out equity"
    econ = state["economy"]
    rate = round(yield_at(econ, 10) + 0.035, 5)
    bank["preferred_rate"] = rate
    L.post(bank["ledger"], state["time"]["date"],
           "Preferred stock issued ($%s @ %.2f%%)" % (f"{amount // 100:,}", rate * 100),
           [["1000", amount - fees, 0], ["5170", fees, 0], ["3050", 0, amount]], tag="cap")
    return {"rate": rate}


def buyback(state, amount):
    bank = state["bank"]
    reg = state["regulation"]
    if reg.get("dividend_ban", False):
        return "capital distributions are prohibited under your enforcement action"
    if reg["pca"] != "well":
        return "buybacks require well-capitalized status"
    cash = ensure_cash(state, amount)
    if amount > cash:
        return "not enough cash"
    equity = L.total_equity(bank["ledger"])
    tbv = max(1, equity - bank["ledger"]["balances"]["1600"])
    px = max(1, int(tbv / bank["shares"] * 1.1))
    shares = min(bank["shares"] // 5, amount // px)
    if shares <= 0:
        return "amount too small"
    spend = shares * px
    L.post(bank["ledger"], state["time"]["date"],
           "Share buyback (%s shares)" % f"{shares:,}",
           [["3000", spend, 0], ["1000", 0, spend]], tag="cap")
    bank["shares"] -= shares
    return {"shares_bought": shares, "price": px}


def pay_dividends(state):
    """Quarterly, per the payout policy."""
    bank = state["bank"]
    reg = state["regulation"]
    payout = bank["policies"]["dividend_payout"]   # 0..100 (% of trailing quarterly earnings)
    if payout <= 0:
        return 0
    if reg.get("dividend_ban", False) or reg["pca"] not in ("well", "adequate"):
        return 0
    earn = bank.get("last_quarter_net_income", 0)
    if earn <= 0:
        return 0
    div = int(earn * payout / 100)
    cash = bank["ledger"]["balances"]["1000"]
    div = min(div, max(0, cash - 1_000_000_00))
    if div <= 0:
        return 0
    L.post(bank["ledger"], state["time"]["date"],
           "Common dividend paid (%d%% payout)" % payout,
           [["3100", div, 0], ["1000", 0, div]], tag="cap")
    return div


def pay_preferred_dividends(state):
    bank = state["bank"]
    pref = -bank["ledger"]["balances"]["3050"]
    if pref <= 0:
        return 0
    rate = bank.get("preferred_rate", 0.07)
    div = int(pref * rate / 4)
    if bank["ledger"]["balances"]["1000"] < div:
        return 0
    L.post(bank["ledger"], state["time"]["date"], "Preferred dividend paid",
           [["3100", div, 0], ["1000", 0, div]], tag="cap")
    return div
