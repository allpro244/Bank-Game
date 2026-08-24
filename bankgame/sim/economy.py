"""Macro economy: business cycle, inflation, Fed policy, yield curve,
credit conditions, commodities, equities, housing.

Design notes:
  * The business cycle EMERGES from an output-gap process with monetary
    policy feedback and an endogenous credit boom/bust mechanism -- it is
    not a scripted timer. Long expansions build leverage; when the boom
    variable is stretched, small shocks can cascade into a credit crunch.
  * The Fed follows a Taylor-type rule with heavy inertia plus occasional
    discretionary shocks, moving in 25bp steps.
  * The yield curve is a two-factor (short rate + long rate) model with a
    curvature hump; inversion happens naturally late in hiking cycles.
All rates are decimal fractions (0.05 = 5%). Monthly update on the first
business day of each month; small daily noise on the curve.
"""

TENORS = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]

HIST_CAP = 2400  # months (~200 years)


def new_economy(rng):
    econ = {
        "output_gap": 0.5,          # % of potential GDP
        "gap_prev": 0.3,
        "potential_growth": 2.4,    # real, %/yr
        "inflation": 2.6,           # %/yr, headline
        "core_inflation": 2.4,
        "unemployment": 4.6,
        "natural_unemployment": 4.5,
        "fed_funds": 0.0525,
        "r_star": 1.0,              # natural real rate, %
        "long_rate": 0.062,         # 10y anchor
        "term_premium": 0.009,
        "curvature": 0.0,
        "gdp_growth": 3.0,          # latest annualized real growth, %
        "consumer_confidence": 100.0,
        "credit_boom": 0.25,        # 0..1.5 leverage in the system
        "credit_stress": 0.05,      # 0..1 crunch severity
        "in_bust": 0,               # months remaining of active bust
        "ig_spread": 0.012,
        "hy_spread": 0.045,
        "equity_index": 1000.0,
        "equity_drawdown": 0.0,
        "oil": 27.0,                # WTI $/bbl
        "natgas": 2.4,
        "cattle": 70.0,             # $/cwt
        "cotton": 0.55,             # $/lb
        "housing_index": 100.0,     # national
        "housing_apprec": 3.0,      # %/yr latest
        "cap_rate": 0.085,          # commercial property cap rate
        "mmf_rate": 0.048,          # money market fund yield competitors
        "recession": False,
        "months": 0,
        "history": [],              # monthly snapshots for charts
    }
    econ["curve"] = _build_curve(econ)
    return econ


def _build_curve(e):
    """Yield curve from short rate, long anchor, and curvature hump."""
    short = e["fed_funds"] + 0.0005
    long10 = e["long_rate"]
    curve = {}
    import math
    for t in TENORS:
        w = math.exp(-t / 2.8)            # weight on the short end
        base = w * short + (1 - w) * long10
        hump = e["curvature"] * (math.exp(-((t - 2.0) ** 2) / 4.0))
        slope_ext = 0.0
        if t > 10:                        # 20y/30y extension beyond 10y anchor
            slope_ext = (e["term_premium"] * 0.5) * min(1.0, (t - 10) / 20.0)
        curve[str(t)] = max(0.0001, base + hump + slope_ext)
    return curve


def yield_at(econ, tenor_years):
    """Linear interpolation on the stored curve."""
    c = econ["curve"]
    if tenor_years <= TENORS[0]:
        return c[str(TENORS[0])]
    if tenor_years >= TENORS[-1]:
        return c[str(TENORS[-1])]
    for i in range(len(TENORS) - 1):
        a, b = TENORS[i], TENORS[i + 1]
        if a <= tenor_years <= b:
            ya, yb = c[str(a)], c[str(b)]
            f = (tenor_years - a) / (b - a)
            return ya + f * (yb - ya)
    return c[str(TENORS[-1])]


