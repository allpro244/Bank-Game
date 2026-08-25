"""Regional economies.

Each market has its own population, income, industry mix, deposit pool and
loan demand. Industry weights determine sensitivity to macro variables:
oil towns boom and bust with crude, ag counties with cattle/cotton and
drought, metro markets with the national cycle and (for Austin) tech/equity
conditions. Local one-off shocks (plant closure, drought, hurricane, new
highway, data center) hit individual markets.
"""

# industry mix keys: oil, ag, mfg, services, tech, port
MARKET_DEFS = [
    {"id": "caprock", "name": "Caprock City, TX", "kind": "rural",
     "pop": 14200, "income": 41000, "growth": 0.2,
     "mix": {"oil": 0.20, "ag": 0.35, "mfg": 0.05, "services": 0.40},
     "competition": 0.9, "note": "Home. Courthouse square, cotton gins, one stoplight that matters."},
    {"id": "verhalen", "name": "Verhalen, TX (Permian)", "kind": "rural",
     "pop": 9100, "income": 47000, "growth": 0.4,
     "mix": {"oil": 0.65, "ag": 0.10, "services": 0.25},
     "competition": 0.8, "note": "Permian Basin oilpatch town. Lives and dies with the rig count."},
    {"id": "plainview", "name": "Plainview, TX", "kind": "rural",
     "pop": 22000, "income": 39000, "growth": 0.0,
     "mix": {"ag": 0.50, "mfg": 0.15, "services": 0.35},
     "competition": 1.0, "note": "High Plains cattle and cotton country."},
    {"id": "midland", "name": "Midland-Odessa, TX", "kind": "small_metro",
     "pop": 310000, "income": 58000, "growth": 0.9,
     "mix": {"oil": 0.50, "services": 0.45, "mfg": 0.05},
     "competition": 1.3, "note": "The Permian's capital. Energy money, energy volatility."},
    {"id": "lubbock", "name": "Lubbock, TX", "kind": "small_metro",
     "pop": 260000, "income": 46000, "growth": 0.8,
     "mix": {"ag": 0.25, "services": 0.60, "mfg": 0.10, "tech": 0.05},
     "competition": 1.2, "note": "Hub city of the South Plains. University, hospitals, ag finance."},
    {"id": "rockwall", "name": "Rockwall County, TX", "kind": "suburb",
     "pop": 95000, "income": 74000, "growth": 2.6,
     "mix": {"services": 0.75, "mfg": 0.15, "tech": 0.10},
     "competition": 1.4, "note": "Fast-growing DFW suburb. Rooftops and retail follow."},
    {"id": "fortworth", "name": "Fort Worth, TX", "kind": "metro",
     "pop": 2100000, "income": 62000, "growth": 1.8,
     "mix": {"services": 0.55, "mfg": 0.25, "tech": 0.10, "oil": 0.10},
     "competition": 1.6, "note": "Big-city banking with a cowtown handshake."},
    {"id": "dallas", "name": "Dallas, TX", "kind": "metro",
     "pop": 4800000, "income": 68000, "growth": 1.9,
     "mix": {"services": 0.65, "tech": 0.20, "mfg": 0.15},
     "competition": 1.8, "note": "Regional money center. Every bank in Texas wants this."},
    {"id": "houston", "name": "Houston, TX", "kind": "metro",
     "pop": 6800000, "income": 64000, "growth": 1.7,
     "mix": {"oil": 0.30, "port": 0.15, "services": 0.45, "mfg": 0.10},
     "competition": 1.8, "note": "Energy capital. Hurricane alley."},
    {"id": "austin", "name": "Austin, TX", "kind": "metro",
     "pop": 2200000, "income": 78000, "growth": 2.8,
     "mix": {"tech": 0.45, "services": 0.50, "mfg": 0.05},
     "competition": 1.9, "note": "Tech boomtown. Priced accordingly."},
    {"id": "sanantonio", "name": "San Antonio, TX", "kind": "metro",
     "pop": 2500000, "income": 55000, "growth": 1.6,
     "mix": {"services": 0.75, "mfg": 0.15, "tech": 0.10},
     "competition": 1.5, "note": "Military, medicine, tourism. Steady."},
    {"id": "nyc", "name": "New York, NY", "kind": "money_center",
     "pop": 19500000, "income": 92000, "growth": 0.8,
     "mix": {"services": 0.80, "tech": 0.20},
     "competition": 2.6, "note": "The big leagues. Bottomless deposits, merciless competition."},
    # Weight-class unlocks. The towns exist from day one; you cannot
    # open there until the book is in that class. Not a 50-state pack.
    {"id": "desmoines", "name": "Des Moines, IA", "kind": "small_metro",
     "pop": 280000, "income": 54000, "growth": 0.7,
     "mix": {"ag": 0.40, "services": 0.50, "mfg": 0.10},
     "competition": 1.2, "unlock_assets": 200_000_000_00,
     "note": "Iowa insurance and corn. An ag book without the Permian."},
    {"id": "neworleans", "name": "New Orleans, LA", "kind": "metro",
     "pop": 1270000, "income": 52000, "growth": 0.6,
     "mix": {"port": 0.35, "services": 0.50, "mfg": 0.15},
     "competition": 1.5, "unlock_assets": 400_000_000_00,
     "note": "River and gulf. Hurricanes and trade, not Houston energy."},
    {"id": "charlotte", "name": "Charlotte, NC", "kind": "metro",
     "pop": 2700000, "income": 61000, "growth": 1.5,
     "mix": {"services": 0.70, "mfg": 0.15, "tech": 0.15},
     "competition": 1.7, "unlock_assets": 1_000_000_000_00,
     "note": "Carolinas super-regional town. Banking is the local industry."},
    {"id": "chicago", "name": "Chicago, IL", "kind": "money_center",
     "pop": 9500000, "income": 72000, "growth": 0.7,
     "mix": {"services": 0.70, "mfg": 0.20, "tech": 0.10},
     "competition": 2.3, "unlock_assets": 2_000_000_000_00,
     "note": "Midwest clearing. Another money center, not a bigger Dallas."},
    {"id": "losangeles", "name": "Los Angeles, CA", "kind": "money_center",
     "pop": 13200000, "income": 70000, "growth": 0.9,
     "mix": {"services": 0.55, "port": 0.15, "tech": 0.20, "mfg": 0.10},
     "competition": 2.4, "unlock_assets": 5_000_000_000_00,
     "note": "West-coast deposits. Merciless, coastal, a different oil."},
]

