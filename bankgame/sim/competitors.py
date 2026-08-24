"""Competitor banks, credit unions, fintechs and money funds.

Rivals set deposit and loan pricing according to strategy archetypes, feel
the same macro cycle you do, gain or lose deposits against you, and can
fail in downturns (creating FDIC-assisted acquisition opportunities) or
offer to sell / try to buy you.

Also computes "prevailing market rates": what the competition is paying on
deposits and charging on loans, which drives your share of every market.
"""

STRATEGIES = ["rate_leader", "relationship", "aggressive_lender",
              "conservative", "roll_up", "digital"]

BANK_NAMES = [
    ("First Cattlemen's Bank", "relationship", ["caprock", "plainview", "lubbock"]),
    ("Permian Basin State Bank", "aggressive_lender", ["verhalen", "midland"]),
    ("Llano Estacado National", "conservative", ["plainview", "lubbock"]),
    ("Trinity Bancshares", "roll_up", ["dallas", "fortworth", "rockwall"]),
    ("Gulf Coast Commerce Bank", "aggressive_lender", ["houston", "sanantonio"]),
    ("Hill Country Savings", "relationship", ["austin", "sanantonio"]),
    ("Lone Star Interstate Bank", "rate_leader", ["dallas", "houston", "austin", "fortworth"]),
    ("Metroplex National Bank", "conservative", ["dallas", "rockwall", "fortworth"]),
    ("Comanche Peak Bank & Trust", "relationship", ["fortworth", "caprock"]),
    ("Meridian Digital Bank", "digital", ["dallas", "austin", "houston", "nyc"]),
    ("Empire Clearing Bank", "rate_leader", ["nyc"]),
    ("Knickerbocker Trust Co.", "conservative", ["nyc"]),
]

# deposit rate betas vs fed funds by product (competitive national norms)
DEPOSIT_BETAS = {
    "checking_int": (0.08, 0.0),     # (beta, floor add)
    "savings": (0.25, 0.0010),
    "money_market": (0.55, 0.0015),
    "cd_3m": (0.80, 0.0020),
    "cd_1y": (0.88, 0.0030),
    "cd_2y": (0.85, 0.0040),
    "cd_5y": (0.80, 0.0060),
}

# loan pricing: product -> (benchmark tenor years or "ff", spread)
LOAN_BENCH = {
    "auto": (2.0, 0.026),
    "mortgage": (10.0, 0.017),
    "heloc": ("ff", 0.031),
    "credit_card": ("ff", 0.135),
    "small_business": ("ff", 0.034),
    "ci": ("ff", 0.027),
    "cre": (5.0, 0.024),
    "construction": ("ff", 0.033),
    "ag": (5.0, 0.026),
    "sba": ("ff", 0.028),
}

STRAT_PARAMS = {
    # dep_stance: added to deposit rates; loan_stance: added to loan rates;
    # risk: loss sensitivity in busts; growth: organic growth tilt
    "rate_leader":       {"dep": +0.0035, "loan": -0.0030, "risk": 1.0, "growth": 1.4},
    "relationship":      {"dep": -0.0030, "loan": +0.0020, "risk": 0.8, "growth": 0.9},
    "aggressive_lender": {"dep": +0.0015, "loan": -0.0045, "risk": 1.9, "growth": 1.6},
    "conservative":      {"dep": -0.0015, "loan": +0.0035, "risk": 0.5, "growth": 0.7},
    "roll_up":           {"dep": 0.0,     "loan": 0.0,     "risk": 1.1, "growth": 1.2},
    "digital":           {"dep": +0.0060, "loan": -0.0015, "risk": 1.0, "growth": 1.8},
}


def new_competitors(rng):
    banks = []
    sizes = [95, 240, 130, 1900, 850, 320, 4200, 1100, 60, 700, 26000, 9000]
    for i, (name, strat, markets) in enumerate(BANK_NAMES):
        assets = sizes[i] * 1_000_000 * 100  # cents
        banks.append({
            "id": "cb%d" % i, "name": name, "strategy": strat, "markets": markets,
            "assets": assets, "equity_ratio": rng.uniform(0.085, 0.115),
            "npa_ratio": rng.uniform(0.003, 0.012),
            "roa": rng.uniform(0.008, 0.013), "nim": rng.uniform(0.032, 0.042),
            "efficiency": rng.uniform(0.55, 0.68),
            "alive": True, "stress": 0.0, "months_weak": 0,
        })
    return {"banks": banks, "failed_log": [], "next_id": len(banks)}


def national_deposit_rates(econ):
    ff = econ["fed_funds"]
    rates = {}
    for prod, (beta, add) in DEPOSIT_BETAS.items():
        r = ff * beta + add
        rates[prod] = round(max(0.0001, r), 5)
    rates["checking"] = 0.0
    return rates


def national_loan_rates(econ):
    from .economy import yield_at
    ff = econ["fed_funds"]
    stress_add = econ["credit_stress"] * 0.012
    rates = {}
    for prod, (bench, spread) in LOAN_BENCH.items():
        base = ff if bench == "ff" else yield_at(econ, bench)
        rates[prod] = round(max(0.005, base + spread + stress_add), 5)
    return rates