def step_month(econ, rng, date=None, era="sandbox"):
    """Advance the macro economy one month."""
    e = econ
    e["months"] += 1

    # --- credit cycle: booms build during easy times, busts release them ---
    real_rate = e["fed_funds"] * 100 - e["core_inflation"]
    easy = max(0.0, e["r_star"] - real_rate) * 0.024 + max(0.0, e["output_gap"]) * 0.012
    e["credit_boom"] = max(0.0, min(1.6, e["credit_boom"] + easy - 0.003
                                    - e["credit_stress"] * 0.09))
    bust_prob = 0.0
    if e["credit_boom"] > 0.60:
        bust_prob = (e["credit_boom"] - 0.60) ** 2 * 0.22
    if e["in_bust"] == 0 and rng.chance(bust_prob):
        # A credit bust begins: 8-20 months of stress scaled by boom size
        e["in_bust"] = rng.randint(8, 20)
        e["bust_severity"] = 0.35 + 0.65 * min(1.0, (e["credit_boom"] - 0.6))
    if e["in_bust"] > 0:
        e["in_bust"] -= 1
        sev = e.get("bust_severity", 0.5)
        e["credit_stress"] = min(1.0, e["credit_stress"] + 0.10 * sev + rng.uniform(0, 0.04))
        e["credit_boom"] = max(0.0, e["credit_boom"] - 0.05)
    else:
        e["credit_stress"] = max(0.02, e["credit_stress"] * 0.90)

    # --- output gap: AR(2) + policy drag + credit stress + shocks ---
    shock = rng.normal(0.0, 0.33)
    policy_drag = -0.045 * (real_rate - e["r_star"])
    stress_drag = -1.5 * e["credit_stress"] * 0.20
    new_gap = (1.25 * e["output_gap"] - 0.32 * e["gap_prev"]
               + policy_drag + stress_drag + shock)
    new_gap = max(-9.0, min(6.0, new_gap))
    gap_change = new_gap - e["output_gap"]
    e["gap_prev"] = e["output_gap"]
    e["output_gap"] = new_gap
    e["gdp_growth"] = round(e["potential_growth"] + gap_change * 12.0, 2)
    e["recession"] = e["output_gap"] < -1.0 and gap_change < 0.05

    # --- unemployment (Okun) ---
    target_u = e["natural_unemployment"] - 0.45 * e["output_gap"]
    e["unemployment"] = round(max(2.5, min(16.0,
        e["unemployment"] + 0.30 * (target_u - e["unemployment"]) + rng.normal(0, 0.07))), 2)

    # --- inflation: expectations + Phillips + oil passthrough ---
    oil_shock = (e["oil"] / max(15.0, e.get("oil_prev", e["oil"])) - 1.0)
    e["oil_prev"] = e["oil"]
    # expectations are only partly anchored: sustained inflation feeds itself
    anchor = 2.0 + 0.45 * (e["core_inflation"] - 2.0)
    supply_shock = 0.0
    if rng.chance(0.008):     # rare supply/inflation shock (embargo, pandemic...)
        supply_shock = rng.uniform(0.5, 2.8)
    e["core_inflation"] = round(max(-1.5, min(14.0,
        0.88 * e["core_inflation"] + 0.12 * anchor
        + 0.050 * e["output_gap"] + supply_shock + rng.normal(0, 0.11))), 2)
    e["inflation"] = round(max(-2.0, min(16.0,
        e["core_inflation"] + oil_shock * 2.2 + rng.normal(0, 0.12))), 2)

    # --- Fed reaction function (inertial Taylor rule, 25bp steps) ---
    pi = e["core_inflation"]
    desired = (e["r_star"] + pi + 1.5 * (pi - 2.0) + 0.5 * e["output_gap"]) / 100.0
    if e["credit_stress"] > 0.35:      # crisis-fighting discretion
        desired -= e["credit_stress"] * 0.02
    inertial = 0.80 * e["fed_funds"] + 0.20 * desired
    if rng.chance(0.04):               # occasional discretionary surprise
        inertial += rng.choice([-0.005, -0.0025, 0.0025, 0.005])
    new_ff = max(0.0, round(inertial * 400) / 400.0)   # nearest 25bp
    # cap per-month move at 75bp to mimic meeting cadence
    move = max(-0.0075, min(0.0075, new_ff - e["fed_funds"]))
    e["fed_funds"] = round(max(0.0, e["fed_funds"] + move), 6)

    # --- long rate: expectations + term premium ---
    exp_short = (e["r_star"] + pi) / 100.0
    e["term_premium"] = max(-0.005, min(0.035,
        e["term_premium"] + 0.05 * (0.012 - e["term_premium"]) + rng.normal(0, 0.0012)))
    target_long = 0.35 * e["fed_funds"] + 0.65 * exp_short + e["term_premium"]
    e["long_rate"] = max(0.004, e["long_rate"] + 0.18 * (target_long - e["long_rate"])
                         + rng.normal(0, 0.0011))
    e["curvature"] = max(-0.006, min(0.006, e["curvature"] * 0.85 + rng.normal(0, 0.0008)))

    # --- credit spreads ---
    e["ig_spread"] = round(max(0.005, 0.009 + 0.035 * e["credit_stress"]
                               + rng.normal(0, 0.0008)), 5)
    e["hy_spread"] = round(max(0.02, 0.032 + 0.14 * e["credit_stress"]
                               + rng.normal(0, 0.002)), 5)

    # --- equities ---
    eq_ret = (0.006 + 0.010 * gap_change - 6.0 * max(0.0, move)
              - 0.10 * max(0.0, e["credit_stress"] - 0.25) + rng.normal(0, 0.038))
    e["equity_index"] = max(50.0, e["equity_index"] * (1 + eq_ret))
    peak = max(e.get("equity_peak", e["equity_index"]), e["equity_index"])
    e["equity_peak"] = peak
    e["equity_drawdown"] = round(1 - e["equity_index"] / peak, 3)

    # --- commodities (OU in logs with occasional regime jumps) ---
    _commodity(e, rng, "oil", mu=55.0, theta=0.02, sigma=0.075, jump_p=0.012, jump_lo=-0.45, jump_hi=0.55)
    _commodity(e, rng, "natgas", mu=3.6, theta=0.03, sigma=0.10, jump_p=0.015, jump_lo=-0.4, jump_hi=0.8)
    _commodity(e, rng, "cattle", mu=110.0, theta=0.015, sigma=0.04, jump_p=0.006, jump_lo=-0.25, jump_hi=0.3)
    _commodity(e, rng, "cotton", mu=0.72, theta=0.02, sigma=0.055, jump_p=0.008, jump_lo=-0.3, jump_hi=0.4)

    # --- housing ---
    mort = yield_at(e, 10) + 0.017
    affordability_drag = max(0.0, (mort - 0.055)) * 28.0
    apprec = (2.6 + 0.9 * e["output_gap"] - affordability_drag
              - 9.0 * max(0.0, e["credit_stress"] - 0.3) + rng.normal(0, 0.9))
    e["housing_apprec"] = round(apprec, 2)
    e["housing_index"] = max(30.0, e["housing_index"] * (1 + apprec / 100.0 / 12.0))

    # --- CRE cap rates: float over long rate + stress ---
    tgt_cap = e["long_rate"] + 0.028 + 0.03 * e["credit_stress"]
    e["cap_rate"] = round(e["cap_rate"] + 0.10 * (tgt_cap - e["cap_rate"]), 5)

    # --- consumer confidence ---
    e["consumer_confidence"] = round(max(35.0, min(150.0,
        e["consumer_confidence"] + 2.2 * gap_change - 28.0 * max(0.0, e["credit_stress"] - 0.25)
        + rng.normal(0, 1.6) + 0.25 * (100 - e["consumer_confidence"]) * 0.05)), 1)

    # --- money market fund yield (deposit competitor) ---
    e["mmf_rate"] = round(max(0.0005, e["fed_funds"] - 0.0025), 5)

    if era == "historical" and date:
        _nudge_historical(e, date)

    e["curve"] = _build_curve(e)
    _record(e)


