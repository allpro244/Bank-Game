"""Crises: deposit runs, contagion, cyberattacks.

Bank runs are BEHAVIOR, not an event card. Every day a rumor level
evolves from your actual condition: thin capital, big unrealized bond
losses relative to equity, a heavy uninsured deposit share, public
enforcement actions, recent losses, and failures of other banks around
you. Social media speed rises over the decades, so a 2030s run moves
much faster than a 1990s one. If projected outflows exceed every dollar
of liquidity you can raise (cash, fed funds, FHLB, discount window
collateral, securities), the FDIC arrives before the weekend.
"""

from . import ledger as L
from .deposits import PRODUCTS, ACCT, uninsured_share

# products ranked by how fast that money runs
RUN_SPEED = {"money_market": 1.6, "cd_3m": 0.9, "checking": 0.35, "checking_int": 0.40,
             "savings": 0.7, "cd_1y": 0.45, "cd_2y": 0.3, "cd_5y": 0.2}


def new_crisis():
    return {"rumor": 0.0, "run_active": False, "run_days": 0,
            "total_run_outflow": 0, "worst_day": 0, "history": []}


def run_cause(state):
    """Why rumor is up, in one owner sentence."""
    bank = state["bank"]
    reg = state["regulation"]
    ratios = reg.get("last_ratios") or {}
    te = ratios.get("tang_equity_ratio")
    bits = []
    if te is not None and te < 0.08:
        bits.append("thin capital")
    equity = max(1, L.total_equity(bank["ledger"]))
    unreal = min(0, bank.get("cached_htm_unrealized", 0)) + \
        min(0, -bank["ledger"]["balances"]["3200"])
    if unreal < 0 and (-unreal / equity) > 0.08:
        bits.append("bond marks vs equity")
    if uninsured_share(state) > 0.28:
        bits.append("a lot of uninsured money")
    if reg["camels"]["composite"] >= 4:
        bits.append("a 4-rated exam")
    recent = sum(1 for f in state["competitors"]["failed_log"]
                 if state["economy"]["months"] - f["m"] <= 3)
    if recent:
        bits.append("other banks just failed")
    if not bits:
        bits.append("word on the street")
    return bits[0] if len(bits) == 1 else (bits[0] + " and " + bits[1])


def run_status(state):
    """Payload for Deposits / Desk / franchise. No mutation."""
    cr = state.get("crisis") or {}
    rumor = float(cr.get("rumor") or 0.0)
    active = bool(cr.get("run_active"))
    return {
        "run": active,
        "watch": (not active) and rumor > 0.25,
        "rumor": round(rumor, 3),
        "run_days": int(cr.get("run_days") or 0),
        "outflow": int(cr.get("total_run_outflow") or 0),
        "cause": run_cause(state) if (active or rumor > 0.25) else "",
    }


def social_media_factor(state):
    years = state["economy"]["months"] / 12.0
    size = state["bank"]["cached_assets"] / 100 / 1_000_000_000  # $B
    return 1.0 + min(2.5, years * 0.04) + min(1.0, size / 100.0)


def condition_weakness(state):
    """0 (fortress) .. 1 (dead bank walking) from real fundamentals."""
    bank = state["bank"]
    reg = state["regulation"]
    ratios = reg.get("last_ratios")
    w = 0.0
    if ratios:
        te = ratios["tang_equity_ratio"]
        if te < 0.08:
            w += min(0.45, (0.08 - te) * 9)
    # unrealized securities losses vs equity (the SVB tell)
    equity = max(1, L.total_equity(bank["ledger"]))
    unreal = min(0, bank.get("cached_htm_unrealized", 0)) + \
        min(0, -bank["ledger"]["balances"]["3200"])
    if unreal < 0:
        w += min(0.35, -unreal / equity * 0.5)
    from .loans import npl_balance
    npa = npl_balance(bank["loans"]) / max(1, bank["cached_assets"])
    w += min(0.25, npa * 6)
    if bank.get("last_quarter_net_income", 0) < 0:
        w += 0.08
    if reg["camels"]["composite"] >= 4:
        w += 0.15
    if any("Consent order" in o for o in reg["orders"]):
        w += 0.08
    return min(1.0, w)


