"""Investment securities and interest-rate hedging.

Buy Treasuries, agencies, MBS, munis and corporates at market yields off
the live curve. Classify each lot available-for-sale (marked to market
through AOCI daily -- your book equity breathes with rates) or
held-to-maturity (carried at cost, but the unrealized loss is still
there, still reported, and still very real if a deposit run ever forces
you to sell -- selling ANY HTM taints the whole HTM book and forces a
full mark. Ask Silicon Valley Bank how that goes).

Hedges: pay-fixed swaps and rate caps settle monthly against fed funds.
"""

from . import ledger as L
from .economy import yield_at

TYPES = ["treasury", "agency", "mbs", "muni", "corporate"]

SPREAD = {"treasury": 0.0, "agency": 0.0012, "mbs": 0.0050,
          "muni": -0.0035, "corporate": None}   # corporate uses live IG spread

RISK_WEIGHT = {"treasury": 0.0, "agency": 0.20, "mbs": 0.20,
               "muni": 0.20, "corporate": 1.00}


def new_book():
    return {"lots": [], "next_id": 1, "htm_tainted": False, "hedges": [],
            "next_hedge_id": 1}


def type_yield(econ, sec_type, tenor_years):
    base = yield_at(econ, tenor_years)
    if sec_type == "corporate":
        return round(base + econ["ig_spread"], 5)
    return round(max(0.0005, base + SPREAD[sec_type]), 5)


def buy(state, sec_type, tenor_years, par, classification):
    """Buy at par with coupon = current market yield. Returns lot or error str."""
    bank = state["bank"]
    if sec_type not in TYPES:
        return "unknown security type"
    if classification not in ("AFS", "HTM"):
        return "classification must be AFS or HTM"
    if par < 100_000_00:
        return "minimum purchase is $100,000"
    from .funding import ensure_cash
    cash = ensure_cash(state, par)
    if par > cash:
        return "not enough cash (have $%s)" % f"{cash // 100:,}"
    econ = state["economy"]
    coupon = type_yield(econ, sec_type, tenor_years)
    book = bank["securities"]
    if classification == "HTM" and book["htm_tainted"]:
        classification = "AFS"   # tainted: no more HTM
    lot = {"id": book["next_id"], "type": sec_type, "tenor0": tenor_years,
           "maturity_m": int(tenor_years * 12), "coupon": coupon, "par": par,
           "book": par, "cls": classification, "mv": par,
           "bought": state["time"]["date"]}
    book["next_id"] += 1
    book["lots"].append(lot)
    acct = "1200" if classification == "AFS" else "1210"
    L.post(bank["ledger"], state["time"]["date"],
           "Bought %s %s %.2f%% ($%s) [%s]" % (sec_type.upper(),
               _tenor_label(tenor_years), coupon * 100, f"{par // 100:,}", classification),
           [[acct, par, 0], ["1000", 0, par]], tag="sec")
    return lot


def _tenor_label(t):
    return ("%dm" % int(t * 12)) if t < 1 else ("%gy" % t)


def price_lot(econ, lot):
    """Fair value from the live curve (annual-compounding closed form)."""
    n = max(0.05, lot["maturity_m"] / 12.0)
    if lot["type"] == "corporate":
        y = yield_at(econ, n) + econ["ig_spread"]
    else:
        y = max(0.0005, yield_at(econ, n) + SPREAD[lot["type"]])
    if lot["type"] == "mbs":
        # extension risk: when rates rise, effective life extends
        incentive = lot["coupon"] - y
        n = max(0.1, n * (1.0 - max(-0.35, min(0.35, incentive * 6))))
        y = max(0.0005, yield_at(econ, n) + SPREAD["mbs"])
    c = lot["coupon"]
    if y < 0.0001:
        y = 0.0001
    pf = (c / y) * (1 - (1 + y) ** -n) + (1 + y) ** -n
    return int(lot["par"] * pf)