# Soft era landmarks. Organic cycle still runs; we blend toward these.
# (year, month) → fed_funds, credit_stress, credit_boom, output_gap, inflation
_HIST_MARKS = (
    (2000, 1, 0.0550, 0.06, 0.30, 0.8, 2.7),
    (2001, 1, 0.0600, 0.10, 0.25, 0.2, 3.4),
    (2001, 4, 0.0450, 0.22, 0.15, -1.2, 3.0),   # dot-com bust / 2001 cut
    (2002, 1, 0.0175, 0.18, 0.10, -1.6, 1.6),
    (2003, 6, 0.0100, 0.08, 0.20, 0.4, 2.3),
    (2004, 6, 0.0125, 0.06, 0.45, 1.2, 3.0),
    (2005, 6, 0.0325, 0.07, 0.70, 1.4, 3.2),
    (2006, 6, 0.0525, 0.10, 0.95, 1.1, 4.0),   # boom peak
    (2007, 8, 0.0525, 0.28, 0.70, 0.2, 2.4),
    (2008, 9, 0.0200, 0.75, 0.15, -3.5, 4.9),  # bust
    (2009, 3, 0.0025, 0.70, 0.05, -6.0, -0.4),
    (2011, 6, 0.0025, 0.20, 0.15, -1.2, 3.6),
    (2015, 12, 0.0050, 0.08, 0.30, 0.6, 0.7),
    (2018, 12, 0.0225, 0.08, 0.40, 1.0, 2.2),
    (2020, 4, 0.0025, 0.55, 0.10, -8.0, 0.3),  # COVID
    (2021, 6, 0.0010, 0.12, 0.45, 2.2, 5.4),
    (2022, 6, 0.0175, 0.14, 0.40, 1.4, 9.1),
    (2023, 3, 0.0475, 0.22, 0.30, 0.6, 5.0),   # SVB-era hike
    (2024, 6, 0.0530, 0.12, 0.35, 0.4, 3.0),
)