# Deposits per capita by market kind (dollars) -- scaled by income
DEP_PER_CAP = {"rural": 14000, "small_metro": 17000, "suburb": 19000,
               "metro": 24000, "money_center": 55000}

SHOCK_DEFS = [
    {"id": "drought", "name": "Severe drought", "needs": "ag", "months": [14, 30],
     "sev": [0.25, 0.6], "text": "Extended drought is scorching pastures and dryland cotton. Ag borrowers will hurt."},
    {"id": "plant_close", "name": "Major employer closes", "needs": "mfg", "months": [10, 24],
     "sev": [0.2, 0.5], "text": "The area's largest manufacturer is shutting its plant. Layoffs hit deposits and credit."},
    {"id": "hurricane", "name": "Hurricane landfall", "needs": "port", "months": [4, 9],
     "sev": [0.3, 0.7], "text": "A major hurricane has made landfall. Expect insurance chaos, damaged collateral, and draw-downs."},
    {"id": "highway", "name": "New interstate spur", "needs": None, "months": [24, 48],
     "sev": [-0.5, -0.2], "text": "A new highway spur is routing traffic and development through town. Growth tailwind."},
    {"id": "datacenter", "name": "Data center campus", "needs": None, "months": [18, 40],
     "sev": [-0.6, -0.25], "text": "A hyperscaler is building a data center campus. Construction jobs now, tax base later."},
    {"id": "military_expand", "name": "Base expansion", "needs": None, "months": [18, 36],
     "sev": [-0.4, -0.2], "text": "The nearby military installation is expanding. Steady payroll inflow."},
]


def new_regions(rng):
    regions = {}
    for d in MARKET_DEFS:
        pool = int(d["pop"] * DEP_PER_CAP[d["kind"]] * (d["income"] / 55000.0)) * 100
        regions[d["id"]] = {
            "id": d["id"], "name": d["name"], "kind": d["kind"],
            "pop": d["pop"], "income": d["income"], "base_growth": d["growth"],
            "mix": d["mix"], "competition": d["competition"], "note": d["note"],
            "deposit_pool": pool,          # cents, total deposits held in this market
            "loan_demand_mult": 1.0,       # local demand multiplier
            "local_activity": 1.0,         # 1.0 = normal; boom > 1, bust < 1
            "employment_shock": 0.0,       # adds to local unemployment
            "housing_index": 100.0,
            "shock": None,                 # active local shock
            "unlock_assets": int(d.get("unlock_assets") or 0),
            "history": [],
        }
    return regions