def duration_lot(lot, econ):
    n = max(0.05, lot["maturity_m"] / 12.0)
    y = max(0.001, yield_at(econ, n))
    c = max(0.0005, lot["coupon"])
    try:
        mac = (1 + y) / y - ((1 + y) + n * (c - y)) / (c * ((1 + y) ** n - 1) + y)
    except ZeroDivisionError:
        mac = n
    return max(0.05, min(n, mac / (1 + y)))


def revalue(state):
    """Mark AFS to market through AOCI; track HTM unrealized off-ledger."""
    bank = state["bank"]
    econ = state["economy"]
    book = bank["securities"]
    afs_mv = 0
    afs_carry = bank["ledger"]["balances"]["1200"]
    htm_unreal = 0
    for lot in book["lots"]:
        lot["mv"] = price_lot(econ, lot)
        if lot["cls"] == "AFS":
            afs_mv += lot["mv"]
        else:
            htm_unreal += lot["mv"] - lot["book"]
    delta = afs_mv - afs_carry
    if delta != 0:
        if delta > 0:
            lines = [["1200", delta, 0], ["3200", 0, delta]]
        else:
            lines = [["3200", -delta, 0], ["1200", 0, -delta]]
        L.post(bank["ledger"], state["time"]["date"], "AFS mark-to-market (AOCI)",
               lines, tag="sec")
    bank["cached_htm_unrealized"] = htm_unreal
    return afs_mv, htm_unreal


def accrue_day(state, days):
    bank = state["bank"]
    accr = 0
    for lot in bank["securities"]["lots"]:
        accr += int(round(lot["par"] * lot["coupon"] * days / 365.0))
    if accr > 0:
        L.post(bank["ledger"], state["time"]["date"], "Securities interest accrual",
               [["1400", accr, 0], ["4010", 0, accr]], tag="int")
    return accr


def step_month(state, rng):
    """Age lots, receive MBS paydowns and maturities."""
    bank = state["bank"]
    econ = state["economy"]
    book = bank["securities"]
    date = state["time"]["date"]
    cash_in = 0
    by_acct = {"1200": 0, "1210": 0}
    matured = []
    for lot in book["lots"]:
        lot["maturity_m"] -= 1
        if lot["type"] == "mbs" and lot["par"] > 0:
            cur = type_yield(econ, "mbs", max(0.5, lot["maturity_m"] / 12.0))
            incentive = lot["coupon"] - cur
            cpr = max(0.03, min(0.55, 0.08 + incentive * 4.0))
            pay = int(lot["par"] * cpr / 12)
            pay = min(pay, lot["par"])
            if pay > 0:
                lot["par"] -= pay
                lot["book"] = min(lot["book"], lot["par"])
                cash_in += pay
                by_acct["1200" if lot["cls"] == "AFS" else "1210"] += pay
        if lot["maturity_m"] <= 0 or lot["par"] <= 0:
            if lot["par"] > 0:
                cash_in += lot["par"]
                by_acct["1200" if lot["cls"] == "AFS" else "1210"] += lot["par"]
            matured.append(lot)
    for lot in matured:
        book["lots"].remove(lot)
    if cash_in > 0:
        lines = [["1000", cash_in, 0]]
        for acct, amt in by_acct.items():
            if amt > 0:
                lines.append([acct, 0, amt])
        L.post(bank["ledger"], date, "Securities principal received", lines, tag="sec")
    revalue(state)
    _settle_hedges(state)
    collect_interest(state)


def collect_interest(state):
    # securities + loan accrued interest both flow through 1400; loans module
    # collects its own, so here we sweep whatever remains monthly.
    pass