def step_day(state, rng):
    bank = state["bank"]
    cr = state["crisis"]
    econ = state["economy"]
    events = []
    weak = condition_weakness(state)
    unins = uninsured_share(state)
    social = social_media_factor(state)

    # ambient fear: rises when other banks fail nearby
    recent_failures = sum(1 for f in state["competitors"]["failed_log"]
                          if econ["months"] - f["m"] <= 3)
    ambient = econ["credit_stress"] * 0.10 + recent_failures * 0.05

    spark = 0.0
    if weak > 0.25:
        spark = (weak - 0.25) * 0.02 * social
    if rng.chance(min(0.4, spark + ambient * 0.02)):
        cr["rumor"] = min(1.0, cr["rumor"] + rng.uniform(0.05, 0.2) * social * 0.5)
    # rumor feeds on weakness, dies on strength
    drift = (weak * 0.6 + ambient - 0.30) * 0.08
    cr["rumor"] = max(0.0, min(1.0, cr["rumor"] + drift * cr["rumor"] +
                               (0.0 if cr["rumor"] > 0 else 0.0)))
    if weak < 0.15:
        cr["rumor"] *= 0.90

    was_active = cr["run_active"]
    cr["run_active"] = cr["rumor"] > 0.45
    if cr["run_active"] and not was_active:
        events.append({"type": "run_start", "blocking": True,
                       "title": "DEPOSITORS ARE PULLING MONEY",
                       "text": ("Lines at the branches, wire queues online. Word is out that the "
                                "bank is in trouble (weakness %.0f%%, uninsured deposits %.0f%%). "
                                "You need liquidity and you need confidence: raise deposit "
                                "rates, draw FHLB early, sell securities, raise capital — or "
                                "watch it spiral. Social media speed multiplier: %.1fx.")
                               % (weak * 100, unins * 100, social)})
    if not cr["run_active"]:
        if was_active and cr["run_days"] > 0:
            events.append({"type": "run_end", "blocking": False,
                           "title": "The run has subsided",
                           "text": "Outflows have normalized after %d days and $%s withdrawn."
                                   % (cr["run_days"], f"{cr['total_run_outflow'] // 100:,}")})
            cr["run_days"] = 0
            cr["total_run_outflow"] = 0
        return events

    # ---- an active run: compute today's outflow ----
    cr["run_days"] += 1
    deposits_total = L.total_deposits(bank["ledger"])
    # rate defense: paying up slows the walk
    edge = bank["deposits"]["offsets_bp"].get("money_market", 0) / 10000.0
    defense = max(0.5, 1.0 - max(0.0, edge) * 30)
    frac = (cr["rumor"] - 0.40) * 0.035 * social * (0.4 + unins * 1.6) * defense
    frac = max(0.001, min(0.18, frac))
    outflow = int(deposits_total * frac)
    if outflow <= 0:
        return events

    capacity = _total_liquidity_capacity(state)
    if outflow > capacity:
        # cannot meet withdrawals: illiquidity failure
        state["regulation"]["seized"] = True
        events.append({"type": "seizure", "blocking": True,
                       "title": "FAILED: UNABLE TO MEET WITHDRAWALS",
                       "text": ("Today's withdrawal demand ($%s) exceeded every source of "
                                "liquidity the bank could raise ($%s). The regulators closed "
                                "the bank mid-run. After %d days of the run, $%s had already "
                                "left. This is how it ends when uninsured money loses faith.")
                               % (f"{outflow // 100:,}", f"{capacity // 100:,}",
                                  cr["run_days"], f"{cr['total_run_outflow'] // 100:,}")})
        return events

    _execute_outflow(state, outflow)
    cr["total_run_outflow"] += outflow
    cr["worst_day"] = max(cr["worst_day"], outflow)
    if cr["run_days"] in (2, 5, 9):
        events.append({"type": "run_update", "blocking": cr["run_days"] == 5,
                       "title": "Run day %d: $%s withdrawn today" % (cr["run_days"],
                                                                     f"{outflow // 100:,}"),
                       "text": ("Cumulative outflow $%s (%.1f%% of deposits). Liquidity "
                                "remaining: $%s. Rumor level %.0f%%.")
                               % (f"{cr['total_run_outflow'] // 100:,}",
                                  100.0 * cr["total_run_outflow"] / max(1, deposits_total),
                                  f"{_total_liquidity_capacity(state) // 100:,}",
                                  cr["rumor"] * 100)})
    return events