def market_rates(state, market_id):
    """Prevailing rates in one market, tilted by local competition and the
    stances of rivals present there."""
    econ = state["economy"]
    region = state["regions"][market_id]
    dep = dict(national_deposit_rates(econ))
    loan = dict(national_loan_rates(econ))
    comp_factor = (region["competition"] - 1.0)
    dep_tilt = 0.0008 * comp_factor * 10
    loan_tilt = -0.0010 * comp_factor * 10
    n = 0
    dstance = lstance = 0.0
    for b in state["competitors"]["banks"]:
        if b["alive"] and market_id in b["markets"]:
            p = STRAT_PARAMS[b["strategy"]]
            dstance += p["dep"]
            lstance += p["loan"]
            n += 1
    if n:
        dstance /= n
        lstance /= n
    for k in dep:
        if k != "checking":
            dep[k] = round(max(0.0001, dep[k] + dep_tilt + dstance), 5)
    for k in loan:
        loan[k] = round(max(0.005, loan[k] + loan_tilt + lstance), 5)
    return {"deposit": dep, "loan": loan}


def step_month(state, rng):
    """Update rival balance sheets and health; emit failure/M&A events."""
    econ = state["economy"]
    comp = state["competitors"]
    events = []
    for b in comp["banks"]:
        if not b["alive"]:
            continue
        p = STRAT_PARAMS[b["strategy"]]
        cycle = econ["output_gap"] * 0.001 + (0.004 if not econ["recession"] else -0.006)
        growth = (p["growth"] * 0.004 + cycle + rng.normal(0, 0.004))
        b["assets"] = max(10_000_000_00, int(b["assets"] * (1 + growth)))
        # credit losses scale with stress * risk appetite
        loss_rate = (0.0003 + econ["credit_stress"] * 0.0035 * p["risk"]
                     + max(0.0, rng.normal(0, 0.0006)))
        b["npa_ratio"] = round(max(0.001, min(0.15,
            b["npa_ratio"] * 0.92 + loss_rate * 2.2)), 5)
        monthly_earn = (b["roa"] / 12.0) - loss_rate
        b["equity_ratio"] = max(0.0, min(0.16, b["equity_ratio"] + monthly_earn
                                         - growth * b["equity_ratio"]))
        b["roa"] = round(max(-0.03, min(0.022,
            b["roa"] * 0.95 + 0.05 * (0.011 * (1.2 if p["risk"] > 1.2 else 1.0))
            - econ["credit_stress"] * 0.004 * p["risk"] + rng.normal(0, 0.0008))), 5)
        b["nim"] = round(max(0.015, min(0.055,
            b["nim"] + 0.02 * (0.036 - b["nim"]) + rng.normal(0, 0.0006))), 5)
        b["efficiency"] = round(max(0.38, min(0.95,
            b["efficiency"] + rng.normal(0, 0.006))), 4)
        b["stress"] = round(max(0.0, min(1.0,
            (0.06 - b["equity_ratio"]) * 12 + b["npa_ratio"] * 6
            + econ["credit_stress"] * 0.3)), 3)

        if b["equity_ratio"] < 0.045 or b["npa_ratio"] > 0.09:
            b["months_weak"] += 1
        else:
            b["months_weak"] = max(0, b["months_weak"] - 1)

        # failure
        fail_p = 0.0
        if b["equity_ratio"] < 0.02:
            fail_p = 0.5
        elif b["months_weak"] > 4:
            fail_p = 0.08 + econ["credit_stress"] * 0.2
        if rng.chance(fail_p):
            b["alive"] = False
            comp["failed_log"].append({"name": b["name"], "m": econ["months"]})
            franchise = _franchise(b, rng)
            events.append({
                "type": "fdic_auction", "blocking": True,
                "title": "BANK FAILURE: %s closed by regulators" % b["name"],
                "text": ("%s (assets ~$%dM) has been closed and the FDIC is running "
                         "an assisted auction this weekend. Franchise: about $%dM of "
                         "deposits, $%dM of loans (to be taken at a %d%% credit mark), "
                         "and %d branches in %s. You may bid a deposit premium; the "
                         "FDIC weighs bids and cost to the fund. Rivals will bid too.")
                        % (b["name"], b["assets"] // 100 // 1_000_000,
                           franchise["deposits"] // 100 // 1_000_000,
                           franchise["loans"] // 100 // 1_000_000,
                           int(franchise["credit_mark"] * 100),
                           franchise["branches"],
                           ", ".join(state["regions"][m]["name"] for m in b["markets"]
                                     if m in state["regions"])),
                "franchise": franchise, "bank_name": b["name"],
                "choices": ["bid", "pass"],
            })
    return events


def _franchise(b, rng):
    deposits = int(b["assets"] * rng.uniform(0.72, 0.85))
    loans = int(b["assets"] * rng.uniform(0.55, 0.72))
    return {
        "deposits": deposits, "loans": loans,
        "credit_mark": round(rng.uniform(0.05, 0.16), 3),
        "branches": max(1, int((b["assets"] / 100 / 1_000_000) ** 0.5 / 3)),
        "markets": list(b["markets"]),
        "rival_bid_bp": rng.randint(-50, 220),  # rivals' premium in bp of deposits; negative = discount bids only
    }


def peer_group(state):
    """Rivals in the player's size class for the peer report."""
    me = state["bank"]["cached_assets"]
    peers = []
    for b in state["competitors"]["banks"]:
        if not b["alive"]:
            continue
        if 0.2 * me <= b["assets"] <= 5 * me or abs(b["assets"] - me) < 500_000_000_00:
            peers.append(b)
    return sorted(peers, key=lambda x: x["assets"])
