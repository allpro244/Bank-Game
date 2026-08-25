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


MIN_LIVING = 8
NEW_CHARTER_NAMES = [
    ("Rio Concho Bank", "relationship"),
    ("Sierra Blanca State Bank", "conservative"),
    ("Pecos Valley National", "relationship"),
    ("Red River Bancshares", "roll_up"),
    ("Cactus State Bank", "conservative"),
    ("Llano River Trust", "relationship"),
    ("High Plains Heritage Bank", "conservative"),
    ("Brazos Forks Bank", "aggressive_lender"),
]


def living_banks(comp):
    return [b for b in comp["banks"] if b.get("alive")]


def circling_rival(state, deal):
    """The living rival most likely to close `deal` if the player waits."""
    need = int((deal.get("assets") or 0) * 1.15)
    if need <= 0:
        return None
    mid = deal.get("market")
    cands = [b for b in living_banks(state["competitors"]) if b["assets"] >= need]
    if not cands:
        return None

    def score(b):
        s = 0.0
        if b.get("strategy") == "roll_up":
            s += 5.0
        if mid and mid in (b.get("markets") or []):
            s += 4.0
        s += min(5.0, b["assets"] / max(1, need))
        return s

    return max(cands, key=score)


def rival_takes_packet(state, deal, rival):
    """A generated private book joins a living rival. Scalars only."""
    take = int((deal.get("assets") or 0) * 0.90)
    if take <= 0 or not rival or not rival.get("alive"):
        return False
    w_a = max(1, rival["assets"])
    rival["assets"] += take
    mark = float(deal.get("credit_mark") or 0.05)
    rival["npa_ratio"] = round(min(0.12, (rival["npa_ratio"] * w_a
                                          + mark * 0.4 * take) / (w_a + take)), 5)
    rival["equity_ratio"] = round(
        min(0.16, (rival["equity_ratio"] * w_a + 0.075 * take) / (w_a + take)), 5)
    mid = deal.get("market")
    if mid and mid not in (rival.get("markets") or []):
        rival["markets"].append(mid)
    return True


def _size_growth_drag(assets_cents):
    """Money-center names slow toward GDP. Community names may still compound."""
    assets_b = max(0.01, assets_cents / 100 / 1_000_000_000)
    return 1.0 / (1.0 + assets_b / 8.0)


def _absorb_rival(winner, loser):
    """Rival–rival merger. Scalars only — no second ledger."""
    take = int(loser["assets"] * 0.85)
    w_a = max(1, winner["assets"])
    winner["assets"] += take
    winner["npa_ratio"] = round(
        (winner["npa_ratio"] * w_a + loser["npa_ratio"] * take) / (w_a + take), 5)
    winner["equity_ratio"] = round(
        min(0.16, (winner["equity_ratio"] * w_a + 0.07 * take) / (w_a + take)), 5)
    for m in loser.get("markets") or []:
        if m not in winner["markets"]:
            winner["markets"].append(m)
    loser["alive"] = False


def _spawn_charter(state, rng):
    """A new community bank in a town that has room."""
    comp = state["competitors"]
    used = {n for n, _s, _m in BANK_NAMES}
    used.update(b["name"] for b in comp["banks"])
    names = [(n, s) for n, s in NEW_CHARTER_NAMES if n not in used]
    if not names:
        return None
    name, strat = rng.choice(names)
    # Prefer towns with few living rivals.
    counts = {}
    for mid in state["regions"]:
        counts[mid] = sum(1 for b in living_banks(comp) if mid in b.get("markets", []))
    towns = sorted(counts, key=lambda m: (counts[m], m))[:4]
    if not towns:
        return None
    home = rng.choice(towns)
    nid = comp.get("next_id", len(comp["banks"]))
    bank = {
        "id": "cb%d" % nid, "name": name, "strategy": strat,
        "markets": [home],
        "assets": int(rng.uniform(25, 80) * 1_000_000 * 100),
        "equity_ratio": round(rng.uniform(0.09, 0.12), 4),
        "npa_ratio": round(rng.uniform(0.003, 0.010), 5),
        "roa": round(rng.uniform(0.008, 0.012), 5),
        "nim": round(rng.uniform(0.032, 0.040), 5),
        "efficiency": round(rng.uniform(0.58, 0.68), 4),
        "alive": True, "stress": 0.0, "months_weak": 0,
    }
    comp["banks"].append(bank)
    comp["next_id"] = nid + 1
    return bank