def market_unlocked(state, market_id):
    """Weight-class towns exist on the map; you cannot enter until the book fits."""
    region = state["regions"].get(market_id)
    if region is None:
        return False
    need = int(region.get("unlock_assets") or 0)
    if need <= 0:
        return True
    assets = max(0, state["bank"].get("cached_assets") or 0)
    return assets >= need


def market_condition(region, econ):
    """Composite local condition multiplier used by loan demand / credit."""
    return region["local_activity"]


def step_month(regions, econ, rng):
    events = []
    oil_norm = econ["oil"] / 55.0
    cattle_norm = econ["cattle"] / 110.0
    cotton_norm = econ["cotton"] / 0.72
    natgas_norm = econ["natgas"] / 3.6
    ag_norm = 0.6 * cattle_norm + 0.4 * cotton_norm
    tech_norm = econ["equity_index"] / max(200.0, econ.get("equity_peak", econ["equity_index"]))

    for rid in sorted(regions.keys()):
        r = regions[rid]
        mix = r["mix"]
        # local activity: national gap plus industry-weighted commodity effects
        industry = (mix.get("oil", 0) * (0.55 * (oil_norm - 1) + 0.15 * (natgas_norm - 1))
                    + mix.get("ag", 0) * 0.45 * (ag_norm - 1)
                    + mix.get("tech", 0) * 0.5 * (tech_norm - 1)
                    + mix.get("port", 0) * 0.2 * (oil_norm - 1))
        national = econ["output_gap"] * 0.035
        shock_drag = 0.0
        if r["shock"]:
            s = r["shock"]
            shock_drag = -s["sev"] * 0.25
            s["months_left"] -= 1
            if s["months_left"] <= 0:
                events.append({"type": "region_shock_end", "region": rid,
                               "title": "%s: %s has ended" % (r["name"], s["name"])})
                r["shock"] = None
        target = 1.0 + national + industry + shock_drag
        r["local_activity"] = round(max(0.45, min(1.8,
            r["local_activity"] + 0.25 * (target - r["local_activity"]) + rng.normal(0, 0.01))), 4)

        # population and income drift
        g = (r["base_growth"] + 1.5 * (r["local_activity"] - 1.0)) / 100.0 / 12.0
        r["pop"] = max(500, int(r["pop"] * (1 + g)))
        r["income"] = max(20000, int(r["income"] * (1 + (econ["inflation"] * 0.8 / 100.0
                                                         + 1.2 * (r["local_activity"] - 1) / 100.0) / 12.0)))

        # deposit pool grows with pop, income, activity
        pool_growth = g + econ["inflation"] / 100.0 / 12.0 * 0.9 + (r["local_activity"] - 1) * 0.004
        r["deposit_pool"] = max(10000_00, int(r["deposit_pool"] * (1 + pool_growth)))

        # local unemployment shock and housing
        r["employment_shock"] = round(max(-1.5, min(6.0,
            r["employment_shock"] * 0.85 - (r["local_activity"] - 1.0) * 1.2)), 2)
        local_apprec = econ["housing_apprec"] + 4.0 * (r["local_activity"] - 1.0)
        r["housing_index"] = round(max(25.0, r["housing_index"] * (1 + local_apprec / 100.0 / 12.0)), 2)

        r["loan_demand_mult"] = round(max(0.3, min(2.2,
            0.5 + 0.5 * r["local_activity"] + 0.15 * max(0, econ["output_gap"]) * 0.1)), 3)

        # spawn local shocks
        if r["shock"] is None and rng.chance(0.006):
            candidates = [s for s in SHOCK_DEFS
                          if s["needs"] is None or r["mix"].get(s["needs"], 0) >= 0.10]
            if candidates:
                sd = rng.choice(candidates)
                sev = rng.uniform(sd["sev"][0], sd["sev"][1])
                r["shock"] = {"id": sd["id"], "name": sd["name"], "sev": sev,
                              "months_left": rng.randint(sd["months"][0], sd["months"][1])}
                events.append({"type": "region_shock", "region": rid,
                               "title": "%s: %s" % (r["name"], sd["name"]),
                               "text": sd["text"],
                               "good": sev < 0})

        r["history"].append({"m": econ["months"], "act": r["local_activity"],
                             "pool": r["deposit_pool"] // 100, "pop": r["pop"],
                             "housing": r["housing_index"]})
        if len(r["history"]) > 1200:
            del r["history"][:len(r["history"]) - 1200]
    return events