def sell(state, lot_id, par_amount=None):
    """Sell a lot (or part). Returns dict or error string."""
    bank = state["bank"]
    book = bank["securities"]
    lot = None
    for l in book["lots"]:
        if l["id"] == lot_id:
            lot = l
            break
    if lot is None:
        return "lot not found"
    econ = state["economy"]
    lot["mv"] = price_lot(econ, lot)
    frac = 1.0
    if par_amount and 0 < par_amount < lot["par"]:
        frac = par_amount / lot["par"]
    sell_par = int(lot["par"] * frac)
    sell_mv = int(lot["mv"] * frac)
    sell_book = int(lot["book"] * frac)
    date = state["time"]["date"]
    gl = sell_mv - sell_book
    events = []
    if lot["cls"] == "AFS":
        # carrying value equals mv (post-revalue); reclassify AOCI to earnings
        lines = [["1000", sell_mv, 0], ["1200", 0, sell_mv]]
        L.post(bank["ledger"], date, "Sold AFS %s ($%s par)" % (lot["type"].upper(),
               f"{sell_par // 100:,}"), lines, tag="sec")
        if gl > 0:
            L.post(bank["ledger"], date, "Realized gain on AFS sale",
                   [["3200", gl, 0], ["4140", 0, gl]], tag="sec")
        elif gl < 0:
            L.post(bank["ledger"], date, "Realized loss on AFS sale",
                   [["5180", -gl, 0], ["3200", 0, -gl]], tag="sec")
    else:
        lines = [["1000", sell_mv, 0], ["1210", 0, sell_book]]
        if gl > 0:
            lines.append(["4140", 0, gl])
        elif gl < 0:
            lines.append(["5180", -gl, 0])
        L.post(bank["ledger"], date, "SOLD HTM %s ($%s par) — HTM BOOK TAINTED"
               % (lot["type"].upper(), f"{sell_par // 100:,}"), lines, tag="sec")
        # Shrink/remove THIS lot before taint, or _taint_htm posts 1210 again.
        lot["par"] -= sell_par
        lot["book"] -= sell_book
        lot["mv"] -= sell_mv
        if lot["par"] <= 0:
            book["lots"].remove(lot)
        if not book["htm_tainted"]:
            book["htm_tainted"] = True
            events.append(_taint_htm(state))
        revalue(state)
        return {"proceeds": sell_mv, "gain_loss": gl, "events": events}
    lot["par"] -= sell_par
    lot["book"] -= sell_book
    lot["mv"] -= sell_mv
    if lot["par"] <= 0:
        book["lots"].remove(lot)
    revalue(state)
    return {"proceeds": sell_mv, "gain_loss": gl, "events": events}


def _taint_htm(state):
    """Selling from HTM forces the entire HTM book to AFS at fair value."""
    bank = state["bank"]
    book = bank["securities"]
    econ = state["economy"]
    date = state["time"]["date"]
    total_book = 0
    total_mv = 0
    for lot in book["lots"]:
        if lot["cls"] == "HTM":
            lot["mv"] = price_lot(econ, lot)
            total_book += lot["book"]
            total_mv += lot["mv"]
            lot["cls"] = "AFS"
            lot["book"] = lot["mv"]  # new basis at transfer? keep simple: basis = mv
    if total_book > 0:
        # move carrying from 1210 to 1200 at fair value; difference hits AOCI
        diff = total_mv - total_book
        lines = [["1200", total_mv, 0], ["1210", 0, total_book]]
        if diff < 0:
            lines.append(["3200", -diff, 0])
        elif diff > 0:
            lines.append(["3200", 0, diff])
        L.post(bank["ledger"], date, "HTM portfolio tainted: transferred to AFS at fair value",
               lines, tag="sec")
    return {"type": "htm_taint", "blocking": True,
            "title": "HTM PORTFOLIO TAINTED",
            "text": ("You sold held-to-maturity securities. Accounting rules now force "
                     "the ENTIRE HTM book to be reclassified to available-for-sale at "
                     "fair value. Unrealized loss of $%s just hit your AOCI and your "
                     "tangible equity. Examiners will notice.")
                    % f"{max(0, total_book - total_mv) // 100:,}"}