def _hist_lerp(date):
    y, m = int(date[:4]), int(date[5:7])
    t = y + (m - 1) / 12.0
    marks = [(my + (mm - 1) / 12.0, ff, st, boom, gap, inf)
             for my, mm, ff, st, boom, gap, inf in _HIST_MARKS]
    if t <= marks[0][0]:
        return marks[0][1:]
    if t >= marks[-1][0]:
        return marks[-1][1:]
    for i in range(len(marks) - 1):
        a, b = marks[i], marks[i + 1]
        if a[0] <= t <= b[0]:
            f = (t - a[0]) / max(0.01, b[0] - a[0])
            return tuple(a[j] + f * (b[j] - a[j]) for j in range(1, 6))
    return marks[-1][1:]


def _nudge_historical(e, date):
    """Blend the organic path toward a recognizable 2000–2024 shape."""
    ff, stress, boom, gap, infl = _hist_lerp(date)
    blend = 0.18
    e["fed_funds"] = round(max(0.0, e["fed_funds"] * (1 - blend) + ff * blend), 6)
    e["credit_stress"] = max(0.02, min(1.0, e["credit_stress"] * (1 - blend) + stress * blend))
    e["credit_boom"] = max(0.0, min(1.6, e["credit_boom"] * (1 - blend) + boom * blend))
    e["output_gap"] = max(-9.0, min(6.0, e["output_gap"] * (1 - blend) + gap * blend))
    e["inflation"] = round(max(-2.0, min(16.0, e["inflation"] * (1 - blend) + infl * blend)), 2)
    e["recession"] = e["output_gap"] < -1.0
    if stress > 0.45 and e.get("in_bust", 0) == 0:
        e["in_bust"] = 4
        e["bust_severity"] = max(e.get("bust_severity", 0.4), stress)


def _commodity(e, rng, key, mu, theta, sigma, jump_p, jump_lo, jump_hi):
    import math
    x = math.log(e[key])
    x += theta * (math.log(mu) - x) + rng.normal(0, sigma)
    if rng.chance(jump_p):
        x += math.log(1 + rng.uniform(jump_lo, jump_hi))
    e[key] = round(max(mu * 0.12, math.exp(x)), 2)


def step_day(econ, rng):
    """Small daily wiggle on the curve so marks move between months."""
    e = econ
    e["long_rate"] = max(0.004, e["long_rate"] + rng.normal(0, 0.00035))
    e["curve"] = _build_curve(e)


def _record(e):
    row = {
        "m": e["months"], "ff": e["fed_funds"], "y10": round(yield_at(e, 10), 5),
        "y2": round(yield_at(e, 2), 5), "gap": round(e["output_gap"], 2),
        "infl": e["inflation"], "unemp": e["unemployment"], "gdp": e["gdp_growth"],
        "oil": e["oil"], "equity": round(e["equity_index"], 1),
        "housing": round(e["housing_index"], 1), "stress": round(e["credit_stress"], 3),
        "boom": round(e["credit_boom"], 3), "ig": e["ig_spread"], "conf": e["consumer_confidence"],
        "cattle": e["cattle"], "cotton": e["cotton"], "natgas": e["natgas"],
        "cap_rate": e["cap_rate"],
    }
    e["history"].append(row)
    if len(e["history"]) > HIST_CAP:
        del e["history"][:len(e["history"]) - HIST_CAP]