def _execute_outflow(state, outflow):
    """Withdrawals leave hot products first; ledger + pools stay in sync."""
    bank = state["bank"]
    deps = bank["deposits"]
    weights = []
    for mid in sorted(deps["pools"].keys()):
        for p in PRODUCTS:
            bal = deps["pools"][mid][p]["balance"]
            if bal > 0:
                weights.append((mid, p, bal * RUN_SPEED[p]))
    total_w = sum(w for _, _, w in weights)
    if total_w <= 0:
        return
    by_acct = {}
    taken_total = 0
    for mid, p, w in weights:
        pool = deps["pools"][mid][p]
        take = min(pool["balance"], int(outflow * w / total_w))
        pool["balance"] -= take
        by_acct[ACCT[p]] = by_acct.get(ACCT[p], 0) + take
        taken_total += take
    if taken_total > 0:
        lines = [[acct, amt, 0] for acct, amt in sorted(by_acct.items()) if amt > 0]
        lines.append(["1000", 0, taken_total])
        L.post(bank["ledger"], state["time"]["date"], "DEPOSIT RUN outflows",
               lines, tag="run")


def _total_liquidity_capacity(state):
    bank = state["bank"]
    ledger = bank["ledger"]
    from .funding import fhlb_capacity
    cash = max(0, ledger["balances"]["1000"]) + ledger["balances"]["1100"] \
        + ledger["balances"]["1010"]
    afs = sum(l["mv"] for l in bank["securities"]["lots"] if l["cls"] == "AFS")
    htm = int(sum(l["mv"] for l in bank["securities"]["lots"] if l["cls"] == "HTM") * 0.95)
    fhlb = fhlb_capacity(state)
    dw_collateral = int(0.25 * sum(p["balance"] for p in bank["loans"]["pools"]))
    return cash + afs + htm + fhlb + dw_collateral


def step_month(state, rng):
    """Rare cyberattack; scales with weak cyber spend."""
    bank = state["bank"]
    ops = bank["ops"]
    events = []
    assets = max(bank["cached_assets"], 20_000_000_00)
    need = assets * 0.00001
    protection = min(1.5, ops["cyber_spend"] / max(1, need))
    p = max(0.0005, 0.006 - 0.0035 * protection)
    if rng.chance(p):
        loss = int(assets * rng.uniform(0.001, 0.004)) + 100_000_00
        L.post(bank["ledger"], state["time"]["date"], "CYBERATTACK: response and remediation",
               [["5160", loss, 0], ["1000", 0, loss]], tag="fraud")
        state["crisis"]["rumor"] = min(1.0, state["crisis"]["rumor"] + 0.2)
        for mid in ops["brand"]:
            ops["brand"][mid] = max(0.0, ops["brand"][mid] - 6.0)
        events.append({"type": "cyber", "blocking": True,
                       "title": "CYBERATTACK — $%s in damage" % f"{loss // 100:,}",
                       "text": ("Attackers got into the network. Systems were down, some "
                                "customer data was accessed, and remediation plus notification "
                                "cost $%s. The story is in the paper, and nervous depositors "
                                "read the paper. Cybersecurity spend is a dial on the "
                                "Operations tab; it was at $%s/month.")
                               % (f"{loss // 100:,}", f"{ops['cyber_spend'] // 100:,}")})
    return events