# ------------------------------------------------------------------ hedges

def add_hedge(state, kind, notional, tenor_years):
    bank = state["bank"]
    econ = state["economy"]
    book = bank["securities"]
    if kind not in ("pay_fixed_swap", "rate_cap"):
        return "unknown hedge kind"
    if notional < 1_000_000_00:
        return "minimum notional is $1,000,000"
    fixed = yield_at(econ, tenor_years) + 0.0010
    h = {"id": book["next_hedge_id"], "kind": kind, "notional": notional,
         "months_left": int(tenor_years * 12)}
    book["next_hedge_id"] += 1
    if kind == "pay_fixed_swap":
        h["fixed"] = round(fixed, 5)
    else:
        h["strike"] = round(econ["fed_funds"] + 0.01, 5)
        premium = int(notional * 0.002 * tenor_years)
        from .funding import ensure_cash
        cash = ensure_cash(state, premium)
        if premium > cash:
            return "not enough cash for cap premium ($%s)" % f"{premium // 100:,}"
        L.post(bank["ledger"], state["time"]["date"], "Rate cap premium paid",
               [["5170", premium, 0], ["1000", 0, premium]], tag="hedge")
        h["premium"] = premium
    book["hedges"].append(h)
    return h


def _settle_hedges(state):
    bank = state["bank"]
    econ = state["economy"]
    book = bank["securities"]
    date = state["time"]["date"]
    done = []
    for h in book["hedges"]:
        h["months_left"] -= 1
        if h["kind"] == "pay_fixed_swap":
            net = int(h["notional"] * (econ["fed_funds"] - h["fixed"]) / 12.0)
            if net > 0:
                L.post(bank["ledger"], date, "Swap settlement received (pay-fixed)",
                       [["1000", net, 0], ["4150", 0, net]], tag="hedge")
            elif net < 0:
                L.post(bank["ledger"], date, "Swap settlement paid (pay-fixed)",
                       [["5010", -net, 0], ["1000", 0, -net]], tag="hedge")
        else:
            pay = int(h["notional"] * max(0.0, econ["fed_funds"] - h["strike"]) / 12.0)
            if pay > 0:
                L.post(bank["ledger"], date, "Rate cap payout received",
                       [["1000", pay, 0], ["4150", 0, pay]], tag="hedge")
        if h["months_left"] <= 0:
            done.append(h)
    for h in done:
        book["hedges"].remove(h)


def summary(state):
    bank = state["bank"]
    econ = state["economy"]
    lots = bank["securities"]["lots"]
    afs_mv = sum(l["mv"] for l in lots if l["cls"] == "AFS")
    afs_book = sum(l["book"] for l in lots if l["cls"] == "AFS")
    htm_book = sum(l["book"] for l in lots if l["cls"] == "HTM")
    htm_mv = sum(l["mv"] for l in lots if l["cls"] == "HTM")
    tot_par = sum(l["par"] for l in lots)
    dur = 0.0
    if tot_par > 0:
        dur = sum(duration_lot(l, econ) * l["par"] for l in lots) / tot_par
    return {"afs_mv": afs_mv, "afs_book": afs_book, "htm_book": htm_book,
            "htm_mv": htm_mv, "htm_unrealized": htm_mv - htm_book,
            "duration": round(dur, 2), "count": len(lots),
            "tainted": bank["securities"]["htm_tainted"],
            "yield": round(sum(l["par"] * l["coupon"] for l in lots) / tot_par, 5) if tot_par else 0}


# Effective durations (years). Core deposits use decay, not overnight
# beta — otherwise a community book looks like SVB on day one.
_DEP_DUR = {
    "checking": 2.40, "checking_int": 2.10, "savings": 2.80,
    "money_market": 0.70, "cd_3m": 0.22, "cd_1y": 0.85,
    "cd_2y": 1.60, "cd_5y": 3.10,
}