def step_month(state, rng):
    """Update rival balance sheets and health; emit failure/M&A events.

    Failures leave survivors. New charters fill emptied towns. Growth
    slows with size so Empire does not 9%/yr forever.
    """
    econ = state["economy"]
    comp = state["competitors"]
    events = []
    pending_fail = []
    for b in comp["banks"]:
        if not b["alive"]:
            continue
        p = STRAT_PARAMS[b["strategy"]]
        cycle = econ["output_gap"] * 0.001 + (0.004 if not econ["recession"] else -0.006)
        raw = p["growth"] * 0.003 + cycle + rng.normal(0, 0.002)
        growth = min(0.005, raw * _size_growth_drag(b["assets"]))
        b["assets"] = max(10_000_000_00, int(b["assets"] * (1 + growth)))
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

        fail_p = 0.0
        if b["equity_ratio"] < 0.02:
            fail_p = 0.08
        elif b["months_weak"] > 12:
            fail_p = 0.015 + econ["credit_stress"] * 0.04
        if rng.chance(fail_p):
            pending_fail.append(b)

    for b in pending_fail:
        if not b.get("alive"):
            continue
        living = living_banks(comp)
        if len(living) <= MIN_LIVING:
            # Recap in place — the industry does not mass-extinct.
            b["equity_ratio"] = max(0.07, b["equity_ratio"])
            b["months_weak"] = 0
            b["npa_ratio"] = min(b["npa_ratio"], 0.04)
            continue
        peers = [x for x in living if x["id"] != b["id"] and x["assets"] > b["assets"]]
        if peers and rng.chance(0.65):
            winner = max(peers, key=lambda x: x["assets"])
            _absorb_rival(winner, b)
            comp["failed_log"].append({"name": b["name"], "m": econ["months"],
                                       "how": "merged"})
            events.append({
                "type": "rival_merger", "blocking": False,
                "title": "%s buys %s" % (winner["name"], b["name"]),
                "text": ("%s absorbed %s. The map consolidated; it did not empty."
                         % (winner["name"], b["name"])),
            })
            continue
        b["alive"] = False
        comp["failed_log"].append({"name": b["name"], "m": econ["months"],
                                   "how": "failed"})
        franchise = _franchise(b, rng)
        events.append({
            "type": "fdic_auction", "blocking": True,
            "title": "BANK FAILURE: %s closed by regulators" % b["name"],
            "text": ("%s (assets ~$%dM — %.1f× your bank) has been closed and the "
                     "FDIC is running an assisted auction this weekend. Franchise: "
                     "about $%dM of deposits, $%dM of loans (to be taken at a %d%% "
                     "credit mark), and %d branches in %s. You may bid a deposit "
                     "premium; the FDIC weighs bids and cost to the fund. Rivals "
                     "will bid too. A franchise more than twice your size is refused."
                     )
                    % (b["name"], b["assets"] // 100 // 1_000_000,
                       b["assets"] / max(1, state["bank"].get("cached_assets") or 1),
                       franchise["deposits"] // 100 // 1_000_000,
                       franchise["loans"] // 100 // 1_000_000,
                       int(franchise["credit_mark"] * 100),
                       franchise["branches"],
                       ", ".join(state["regions"][m]["name"] for m in b["markets"]
                                 if m in state["regions"])),
            "franchise": franchise, "bank_name": b["name"],
            "choices": ["bid", "pass"],
        })

    living_n = len(living_banks(comp))
    if living_n < 12 and econ["months"] > 0 and econ["months"] % 18 == 0:
        if rng.chance(0.45):
            born = _spawn_charter(state, rng)
            if born:
                events.append({
                    "type": "new_charter", "blocking": False,
                    "title": "New charter: %s" % born["name"],
                    "text": ("%s opened in %s. The industry still issues charters."
                             % (born["name"],
                                state["regions"].get(born["markets"][0], {})
                                .get("name", born["markets"][0]))),
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


# ---------------------------------------------------------------------------
# Call-report books reconstructed from published rival scalars.
# Rivals are not live ledgers (depth over a fake second sim). The identity
# assets = liabilities + equity holds to the cent, and TTM P&L is solved so
# published ROA / NIM / efficiency print exactly. Mix is strategy-tilted and
# drawn from a named RNG derived from master seed + rival id — never the live
# competitor stream — so opening the books does not move the world.
# ---------------------------------------------------------------------------

STRAT_LABEL = {
    "rate_leader": "Rate leader",
    "relationship": "Relationship",
    "aggressive_lender": "Aggressive lender",
    "conservative": "Conservative",
    "roll_up": "Roll-up",
    "digital": "Digital",
}

_ASSET_MIX = {
    "aggressive_lender": {"cash": 0.05, "fed": 0.03, "ff": 0.01, "afs": 0.06,
                          "htm": 0.04, "loans": 0.77, "premises": 0.016, "other": 0.024},
    "conservative":      {"cash": 0.07, "fed": 0.05, "ff": 0.02, "afs": 0.12,
                          "htm": 0.16, "loans": 0.54, "premises": 0.016, "other": 0.024},
    "digital":           {"cash": 0.06, "fed": 0.06, "ff": 0.03, "afs": 0.14,
                          "htm": 0.04, "loans": 0.64, "premises": 0.006, "other": 0.024},
    "rate_leader":       {"cash": 0.06, "fed": 0.04, "ff": 0.02, "afs": 0.10,
                          "htm": 0.06, "loans": 0.68, "premises": 0.014, "other": 0.026},
    "relationship":      {"cash": 0.06, "fed": 0.04, "ff": 0.015, "afs": 0.09,
                          "htm": 0.08, "loans": 0.68, "premises": 0.018, "other": 0.027},
    "roll_up":           {"cash": 0.05, "fed": 0.03, "ff": 0.015, "afs": 0.08,
                          "htm": 0.07, "loans": 0.70, "premises": 0.020, "other": 0.035},
}

_DEP_SHARE = {
    "aggressive_lender": 0.84, "conservative": 0.90, "digital": 0.88,
    "rate_leader": 0.86, "relationship": 0.91, "roll_up": 0.83,
}

_DEP_MIX = {
    "aggressive_lender": {"checking": 0.18, "checking_int": 0.08, "savings": 0.14,
                          "money_market": 0.22, "time": 0.22, "brokered": 0.16},
    "conservative":      {"checking": 0.28, "checking_int": 0.12, "savings": 0.20,
                          "money_market": 0.18, "time": 0.20, "brokered": 0.02},
    "digital":           {"checking": 0.18, "checking_int": 0.08, "savings": 0.12,
                          "money_market": 0.32, "time": 0.18, "brokered": 0.12},
    "rate_leader":       {"checking": 0.16, "checking_int": 0.08, "savings": 0.12,
                          "money_market": 0.28, "time": 0.28, "brokered": 0.08},
    "relationship":      {"checking": 0.32, "checking_int": 0.14, "savings": 0.20,
                          "money_market": 0.16, "time": 0.16, "brokered": 0.02},
    "roll_up":           {"checking": 0.22, "checking_int": 0.10, "savings": 0.16,
                          "money_market": 0.22, "time": 0.20, "brokered": 0.10},
}

_UNINSURED = {
    "aggressive_lender": 0.28, "conservative": 0.16, "digital": 0.38,
    "rate_leader": 0.32, "relationship": 0.14, "roll_up": 0.26,
}

_FEE_OF_ASSETS = {
    "aggressive_lender": 0.0018, "conservative": 0.0024, "digital": 0.0045,
    "rate_leader": 0.0020, "relationship": 0.0032, "roll_up": 0.0028,
}

_KIND_LOANS = {
    "rural":         {"ag": 0.24, "ci": 0.12, "cre": 0.10, "mortgage": 0.20,
                      "auto": 0.12, "small_business": 0.14, "construction": 0.04,
                      "heloc": 0.03, "credit_card": 0.01, "sba": 0.00},
    "small_metro":   {"ag": 0.10, "ci": 0.16, "cre": 0.16, "mortgage": 0.24,
                      "auto": 0.12, "small_business": 0.12, "construction": 0.05,
                      "heloc": 0.03, "credit_card": 0.02, "sba": 0.00},
    "suburb":        {"ag": 0.02, "ci": 0.12, "cre": 0.18, "mortgage": 0.36,
                      "auto": 0.12, "small_business": 0.10, "construction": 0.05,
                      "heloc": 0.04, "credit_card": 0.01, "sba": 0.00},
    "metro":         {"ag": 0.01, "ci": 0.20, "cre": 0.22, "mortgage": 0.24,
                      "auto": 0.08, "small_business": 0.10, "construction": 0.07,
                      "heloc": 0.04, "credit_card": 0.03, "sba": 0.01},
    "money_center":  {"ag": 0.00, "ci": 0.28, "cre": 0.26, "mortgage": 0.16,
                      "auto": 0.03, "small_business": 0.08, "construction": 0.08,
                      "heloc": 0.04, "credit_card": 0.06, "sba": 0.01},
}

_OPEX_MIX = {
    "digital":           {"salaries": 0.42, "occupancy": 0.08, "tech": 0.28,
                          "marketing": 0.08, "fdic": 0.05, "other": 0.09},
    "conservative":      {"salaries": 0.52, "occupancy": 0.16, "tech": 0.10,
                          "marketing": 0.04, "fdic": 0.06, "other": 0.12},
    "aggressive_lender": {"salaries": 0.48, "occupancy": 0.12, "tech": 0.12,
                          "marketing": 0.08, "fdic": 0.07, "other": 0.13},
    "rate_leader":       {"salaries": 0.46, "occupancy": 0.12, "tech": 0.14,
                          "marketing": 0.10, "fdic": 0.06, "other": 0.12},
    "relationship":      {"salaries": 0.54, "occupancy": 0.15, "tech": 0.09,
                          "marketing": 0.05, "fdic": 0.05, "other": 0.12},
    "roll_up":           {"salaries": 0.47, "occupancy": 0.14, "tech": 0.12,
                          "marketing": 0.06, "fdic": 0.06, "other": 0.15},
}


def find_rival(state, bank_id):
    for b in (state.get("competitors") or {}).get("banks", []):
        if b.get("id") == bank_id:
            return b
    return None


def rival_posted_rates(state, bank):
    """What this rival posts: national/local base plus ITS stance only."""
    econ = state["economy"]
    markets = [m for m in bank.get("markets") or [] if m in state["regions"]]
    mid = markets[0] if markets else (state.get("meta") or {}).get("home", "caprock")
    dep = dict(national_deposit_rates(econ))
    loan = dict(national_loan_rates(econ))
    region = (state.get("regions") or {}).get(mid) or {}
    comp_factor = (region.get("competition", 1.0) - 1.0)
    dep_tilt = 0.0008 * comp_factor * 10
    loan_tilt = -0.0010 * comp_factor * 10
    p = STRAT_PARAMS.get(bank.get("strategy"), STRAT_PARAMS["relationship"])
    for k in dep:
        if k != "checking":
            dep[k] = round(max(0.0001, dep[k] + dep_tilt + p["dep"]), 5)
    for k in loan:
        loan[k] = round(max(0.005, loan[k] + loan_tilt + p["loan"]), 5)
    return {"deposit": dep, "loan": loan, "market_id": mid}


def _allocate(total, weights):
    """Integer-cent allocation that sums to total. Last-cent via remainders."""
    names = list(weights)
    if not names:
        return {}
    raw = [max(0.0, float(weights[n])) for n in names]
    s = sum(raw)
    if total == 0:
        return {n: 0 for n in names}
    if s <= 0:
        out = {n: 0 for n in names}
        out[names[-1]] = total
        return out
    exact = [total * w / s for w in raw]
    floors = [int(x) if x >= 0 else -int(-x) for x in exact]
    leftover = total - sum(floors)
    order = sorted(range(len(names)),
                   key=lambda i: (exact[i] - floors[i], -i), reverse=True)
    i = 0
    n = len(order)
    while leftover > 0:
        floors[order[i % n]] += 1
        leftover -= 1
        i += 1
    while leftover < 0:
        idx = order[i % n]
        floors[idx] -= 1
        leftover += 1
        i += 1
    return {names[i]: floors[i] for i in range(len(names))}


def _jitter_weights(base, rng, lo=0.92, hi=1.08):
    return {k: v * rng.uniform(lo, hi) for k, v in base.items()}


def _books_rng(state, bank_id):
    from . import rng as R
    seed = int((state.get("meta") or {}).get("seed") or 0)
    return R.Rng(R.seed_stream(seed, "rival_books:" + str(bank_id)))


def _loan_product_weights(state, bank, rng):
    regions = state.get("regions") or {}
    kinds = []
    for mid in bank.get("markets") or []:
        r = regions.get(mid)
        if r:
            kinds.append(r.get("kind") or "metro")
    if not kinds:
        kinds = ["rural"]
    acc = {}
    for kind in kinds:
        mix = _KIND_LOANS.get(kind, _KIND_LOANS["metro"])
        for k, v in mix.items():
            acc[k] = acc.get(k, 0.0) + v
    n = float(len(kinds))
    acc = {k: v / n for k, v in acc.items()}
    strat = bank.get("strategy")
    tilt = {k: 1.0 for k in acc}
    if strat == "aggressive_lender":
        for k in ("ci", "cre", "construction"):
            tilt[k] = 1.25
        tilt["mortgage"] = 0.85
    elif strat == "conservative":
        tilt["mortgage"] = 1.25
        tilt["ag"] = 1.10
        for k in ("construction", "credit_card"):
            tilt[k] = 0.70
    elif strat == "digital":
        for k in ("auto", "credit_card", "mortgage", "heloc"):
            tilt[k] = 1.20
        tilt["cre"] = 0.70
        tilt["ag"] = 0.40
    elif strat == "rate_leader":
        tilt["mortgage"] = 1.15
        tilt["auto"] = 1.10
    return _jitter_weights({k: acc[k] * tilt.get(k, 1.0) for k in acc}, rng, 0.94, 1.06)


def _est_branches(assets, strat, n_markets):
    assets_m = max(1.0, assets / 100.0 / 1_000_000.0)
    n_markets = max(1, n_markets)
    if strat == "digital":
        return max(1, int(round(n_markets * 0.5 + assets_m ** 0.35 / 6.0)))
    return max(n_markets, int(round((assets_m ** 0.5) / 2.8)))


def rival_books(state, bank_id):
    """Reconstruct a balancing call-report book for one rival. Read-only."""
    bank = find_rival(state, bank_id)
    if bank is None:
        return None
    rng = _books_rng(state, bank_id)
    strat = bank.get("strategy") or "relationship"
    assets = int(bank["assets"])
    if assets < 0:
        assets = 0
    eq_ratio = float(bank.get("equity_ratio") or 0.0)
    npa_ratio = float(bank.get("npa_ratio") or 0.0)
    roa = float(bank.get("roa") or 0.0)
    nim = float(bank.get("nim") or 0.0)
    efficiency = float(bank.get("efficiency") or 0.0)

    equity = int(round(assets * eq_ratio))
    equity = max(0, min(assets, equity))
    liab = assets - equity

    mix = _jitter_weights(_ASSET_MIX.get(strat, _ASSET_MIX["relationship"]), rng)
    buckets = _allocate(assets, mix)
    cash = buckets["cash"]
    fed = buckets["fed"]
    ff = buckets["ff"]
    afs = buckets["afs"]
    htm = buckets["htm"]
    loans_net = buckets["loans"]
    premises = buckets["premises"]
    other = buckets["other"]

    npa = int(round(assets * npa_ratio))
    npa = max(0, min(assets, npa))
    oreo = min(other, npa // 4)
    other = other - oreo
    npl = npa - oreo
    npl = max(0, min(loans_net, npl))
    allowance = int(round(max(loans_net * 0.008, npl * 0.85)))
    allowance = max(0, min(loans_net, allowance))
    loans_gross = loans_net + allowance

    loan_w = _loan_product_weights(state, bank, rng)
    loan_by_prod = _allocate(loans_gross, loan_w)

    dep_share = _DEP_SHARE.get(strat, 0.88) * rng.uniform(0.97, 1.03)
    dep_share = max(0.55, min(0.96, dep_share))
    deposits = int(round(liab * dep_share))
    deposits = max(0, min(liab, deposits))
    wholesale = liab - deposits
    dep_mix = _jitter_weights(_DEP_MIX.get(strat, _DEP_MIX["relationship"]), rng)
    dep_by = _allocate(deposits, dep_mix)
    fhlb = int(round(wholesale * rng.uniform(0.62, 0.82)))
    fhlb = max(0, min(wholesale, fhlb))
    other_liab = wholesale - fhlb

    aoci = int(round(afs * rng.uniform(-0.035, 0.018)))
    aoci = max(-equity // 5 if equity else 0, min(equity // 10 if equity else 0, aoci))
    leftover_eq = equity - aoci
    retained = int(round(leftover_eq * rng.uniform(0.48, 0.62)))
    retained = max(0, min(leftover_eq, retained)) if leftover_eq >= 0 else leftover_eq
    common = leftover_eq - retained

    uninsured_share = _UNINSURED.get(strat, 0.20) * rng.uniform(0.90, 1.10)
    uninsured_share = max(0.05, min(0.62, uninsured_share))
    uninsured = int(round(deposits * uninsured_share))

    nii = int(round(assets * nim))
    fee = int(round(assets * _FEE_OF_ASSETS.get(strat, 0.0025) * rng.uniform(0.90, 1.10)))
    fee = max(0, fee)
    opex = int(round((nii + fee) * efficiency)) if (nii + fee) else 0
    opex = max(0, opex)
    provision = int(round(npa * 0.11 + assets * 0.0009))
    provision = max(0, provision)

    ni = int(round(assets * roa))
    if ni <= 0:
        tax = 0
        pretax = ni
    else:
        pretax = int(round(ni / 0.79))
        if pretax < ni:
            pretax = ni
        tax = pretax - ni
    core = nii + fee - opex - provision
    sec_gl = pretax - core

    posted = rival_posted_rates(state, bank)
    dep_rates = posted["deposit"]
    loan_rates = posted["loan"]
    econ = state["economy"]
    ff_rate = float(econ.get("fed_funds") or 0.0)
    ie_checking = 0
    ie_now = int(round(dep_by["checking_int"] * dep_rates.get("checking_int", 0.0)))
    ie_sav = int(round(dep_by["savings"] * dep_rates.get("savings", 0.0)))
    ie_mm = int(round(dep_by["money_market"] * dep_rates.get("money_market", 0.0)))
    cd_rate = (dep_rates.get("cd_1y", 0.0) + dep_rates.get("cd_2y", 0.0)) / 2.0
    ie_time = int(round(dep_by["time"] * cd_rate))
    ie_brok = int(round(dep_by["brokered"] * (dep_rates.get("cd_1y", 0.0) + 0.004)))
    ie_dep = ie_checking + ie_now + ie_sav + ie_mm + ie_time + ie_brok
    ie_wh = int(round(wholesale * (ff_rate + 0.004)))
    ie = ie_dep + ie_wh
    max_ii = int(round(assets * 0.12))
    if nii + ie > max_ii:
        ie = max(0, max_ii - nii)
        # keep the deposit/wholesale split if we had to cap
        if ie_dep + ie_wh > 0:
            ie_dep = int(round(ie * ie_dep / (ie_dep + ie_wh)))
            ie_wh = ie - ie_dep
        else:
            ie_dep, ie_wh = ie, 0
    ii = nii + ie
    earn = loans_gross + afs + htm + fed + ff
    if earn <= 0:
        ii_loans, ii_sec, ii_other = ii, 0, 0
    else:
        ii_split = _allocate(ii, {
            "loans": loans_gross + 1,
            "sec": afs + htm + 1,
            "other": fed + ff + 1,
        })
        ii_loans, ii_sec, ii_other = ii_split["loans"], ii_split["sec"], ii_split["other"]

    opex_by = _allocate(opex, _OPEX_MIX.get(strat, _OPEX_MIX["relationship"]))
    fee_card = int(round(fee * (0.42 if strat == "digital" else 0.18)))
    fee_card = max(0, min(fee, fee_card))
    fee_svc = fee - fee_card

    rwa = int(round(0.0 * (cash + fed) + 0.20 * (afs + htm + ff)
                    + 1.00 * loans_net + 1.00 * oreo + 1.00 * premises
                    + 1.00 * other))
    rwa = max(1, rwa)
    cet1 = equity / rwa
    leverage = equity / assets if assets else 0.0
    ldr = (loans_gross / deposits) if deposits else 0.0
    liq = (cash + fed + ff + afs) / assets if assets else 0.0
    shown_eff = (opex / (nii + fee)) if (nii + fee) else 0.0

    regions = state.get("regions") or {}
    markets = []
    for mid in bank.get("markets") or []:
        r = regions.get(mid)
        markets.append({
            "id": mid,
            "name": r["name"] if r else mid,
            "kind": r["kind"] if r else "",
        })
    n_markets = max(1, len(markets))
    branches = _est_branches(assets, strat, n_markets)

    bs_assets = [
        ("Cash and due from banks", cash),
        ("Interest-bearing balances at Fed", fed),
        ("Fed funds sold", ff),
        ("Securities available-for-sale (fair value)", afs),
        ("Securities held-to-maturity (amortized cost)", htm),
        ("Loans, gross", loans_gross),
        ("  less: allowance for credit losses", -allowance),
        ("Loans, net", loans_net),
        ("Premises and equipment", premises),
        ("Other real estate owned", oreo),
        ("Other assets", other),
    ]
    bs_liab = [
        ("Noninterest-bearing demand deposits", dep_by["checking"]),
        ("Interest checking (NOW)", dep_by["checking_int"]),
        ("Savings deposits", dep_by["savings"]),
        ("Money market deposits", dep_by["money_market"]),
        ("Time deposits (CDs)", dep_by["time"]),
        ("Brokered deposits", dep_by["brokered"]),
        ("Total deposits", deposits),
        ("FHLB advances", fhlb),
        ("Other liabilities", other_liab),
    ]
    bs_eq = [
        ("Common stock and surplus", common),
        ("Retained earnings", retained),
        ("Accumulated other comprehensive income", aoci),
    ]

    income_lines = [
        ("Interest income", ii),
        ("Interest expense", -ie),
        ("NET INTEREST INCOME", nii),
        ("Provision for credit losses", -provision),
        ("Noninterest income", fee),
        ("Securities gains (losses)", sec_gl),
        ("Noninterest expense", -opex),
        ("PRETAX INCOME", pretax),
        ("Income tax", -tax),
        ("NET INCOME", ni),
    ]
    income_detail = [
        ("Interest income — loans", ii_loans),
        ("Interest income — securities", ii_sec),
        ("Interest income — other", ii_other),
        ("Interest expense — deposits", ie_dep),
        ("Interest expense — wholesale", ie_wh),
        ("Service charges on deposits", fee_svc),
        ("Card interchange", fee_card),
        ("Salaries and benefits", opex_by["salaries"]),
        ("Occupancy and equipment", opex_by["occupancy"]),
        ("Technology", opex_by["tech"]),
        ("Marketing", opex_by["marketing"]),
        ("FDIC assessment", opex_by["fdic"]),
        ("Other expense", opex_by["other"]),
    ]

    siblings = [{"id": b["id"], "name": b["name"], "alive": bool(b.get("alive", True))}
                for b in state["competitors"]["banks"]]

    return {
        "id": bank["id"],
        "name": bank["name"],
        "strategy": strat,
        "strategy_label": STRAT_LABEL.get(strat, strat.replace("_", " ")),
        "alive": bool(bank.get("alive", True)),
        "reconstructed": True,
        "markets": markets,
        "branches_est": branches,
        "posted_rates": posted,
        "published": {
            "assets": assets,
            "equity_ratio": eq_ratio,
            "npa_ratio": npa_ratio,
            "roa": roa,
            "nim": nim,
            "efficiency": efficiency,
        },
        "balance_sheet": {
            "assets": bs_assets,
            "liabilities": bs_liab,
            "equity": bs_eq,
            "total_assets": assets,
            "total_liabilities": liab,
            "total_equity": equity,
        },
        "income_ttm": {
            "period": ["trailing 12m"],
            "lines": income_lines,
            "detail": income_detail,
            "net_income": ni,
            "nii": nii,
            "opex": opex,
            "fee_income": fee,
        },
        "mix": {
            "loans": loan_by_prod,
            "deposits": dep_by,
        },
        "quality": {
            "npa": npa,
            "npl": npl,
            "oreo": oreo,
            "allowance": allowance,
        },
        "ratios": {
            "equity_ratio": (equity / assets) if assets else 0.0,
            "npa_ratio": (npa / assets) if assets else 0.0,
            "roa": (ni / assets) if assets else 0.0,
            "nim": (nii / assets) if assets else 0.0,
            "efficiency": shown_eff,
            "cet1": cet1,
            "leverage": leverage,
            "ldr": ldr,
            "uninsured": uninsured_share,
            "uninsured_dollars": uninsured,
            "liquidity": liq,
            "loan_yield": (ii_loans / loans_gross) if loans_gross else 0.0,
            "cost_of_deposits": (ie_dep / deposits) if deposits else 0.0,
        },
        "siblings": siblings,
        "note": (
            "Reconstructed from this bank's published call-report figures "
            "(assets, capital, NPA, ROA, NIM, efficiency) and its strategy. "
            "Assets equal liabilities plus equity to the cent. Rivals are not "
            "a live general ledger — opening these books does not move the world."
        ),
    }