def _loan_mod_duration(product):
    from .loans import FLOATING, TERM_M
    if product == "credit_card":
        return 0.15
    if product in FLOATING:
        return 0.30
    if product == "mortgage":
        return 6.2
    term_y = TERM_M.get(product, 60) / 12.0
    return max(0.15, min(8.0, term_y * 0.48))


def eve_report(state):
    """Duration-gap EVE under parallel ±100/200/300 bp shocks.

    Display only — does not grade the exam or post to the books.
    Owner sentence: what a 2% rate jump does to tangible book.
    """
    from . import deposits as DEP
    from . import loans as LN
    from . import ledger as LL

    bank = state["bank"]
    econ = state["economy"]
    ledger = bank["ledger"]

    rsa = 0
    rsa_dd = 0.0
    cash = (ledger["balances"]["1000"] + ledger["balances"]["1010"]
            + ledger["balances"]["1100"])
    rsa += cash
    rsa_dd += cash * 0.02
    for lot in bank["securities"]["lots"]:
        rsa += lot["mv"]
        rsa_dd += lot["mv"] * duration_lot(lot, econ)
    for prod, d in LN.portfolio_stats(state).items():
        rsa += d["balance"]
        rsa_dd += d["balance"] * _loan_mod_duration(prod)

    rsl = 0
    rsl_dd = 0.0
    tots = DEP.totals(bank["deposits"])
    for p in DEP.PRODUCTS:
        rsl += tots[p]
        rsl_dd += tots[p] * _DEP_DUR[p]
    fund = bank["funding"]
    for adv in fund.get("fhlb") or []:
        d = max(0.05, adv["months_left"] / 12.0 * 0.85)
        rsl += adv["amount"]
        rsl_dd += adv["amount"] * d
    for adv in fund.get("brokered") or []:
        d = max(0.05, adv["months_left"] / 12.0 * 0.70)
        rsl += adv["amount"]
        rsl_dd += adv["amount"] * d
    for adv in fund.get("subdebt") or []:
        d = max(0.10, adv["months_left"] / 12.0 * 0.55)
        rsl += adv["amount"]
        rsl_dd += adv["amount"] * d
    overnight = max(0, -ledger["balances"]["2110"]) + max(0, -ledger["balances"]["2120"])
    rsl += overnight
    rsl_dd += overnight * 0.02

    da = rsa_dd / rsa if rsa else 0.0
    dl = rsl_dd / rsl if rsl else 0.0
    gap_dollars = rsa_dd - rsl_dd
    tbv = LL.total_equity(ledger) - ledger["balances"]["1600"]
    hedges = bank["securities"].get("hedges") or []

    shocks = []
    for bp in (-300, -200, -100, 100, 200, 300):
        dy = bp / 10000.0
        delta = int(round(-dy * gap_dollars))
        for h in hedges:
            years = max(0.1, h["months_left"] / 12.0)
            if h["kind"] == "pay_fixed_swap":
                delta += int(round(h["notional"] * years * 0.80 * dy))
            elif dy > 0:
                delta += int(round(h["notional"] * years * 0.28 * dy))
        shocks.append({
            "bp": bp,
            "delta_eve": delta,
            "pct_tbv": round(delta / max(1, tbv), 4),
        })
    plus200 = next(s for s in shocks if s["bp"] == 200)
    move = plus200["delta_eve"]
    sign = "rises" if move > 0 else "falls" if move < 0 else "is unchanged"
    owner = ("If rates jump 2%%, tangible book %s about $%s (%.1f%%)."
             % (sign, f"{abs(move) // 100:,}", abs(plus200["pct_tbv"]) * 100))
    return {
        "asset_duration": round(da, 2),
        "liability_duration": round(dl, 2),
        "duration_gap": round(da - dl * (rsl / max(1, rsa)), 2),
        "rsa": rsa, "rsl": rsl, "tbv": tbv,
        "owner": owner,
        "shocks": shocks,
    }
