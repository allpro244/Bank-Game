"""Credit: origination, pricing, underwriting standards, delinquency,
charge-offs, CECL reserves, OREO, and individually-underwritten large loans.

Portfolio structure: loans live in POOLS keyed by (product, market, credit
tier, vintage year). Each pool remembers the underwriting quality of its
vintage -- loosen standards in 2004 and you will meet those loans again in
2008. Large credits above your approval threshold are generated as
individual applications with a credit memo for you (or your auto-policy)
to approve.

Delinquency is a monthly roll-rate model: current -> 30 -> 60 -> 90 ->
nonaccrual -> charge-off/OREO/cure, with probabilities scaled by macro
conditions, the borrower's region (oil towns crack when crude craters),
tier, and vintage quality.
"""

from . import ledger as L
from . import competitors as C

PRODUCTS = ["auto", "mortgage", "heloc", "credit_card", "small_business",
            "ci", "cre", "construction", "ag", "sba"]

FLOATING = {"heloc", "credit_card", "ci", "small_business", "construction", "sba"}

TERM_M = {"auto": 60, "mortgage": 360, "heloc": 120, "credit_card": 0,
          "small_business": 84, "ci": 60, "cre": 120, "construction": 24,
          "ag": 60, "sba": 120}

# base annual PD by product for tier B, normal times
BASE_PD = {"auto": 0.022, "mortgage": 0.008, "heloc": 0.010, "credit_card": 0.050,
           "small_business": 0.032, "ci": 0.018, "cre": 0.014, "construction": 0.034,
           "ag": 0.025, "sba": 0.036}

LGD = {"auto": 0.45, "mortgage": 0.22, "heloc": 0.35, "credit_card": 0.90,
       "small_business": 0.55, "ci": 0.45, "cre": 0.35, "construction": 0.50,
       "ag": 0.40, "sba": 0.40}

TIER_PD_MULT = {"A": 0.45, "B": 1.0, "C": 2.6}
TIER_RATE_ADJ = {"A": -0.005, "B": 0.0, "C": 0.016}

# share of demand by tier at each underwriting tightness (0 loose .. 4 tight)
TIER_MIX = {0: (0.25, 0.45, 0.30), 1: (0.33, 0.45, 0.22), 2: (0.42, 0.44, 0.14),
            3: (0.55, 0.38, 0.07), 4: (0.68, 0.30, 0.02)}

# fraction of a market's deposit pool that shows up as annual loan demand per product
DEMAND_FACTOR = {"auto": 0.045, "mortgage": 0.11, "heloc": 0.018, "credit_card": 0.02,
                 "small_business": 0.035, "ci": 0.06, "cre": 0.07, "construction": 0.025,
                 "ag": 0.02, "sba": 0.012}

# regional industry tilt: which products a market demands more of
def _demand_tilt(region, product):
    mix = region["mix"]
    t = 1.0
    if product == "ag":
        t = 0.15 + mix.get("ag", 0) * 6.0
    elif product in ("ci", "small_business"):
        t = 0.7 + mix.get("mfg", 0) + mix.get("oil", 0) * 1.4 + mix.get("services", 0) * 0.5
    elif product == "cre":
        t = 0.5 + (1.2 if region["kind"] in ("metro", "money_center") else 0.5) \
            + mix.get("services", 0) * 0.4
    elif product == "construction":
        t = 0.4 + region["base_growth"] * 0.45
    elif product == "mortgage":
        t = 0.7 + region["base_growth"] * 0.25
    return max(0.05, t)


RECOVERY_RATE = 0.15      # of charge-offs, returned over following months
RECOVERY_MONTHS = 12

FIRST = ["J.T.", "Wade", "Earlene", "Hollis", "Maria", "Dwight", "Lupe", "Cass",
         "Ray", "Darla", "Sonny", "Beau", "Imogene", "Travis", "Charlene", "Gus",
         "Lacey", "Emmett", "Rosa", "Vern"]
LAST = ["Culpepper", "Ratliff", "Zamora", "Bledsoe", "Hargrove", "Muncy", "Trevino",
        "Stallings", "Kimbrough", "Ozuna", "Pruett", "Whitfill", "Casteel", "Dunagan",
        "Reyes", "Lofton", "Skaggs", "Mayfield", "Herring", "Boydstun"]
BIZ = ["Cattle Co.", "Drilling Partners", "Farm Supply", "Custom Harvesting",
       "Truck Line", "Ranch Properties", "Well Service", "Gin Co-op", "Machine Works",
       "Development LLC", "Hotel Group", "Restaurant Group", "Equipment Rentals",
       "Crop Dusting", "Feedlot LP", "Storage Partners", "Medical Plaza LLC",
       "Retail Centers Ltd.", "Logistics Inc.", "Homebuilders LLC"]


def default_config():
    return {
        "spreads": {p: 0 for p in PRODUCTS},        # player lever, bp vs market
        "standards": {p: 2 for p in PRODUCTS},      # 0 loose .. 4 tight
        "limits": {p: 0 for p in PRODUCTS},         # cap, % of total loans (0 = none)
        "approval_threshold": 500_000_00,           # manual approval above this
        "auto_policy": "queue",                     # queue | approve_ab | decline
        "mortgage_sale_frac": 0.0,                  # sell share of new mortgages
        "pools": [],
        "large": [],
        "queue": [],
        "next_loan_id": 1,
        "recovery_pipe": [],                        # [{amt, months_left}]
        "oreo": [],                                 # [{value, months_held, market}]
        "reserve_required": 0,
        "ncos_ytd": 0,
        "stats": {"originated_mtd": 0, "declined_apps": 0, "approved_apps": 0,
                  "countered_apps": 0, "participated_apps": 0},
        "relationships": [],
    }


def offer_rate(state, product, tier, market_id):
    mkt = C.market_rates(state, market_id)["loan"]
    spread = state["bank"]["loans"]["spreads"][product] / 10000.0
    return round(max(0.005, mkt[product] + spread + TIER_RATE_ADJ[tier]), 5)


def relationships(cfg):
    return cfg.setdefault("relationships", [])


def _find_relationship(cfg, name, market=None):
    for rel in relationships(cfg):
        if rel["name"] == name and (market is None or rel["market"] == market):
            return rel
    return None


def remember_relationship(state, name, market, product, outcome, extra=None):
    """outcome: approved | declined | countered | participated | charged_off | paid."""
    cfg = state["bank"]["loans"]
    rel = _find_relationship(cfg, name, market)
    if rel is None:
        rel = {"name": name, "market": market, "product": product,
               "status": "known", "history": [], "times_booked": 0}
        relationships(cfg).append(rel)
    rel["product"] = product
    rel["last"] = extra or {}
    rel["history"].append({
        "date": state["time"]["date"], "outcome": outcome,
        "amount": (extra or {}).get("amount", 0),
    })
    rel["history"] = rel["history"][-12:]
    if outcome in ("approved", "participated"):
        rel["status"] = "performing"
        rel["times_booked"] = rel.get("times_booked", 0) + 1
    elif outcome == "declined":
        if rel.get("status") != "charged_off":
            rel["status"] = "declined"
    elif outcome == "countered":
        rel["status"] = "performing"
        rel["times_booked"] = rel.get("times_booked", 0) + 1
    elif outcome == "charged_off":
        rel["status"] = "charged_off"
    elif outcome == "paid":
        if rel.get("status") != "charged_off":
            rel["status"] = "performing"
    return rel


def _relationship_line(rel, product):
    if rel is None:
        return ""
    st = rel.get("status")
    n = rel.get("times_booked", 0)
    if st == "charged_off":
        return ("RELATIONSHIP: we charged this name off before. Price it like a "
                "stranger, or pass.")
    if st == "declined":
        return ("RELATIONSHIP: we declined them last time. They came back anyway — "
                "they remember, and so should we.")
    if n >= 1 and st == "performing":
        return ("RELATIONSHIP: performing customer, booked %d time%s. A yes here "
                "is how a franchise is built." % (n, "s" if n != 1 else ""))
    return "RELATIONSHIP: we know the name."


def counter_terms(app, extra_bp=100, hold_frac=0.70, term_frac=0.75):
    """What a standard counter looks like. Extra bp 50–150, smaller hold, shorter term."""
    extra_bp = max(50, min(150, int(extra_bp)))
    hold_frac = max(0.40, min(0.85, float(hold_frac)))
    term_frac = max(0.50, min(0.90, float(term_frac)))
    hold = int(app["amount"] * hold_frac)
    hold = (hold // 10_000_00) * 10_000_00
    hold = max(100_000_00, min(hold, app["amount"]))
    term = max(12, int((app.get("term_m") or 60) * term_frac))
    rate = round(app["rate"] + extra_bp / 10000.0, 5)
    return {
        "extra_bp": extra_bp, "hold_frac": hold_frac,
        "amount": hold, "rate": rate, "term_m": term,
        "sold": app["amount"] - hold,
    }


def participate_hold(app, hold_frac=0.40):
    hold_frac = max(0.25, min(0.50, float(hold_frac)))
    hold = int(app["amount"] * hold_frac)
    hold = (hold // 10_000_00) * 10_000_00
    hold = max(100_000_00, min(hold, app["amount"]))
    return hold, app["amount"] - hold


def mortgage_sale_preview(state, frac=None):
    """Rough next-month mortgage origination and the cash/gain if we sell `frac`."""
    cfg = state["bank"]["loans"]
    if frac is None:
        frac = cfg.get("mortgage_sale_frac", 0)
    frac = max(0.0, min(0.90, float(frac)))
    from .deposits import natural_share
    year_demand = 0
    for market_id in sorted(state["bank"]["deposits"]["pools"].keys()):
        region = state["regions"][market_id]
        nshare = natural_share(state, market_id)
        if nshare <= 0:
            continue
        year_demand += (region["deposit_pool"] * DEMAND_FACTOR["mortgage"]
                        * _demand_tilt(region, "mortgage")
                        * region.get("loan_demand_mult", 1.0) * nshare * 3.0)
    month = int(year_demand / 12.0)
    sold = int(month * frac)
    gain = int(sold * 0.015)
    mort_bal = sum(p["balance"] for p in cfg["pools"] if p["product"] == "mortgage")
    mort_bal += sum(l["balance"] for l in cfg["large"]
                    if l.get("product") == "mortgage"
                    and l.get("status") not in ("paid", "defaulted"))
    return {
        "est_month_orig": month, "frac": frac, "sold": sold, "gain": gain,
        "kept": month - sold, "mortgage_balance": mort_bal,
    }


def _find_pool(cfg, product, market, tier, year):
    for pool in cfg["pools"]:
        if (pool["product"] == product and pool["market"] == market
                and pool["tier"] == tier and pool["vint"] == year):
            return pool
    return None


def add_to_pool(cfg, product, market, tier, year, amount, rate, quality):
    pool = _find_pool(cfg, product, market, tier, year)
    if pool is None:
        pool = {"product": product, "market": market, "tier": tier, "vint": year,
                "balance": 0, "rate": rate, "quality": quality, "age_m": 0,
                "d30": 0.0, "d60": 0.0, "d90": 0.0, "npl": 0.0}
        cfg["pools"].append(pool)
    if pool["balance"] + amount > 0:
        w_new = amount / (pool["balance"] + amount)
        pool["rate"] = round(pool["rate"] * (1 - w_new) + rate * w_new, 5)
        pool["quality"] = round(pool["quality"] * (1 - w_new) + quality * w_new, 4)
    pool["balance"] += amount
    return pool


def total_loans(cfg):
    t = sum(p["balance"] for p in cfg["pools"])
    t += sum(l["balance"] for l in cfg["large"] if l["status"] not in ("paid", "defaulted"))
    return t


def npl_balance(cfg):
    t = sum(int(p["balance"] * p["npl"]) for p in cfg["pools"])
    t += sum(l["balance"] for l in cfg["large"] if l["status"] == "npl")
    return t


def yield_on_loans(cfg):
    tot = 0
    ws = 0.0
    for p in cfg["pools"]:
        perf = int(p["balance"] * (1 - p["npl"]))
        tot += perf
        ws += perf * p["rate"]
    for l in cfg["large"]:
        if l["status"] in ("current", "d30", "d60", "d90"):
            tot += l["balance"]
            ws += l["balance"] * l["rate"]
    return (ws / tot) if tot else 0.0


# ------------------------------------------------------------------ accrual

def step_day(state, days):
    bank = state["bank"]
    cfg = bank["loans"]
    accr = 0
    for p in cfg["pools"]:
        perf = p["balance"] - int(p["balance"] * p["npl"])
        if perf > 0:
            accr += int(round(perf * p["rate"] * days / 365.0))
    for l in cfg["large"]:
        if l["status"] in ("current", "d30", "d60", "d90"):
            accr += int(round(l["balance"] * l["rate"] * days / 365.0))
    if accr > 0:
        L.post(bank["ledger"], state["time"]["date"], "Loan interest accrual",
               [["1400", accr, 0], ["4000", 0, accr]], tag="int")
    return accr


def collect_monthly_interest(state):
    """Borrowers pay accrued interest in cash."""
    bank = state["bank"]
    ar = bank["ledger"]["balances"]["1400"]
    if ar > 0:
        L.post(bank["ledger"], state["time"]["date"], "Loan interest collected",
               [["1000", ar, 0], ["1400", 0, ar]], tag="int")


# ------------------------------------------------------------- originations

def macro_pd_mult(state, product, market_id):
    econ = state["economy"]
    region = state["regions"][market_id]
    u_gap = econ["unemployment"] - econ["natural_unemployment"] + region["employment_shock"]
    m = 1.0 + 0.30 * max(0.0, u_gap) + 1.9 * econ["credit_stress"]
    act = region["local_activity"]
    if act < 0.95:
        m *= 1.0 + (0.95 - act) * 3.2
    if product in ("cre", "construction"):
        m *= 1.0 + max(0.0, (econ["cap_rate"] - 0.085)) * 22
        if product == "construction" and econ["credit_stress"] > 0.3:
            m *= 1.5
    if product == "mortgage" or product == "heloc":
        if econ["housing_apprec"] < -2:
            m *= 1.0 + (-2 - econ["housing_apprec"]) * 0.16
    if product == "ag":
        shock = region.get("shock")
        if shock and shock["id"] == "drought":
            m *= 1.0 + shock["sev"] * 2.2
    if region["mix"].get("oil", 0) > 0.15 and econ["oil"] < 42:
        m *= 1.0 + region["mix"]["oil"] * (42 - econ["oil"]) / 42 * 4.0
    return min(9.0, m)


def lender_capacity(state):
    """Monthly origination capacity in cents, from lending staff."""
    staff = state["bank"]["ops"]["staff"]
    lenders = staff["lenders"]
    per = 1_100_000_00 * (0.6 + 0.2 * lenders["skill"])   # per lender per month
    return int(lenders["count"] * per * max(0.4, lenders["morale"]))


def originate_month(state, rng):
    bank = state["bank"]
    cfg = bank["loans"]
    econ = state["economy"]
    year = state["time"]["date"][:4]
    capacity = lender_capacity(state)
    used = 0
    total_before = max(1, total_loans(cfg))
    originated = {}
    events = []

    enabled = bank["products_enabled"]
    growth_cap = state["regulation"].get("growth_cap_active", False)

    # funding reality: past ~100% loans/deposits, originations shrink
    # hard before wholesale quietly fills the hole (the player has to
    # choose FHLB / pay-up / participate — see funding.manage_overnight).
    ldr = total_before / max(1, L.total_deposits(bank["ledger"]))
    if ldr <= 0.98:
        funding_mult = 1.0
    elif ldr <= 1.05:
        funding_mult = max(0.35, 1.0 - (ldr - 0.98) * 6.0)
    else:
        funding_mult = max(0.05, 0.35 - (ldr - 1.05) * 1.6)
    cash = (bank["ledger"]["balances"]["1000"]
            + bank["ledger"]["balances"]["1010"]
            + bank["ledger"]["balances"]["1100"])
    if cash < max(250_000_00, int(total_before * 0.01)):
        funding_mult *= 0.35
    if bank["funding"].get("shrink_originations"):
        funding_mult *= 0.25
        bank["funding"]["shrink_originations"] = False

    for market_id in sorted(bank["deposits"]["pools"].keys()):
        region = state["regions"][market_id]
        from .deposits import natural_share
        nshare = natural_share(state, market_id)
        if nshare <= 0:
            continue
        brand = bank["ops"]["brand"].get(market_id, 5.0)
        brand_mult = 0.6 + 0.8 * (brand / 100.0)
        for product in PRODUCTS:
            if product not in enabled:
                continue
            tight = cfg["standards"][product]
            spread_bp = cfg["spreads"][product]
            demand_year = (region["deposit_pool"] * DEMAND_FACTOR[product]
                           * _demand_tilt(region, product) * region["loan_demand_mult"])
            demand_mo = demand_year / 12.0
            # price competition: cheaper than market wins volume
            price_mult = max(0.15, min(2.6, 2.718281828 ** (-spread_bp / 10000.0 / 0.01 * 0.55)))
            tight_mult = 1.30 - 0.185 * tight
            stress_mult = max(0.25, 1.0 - econ["credit_stress"] * 1.1)
            my_vol = int(demand_mo * nshare * 3.0 * brand_mult * price_mult
                         * tight_mult * stress_mult * funding_mult)
            if my_vol <= 0:
                continue
            # concentration limit
            lim = cfg["limits"][product]
            if lim > 0:
                prod_bal = sum(p["balance"] for p in cfg["pools"] if p["product"] == product)
                room = int(total_before * lim / 100) - prod_bal
                my_vol = max(0, min(my_vol, room))
            if growth_cap:
                my_vol = int(my_vol * 0.35)
            if used + my_vol > capacity:
                my_vol = max(0, capacity - used)
            if my_vol <= 0:
                continue
            used += my_vol
            quality = round(1.45 - 0.20 * tight, 3)
            mix = TIER_MIX[tight]
            for tier, frac in zip(("A", "B", "C"), mix):
                amt = int(my_vol * frac)
                if amt <= 0:
                    continue
                rate = offer_rate(state, product, tier, market_id)
                sold = 0
                if product == "mortgage" and cfg["mortgage_sale_frac"] > 0:
                    sold = int(amt * cfg["mortgage_sale_frac"])
                    amt -= sold
                    gain = int(sold * 0.015)
                    if gain > 0:
                        L.post(bank["ledger"], state["time"]["date"],
                               "Mortgage banking: loans sold to secondary market",
                               [["1000", gain, 0], ["4160", 0, gain]], tag="loan")
                if amt > 0:
                    add_to_pool(cfg, product, market_id, tier, year, amt, rate, quality)
                    originated[product] = originated.get(product, 0) + amt
    total_orig = sum(originated.values())
    if total_orig > 0:
        from .funding import ensure_cash
        ensure_cash(state, total_orig)
        L.post(bank["ledger"], state["time"]["date"],
               "Loan originations funded (month)",
               [["1300", total_orig, 0], ["1000", 0, total_orig]], tag="loan")
        fees = int(total_orig * 0.0025)
        if fees > 0:
            L.post(bank["ledger"], state["time"]["date"], "Loan origination fees",
                   [["1000", fees, 0], ["4000", 0, fees]], tag="loan")
    cfg["stats"]["originated_mtd"] = total_orig
    # floating-rate pools reprice with the market
    for p in cfg["pools"]:
        if p["product"] in FLOATING and p["balance"] > 0:
            mkt = C.market_rates(state, p["market"])["loan"][p["product"]]
            target = max(0.005, mkt + cfg["spreads"][p["product"]] / 10000.0
                         + TIER_RATE_ADJ[p["tier"]])
            p["rate"] = round(p["rate"] + 0.8 * (target - p["rate"]), 5)
    events.extend(_generate_applications(state, rng))
    return events


# -------------------------------------------------------- large loan queue

def _generate_applications(state, rng):
    bank = state["bank"]
    cfg = bank["loans"]
    events = []
    thr = cfg["approval_threshold"]
    for market_id in sorted(bank["deposits"]["pools"].keys()):
        region = state["regions"][market_id]
        from .deposits import natural_share
        nshare = natural_share(state, market_id)
        if nshare <= 0:
            continue
        lam = min(3.0, 0.5 + (region["deposit_pool"] / 100 / 1_000_000_000) * 0.8) \
            * region["loan_demand_mult"] * min(1.0, nshare * 8)
        n = rng.poisson(lam * 0.5)
        for _ in range(min(n, 3)):
            app = _make_application(state, rng, market_id, thr)
            if app is None:
                continue
            policy = cfg["auto_policy"]
            if policy == "approve_ab" and app["tier"] in ("A", "B"):
                approve_application(state, app, auto=True)
                cfg["stats"]["approved_apps"] += 1
            elif policy == "decline":
                cfg["stats"]["declined_apps"] += 1
            else:
                cfg["queue"].append(app)
                events.append({
                    "type": "loan_application", "blocking": False,
                    "title": "Loan request: %s — $%s (%s)" % (
                        app["name"], f"{app['amount'] // 100:,}", app["product"].upper()),
                    "text": app["memo"], "app_id": app["id"],
                })
    # expire stale apps
    for app in cfg["queue"]:
        app["days_left"] -= 30
    expired = [a for a in cfg["queue"] if a["days_left"] <= 0]
    for a in expired:
        cfg["queue"].remove(a)
    return events


def _make_application(state, rng, market_id, thr):
    region = state["regions"][market_id]
    product = rng.weighted_choice([
        ("ci", 0.28), ("cre", 0.30), ("construction", 0.12),
        ("small_business", 0.12), ("ag", 0.10 if region["mix"].get("ag", 0) > 0.1 else 0.02),
        ("mortgage", 0.08)])
    if product not in state["bank"]["products_enabled"]:
        return None
    size_scale = max(1.0, (region["deposit_pool"] / 100 / 1_000_000_000) ** 0.5 * 3)
    amount = int(thr * rng.lognormal(0.45, 0.7) * size_scale)
    amount = min(amount, thr * 40)
    amount = (amount // 10_000_00) * 10_000_00
    if amount < thr:
        amount = thr + 10_000_00
    tier = rng.weighted_choice([("A", 0.30), ("B", 0.48), ("C", 0.22)])
    dscr = round(max(0.85, rng.normal({"A": 1.55, "B": 1.30, "C": 1.08}[tier], 0.18)), 2)
    ltv = round(min(0.97, max(0.35, rng.normal({"A": 0.58, "B": 0.70, "C": 0.82}[tier], 0.08))), 2)
    cfg = state["bank"]["loans"]
    rel = None
    returning = [r for r in relationships(cfg)
                 if r.get("market") == market_id
                 and r.get("status") in ("performing", "declined", "charged_off")]
    if returning and rng.chance(0.28):
        rel = rng.choice(returning)
        name = rel["name"]
        if rel.get("product") in state["bank"]["products_enabled"]:
            product = rel["product"]
        if rel.get("status") == "charged_off":
            tier = rng.weighted_choice([("B", 0.35), ("C", 0.65)])
    else:
        is_biz = product != "mortgage"
        if is_biz:
            name = "%s %s" % (rng.choice(LAST), rng.choice(BIZ))
        else:
            name = "%s %s" % (rng.choice(FIRST), rng.choice(LAST))
    rate = offer_rate(state, product, tier, market_id)
    coll = {"ci": "blanket lien on equipment, AR and inventory",
            "cre": "first lien on income-producing property",
            "construction": "first lien on project; personal guaranty",
            "small_business": "all business assets; personal guaranty",
            "ag": "crop liens, equipment, and ranch real estate",
            "mortgage": "first lien on primary residence"}[product]
    banks = state.get("competitors") or []
    if isinstance(banks, dict):
        banks = banks.get("banks") or []
    rivals = [c["name"] for c in banks
              if c.get("alive") and market_id in (c.get("markets") or [])]
    if not rivals:
        rivals = [c["name"] for c in banks if c.get("alive")]
    rival = rivals[0] if rivals else "a rival across the square"
    why = {
        "ag": "local operator, years in this county, deposits likely already here",
        "ci": "operating company in a market we serve",
        "cre": "income property in our footprint",
        "construction": "a project that will book deposits if it opens",
        "small_business": "a name the square already knows",
        "mortgage": "a household that may bring the checking account too",
    }.get(product, "a borrower in a market we serve")
    dscr_gloss = ("payment coverage is comfortable" if dscr >= 1.3
                  else "coverage is thin — a bad season hurts"
                  if dscr >= 1.15 else "they barely clear the payment")
    ltv_gloss = ("collateral has room" if ltv <= 0.70
                 else "little room if you have to foreclose" if ltv <= 0.85
                 else "you are underwriting the person, not the asset")
    exception = ""
    tight = state["bank"]["loans"]["standards"].get(product, 2)
    if tight >= 3 and tier == "C":
        exception = "\nPolicy exception: standards are tight and this is a C. Price it or pass."
    memo = (
        "CREDIT MEMO — {name}\n"
        "Market: {mkt} | Product: {prod} | Request: ${amt:,}\n"
        "Proposed rate: {rate:.2f}% | Term: {term} months | Risk tier: {tier}\n"
        "DSCR: {dscr:.2f}x ({dscr_g}) | LTV: {ltv:.0f}% ({ltv_g})\n"
        "Collateral: {coll}\n"
        "Why them: {why}\n"
        "If we decline: they walk to {rival}.\n"
        "Local conditions: activity index {act:.2f}, {shock}\n"
        "Analyst note: {note}{exc}"
    ).format(
        name=name, mkt=region["name"], prod=product.upper(),
        amt=amount // 100, rate=rate * 100, term=TERM_M.get(product, 60) or 60,
        tier=tier, dscr=dscr, ltv=ltv * 100, coll=coll,
        dscr_g=dscr_gloss, ltv_g=ltv_gloss, why=why, rival=rival, exc=exception,
        act=region["local_activity"],
        shock=("ACTIVE SHOCK: %s" % region["shock"]["name"]) if region["shock"] else "no active local shocks",
        note={"A": "Strong borrower; low risk of loss. Priced accordingly.",
              "B": "Acceptable credit with adequate coverage. Watch leverage.",
              "C": "Marginal coverage; this is a rate-for-risk decision. Exceptions to policy noted."}[tier])
    cash = (state["bank"]["ledger"]["balances"]["1000"]
            + state["bank"]["ledger"]["balances"]["1010"]
            + state["bank"]["ledger"]["balances"]["1100"])
    can_fund = cash >= amount
    rel_line = _relationship_line(rel, product)
    if rel_line:
        memo += "\n" + rel_line
    if not can_fund:
        memo += ("\nFUNDING: we do not have the cash to book this whole hold. "
                 "Decline, wait, or participate a piece (we keep 25–50%).")
    else:
        memo += ("\nOPTIONS: approve the whole hold, counter (+rate / smaller "
                 "hold / shorter term), participate a piece, or decline.")
    cfg["next_loan_id"] += 1
    return {"id": cfg["next_loan_id"], "name": name, "product": product,
            "market": market_id, "amount": amount, "rate": rate, "tier": tier,
            "dscr": dscr, "ltv": ltv, "memo": memo, "days_left": 60,
            "term_m": TERM_M.get(product, 60) or 60,
            "can_fund": can_fund,
            "returning": bool(rel),
            "why": why, "rival": rival,
            "dscr_gloss": dscr_gloss, "ltv_gloss": ltv_gloss,
            "relationship_line": rel_line,
            "exception": (exception.strip() or "Within published policy."),
            "collateral": coll}


def _book_large(state, app, amount, rate, term_m, auto=False, participated=0):
    bank = state["bank"]
    cfg = bank["loans"]
    L.post(bank["ledger"], state["time"]["date"],
           "Large loan funded: %s ($%s)" % (app["name"], f"{amount // 100:,}"),
           [["1300", amount, 0], ["1000", 0, amount]], tag="loan")
    rec = {
        "id": app["id"], "name": app["name"], "product": app["product"],
        "market": app["market"], "balance": amount, "rate": rate,
        "tier": app["tier"], "dscr": app["dscr"], "ltv": app["ltv"],
        "term_m": term_m, "age_m": 0, "status": "current",
        "orig_amount": amount, "auto": auto,
        "participated": participated,
    }
    cfg["large"].append(rec)
    return rec


def approve_application(state, app, auto=False):
    _book_large(state, app, app["amount"], app["rate"], app["term_m"], auto=auto)
    remember_relationship(state, app["name"], app["market"], app["product"],
                          "approved", {"amount": app["amount"], "tier": app["tier"]})


def decline_application(state, app):
    remember_relationship(state, app["name"], app["market"], app["product"],
                          "declined", {"amount": app["amount"], "tier": app["tier"]})


def counter_application(state, app, rng, extra_bp=100, hold_frac=0.70):
    """Offer better terms for us. Borrower accepts or walks (simple roll)."""
    terms = counter_terms(app, extra_bp=extra_bp, hold_frac=hold_frac)
    # A-tier walks more; a harsh cut in size or a fat rate bump also walks.
    walk = 0.18
    if app["tier"] == "A":
        walk += 0.16
    elif app["tier"] == "C":
        walk -= 0.08
    walk += max(0.0, (terms["extra_bp"] - 50) / 100.0) * 0.12
    walk += max(0.0, 0.85 - terms["hold_frac"]) * 0.25
    if app.get("dscr", 1.2) < 1.15:
        walk -= 0.08
    accept = not rng.chance(max(0.08, min(0.72, walk)))
    if not accept:
        remember_relationship(state, app["name"], app["market"], app["product"],
                              "declined",
                              {"amount": app["amount"], "tier": app["tier"],
                               "reason": "counter_rejected"})
        return {"accepted": False,
                "message": ("%s walked. They took the original ask to another desk."
                            % app["name"])}
    app = dict(app)
    app["amount"] = terms["amount"]
    app["rate"] = terms["rate"]
    app["term_m"] = terms["term_m"]
    _book_large(state, app, terms["amount"], terms["rate"], terms["term_m"])
    remember_relationship(state, app["name"], app["market"], app["product"],
                          "countered",
                          {"amount": terms["amount"], "tier": app["tier"],
                           "extra_bp": terms["extra_bp"]})
    return {
        "accepted": True, "amount": terms["amount"], "rate": terms["rate"],
        "term_m": terms["term_m"],
        "message": ("Counter accepted: $%s at %.2f%% for %d months (+%dbp, "
                    "smaller hold)."
                    % (f"{terms['amount'] // 100:,}", terms["rate"] * 100,
                       terms["term_m"], terms["extra_bp"])),
    }


def participate_application(state, app, hold_frac=0.40):
    """Book 25–50%; the rest is sold to a rival / correspondent. Escape hatch
    when we cannot fund the whole hold."""
    hold, sold = participate_hold(app, hold_frac)
    _book_large(state, app, hold, app["rate"], app["term_m"], participated=sold)
    fee = int(sold * 0.0025)
    if fee > 0:
        L.post(state["bank"]["ledger"], state["time"]["date"],
               "Participation fee: %s" % app["name"],
               [["1000", fee, 0], ["4000", 0, fee]], tag="loan")
    remember_relationship(state, app["name"], app["market"], app["product"],
                          "participated",
                          {"amount": hold, "sold": sold, "tier": app["tier"]})
    return {
        "hold": hold, "sold": sold, "fee": fee,
        "message": ("Participated %s: we hold $%s, sold $%s (fee $%s)."
                    % (app["name"], f"{hold // 100:,}", f"{sold // 100:,}",
                       f"{fee // 100:,}")),
    }


# ----------------------------------------------------- payments/delinquency

def step_month_credit(state, rng):
    """Amortization, delinquency rolls, charge-offs, recoveries, OREO."""
    bank = state["bank"]
    cfg = bank["loans"]
    econ = state["economy"]
    date = state["time"]["date"]
    events = []

    principal_total = 0
    chargeoffs = 0
    to_oreo = 0
    mort_rate_now = C.national_loan_rates(econ)["mortgage"]

    for p in cfg["pools"]:
        if p["balance"] <= 0:
            continue
        p["age_m"] += 1
        # ---- scheduled principal + prepayment on the current portion ----
        term = TERM_M[p["product"]]
        perf_frac = 1.0 - p["npl"]
        if p["product"] == "credit_card":
            pay = int(p["balance"] * perf_frac * 0.030)
        elif term:
            remaining = max(6, term - p["age_m"])
            pay = int(p["balance"] * perf_frac / remaining)
            if p["product"] in ("mortgage", "heloc"):
                incentive = p["rate"] - mort_rate_now
                cpr = 0.06 + max(0.0, incentive) * 3.5
                pay += int(p["balance"] * perf_frac * min(0.5, cpr) / 12)
            else:
                pay += int(p["balance"] * perf_frac * 0.002)  # baseline payoffs
        else:
            pay = int(p["balance"] * perf_frac * 0.02)
        pay = min(pay, int(p["balance"] * perf_frac))
        _shrink_pool(p, pay)
        principal_total += pay

        # ---- delinquency rolls ----
        pdm = (BASE_PD[p["product"]] / 12.0) * TIER_PD_MULT[p["tier"]] * p["quality"] \
            * macro_pd_mult(state, p["product"], p["market"]) * _seasoning(p)
        pdm = min(0.20, pdm)
        c = max(0.0, 1.0 - p["d30"] - p["d60"] - p["d90"] - p["npl"])
        new30 = c * pdm * 3.2          # entry into 30dpd is several x the pd
        to60 = p["d30"] * 0.38
        cure30 = p["d30"] * 0.45
        to90 = p["d60"] * 0.50
        cure60 = p["d60"] * 0.28
        tonpl = p["d90"] * 0.62
        cure90 = p["d90"] * 0.15
        npl_cure = p["npl"] * 0.05
        npl_resolve = p["npl"] * 0.14   # resolved this month (loss + collateral)
        p["d30"] = max(0.0, p["d30"] + new30 - to60 - cure30)
        p["d60"] = max(0.0, p["d60"] + to60 - to90 - cure60)
        p["d90"] = max(0.0, p["d90"] + to90 - tonpl - cure90)
        p["npl"] = max(0.0, p["npl"] + tonpl - npl_cure - npl_resolve)

        resolve_amt = int(p["balance"] * npl_resolve)
        if resolve_amt > 0:
            lgd = LGD[p["product"]]
            loss = int(resolve_amt * lgd)
            recover_now = resolve_amt - loss
            if p["product"] in ("mortgage", "cre", "construction") and recover_now > 0:
                oreo_part = int(recover_now * 0.6)
                # only real properties end up in OREO; small scraps settle in cash
                if oreo_part >= 50_000_00:
                    to_oreo += oreo_part
                    recover_now -= oreo_part
                    cfg["oreo"].append({"value": oreo_part, "months_held": 0,
                                        "market": p["market"]})
            chargeoffs += loss
            p["balance"] -= resolve_amt
            if recover_now > 0:
                L.post(bank["ledger"], date, "Loan payoffs from workout",
                       [["1000", recover_now, 0], ["1300", 0, recover_now]], tag="credit")

    if principal_total > 0:
        L.post(bank["ledger"], date, "Loan principal payments (month)",
               [["1000", principal_total, 0], ["1300", 0, principal_total]], tag="loan")
    if to_oreo > 0:
        L.post(bank["ledger"], date, "Foreclosed collateral to OREO",
               [["1550", to_oreo, 0], ["1300", 0, to_oreo]], tag="credit")

    chargeoffs += _step_large_loans(state, rng, events)

    if chargeoffs > 0:
        avail = L.allowance(bank["ledger"])
        if chargeoffs > avail:
            # charge-offs exceed reserve: top up reserve through provision first
            top = chargeoffs - avail
            L.post(bank["ledger"], date, "Provision: reserve deficiency at charge-off",
                   [["5150", top, 0], ["1350", 0, top]], tag="credit")
        L.post(bank["ledger"], date, "Net charge-offs",
               [["1350", chargeoffs, 0], ["1300", 0, chargeoffs]], tag="credit")
        cfg["ncos_ytd"] += chargeoffs
        cfg["recovery_pipe"].append({"amt": int(chargeoffs * RECOVERY_RATE),
                                     "months_left": RECOVERY_MONTHS})

    # recoveries trickle back into the allowance
    rec_total = 0
    for r in cfg["recovery_pipe"]:
        take = r["amt"] // max(1, r["months_left"])
        r["amt"] -= take
        r["months_left"] -= 1
        rec_total += take
    cfg["recovery_pipe"] = [r for r in cfg["recovery_pipe"] if r["months_left"] > 0 and r["amt"] > 0]
    if rec_total > 0:
        L.post(bank["ledger"], date, "Recoveries on charged-off loans",
               [["1000", rec_total, 0], ["1350", 0, rec_total]], tag="credit")

    _step_oreo(state, rng)
    _prune_pools(cfg)
    return events


def _shrink_pool(p, principal):
    if p["balance"] <= 0:
        return
    p["balance"] = max(0, p["balance"] - principal)


def _seasoning(p):
    """Losses ramp up over the first ~2 years of a vintage, then fade."""
    a = p["age_m"]
    if a < 6:
        return 0.5 + a / 12.0
    if a < 30:
        return 1.0
    return max(0.55, 1.0 - (a - 30) / 200.0)


def _step_large_loans(state, rng, events):
    bank = state["bank"]
    cfg = bank["loans"]
    econ = state["economy"]
    date = state["time"]["date"]
    chargeoffs = 0
    order = ["current", "d30", "d60", "d90", "npl"]
    for l in cfg["large"]:
        if l["status"] in ("paid", "defaulted"):
            continue
        l["age_m"] += 1
        # amortize
        if l["status"] in ("current", "d30"):
            remaining = max(6, l["term_m"] - l["age_m"])
            pay = min(l["balance"], int(l["balance"] / remaining))
            if pay > 0:
                L.post(bank["ledger"], date, "Principal: %s" % l["name"],
                       [["1000", pay, 0], ["1300", 0, pay]], tag="loan")
                l["balance"] -= pay
            if l["balance"] <= 0 or l["age_m"] >= l["term_m"]:
                if l["balance"] > 0:
                    L.post(bank["ledger"], date, "Payoff at maturity: %s" % l["name"],
                           [["1000", l["balance"], 0], ["1300", 0, l["balance"]]], tag="loan")
                    l["balance"] = 0
                l["status"] = "paid"
                remember_relationship(state, l["name"], l["market"], l["product"],
                                      "paid", {"amount": l.get("orig_amount", 0)})
                continue
        pdm = (BASE_PD[l["product"]] / 12.0) * TIER_PD_MULT[l["tier"]] \
            * macro_pd_mult(state, l["product"], l["market"]) \
            * (1.6 - min(1.5, l["dscr"] - 0.8))
        pdm = min(0.25, max(0.0005, pdm))
        idx = order.index(l["status"])
        if l["status"] == "npl":
            if rng.chance(0.16):   # resolution
                lgd = LGD[l["product"]] * (0.8 + l["ltv"] * 0.5)
                loss = int(l["balance"] * min(0.95, lgd))
                rec = l["balance"] - loss
                chargeoffs += loss
                if rec > 0:
                    L.post(bank["ledger"], date, "Workout recovery: %s" % l["name"],
                           [["1000", rec, 0], ["1300", 0, rec]], tag="credit")
                # the charged-off piece leaves 1300 via the aggregate NCO entry
                l["balance"] -= rec
                l["status"] = "defaulted"
                remember_relationship(state, l["name"], l["market"], l["product"],
                                      "charged_off",
                                      {"amount": l.get("orig_amount", l["balance"])})
                events.append({"type": "loan_loss", "blocking": False,
                               "title": "Loss taken: %s" % l["name"],
                               "text": "Workout of %s concluded. Charge-off: $%s. Recovered: $%s."
                                       % (l["name"], f"{loss // 100:,}", f"{rec // 100:,}")})
            elif rng.chance(0.08):
                l["status"] = "d90"  # partial cure
        else:
            if rng.chance(pdm * (3.0 if l["status"] == "current" else 12.0)):
                new_idx = min(len(order) - 1, idx + 1)
                l["status"] = order[new_idx]
                if l["status"] == "npl":
                    events.append({"type": "loan_watch", "blocking": False,
                                   "title": "NONACCRUAL: %s ($%s)" % (
                                       l["name"], f"{l['balance'] // 100:,}"),
                                   "text": "The %s credit to %s in %s has gone to nonaccrual. "
                                           "Expect a workout." % (l["product"].upper(), l["name"],
                                                                  state["regions"][l["market"]]["name"])})
            elif idx > 0 and rng.chance(0.45):
                l["status"] = order[idx - 1]
    cfg["large"] = [l for l in cfg["large"]
                    if not (l["status"] in ("paid", "defaulted") and l["balance"] <= 0)][-400:]
    return chargeoffs


def _step_oreo(state, rng):
    bank = state["bank"]
    cfg = bank["loans"]
    date = state["time"]["date"]
    sold = []
    for o in cfg["oreo"]:
        o["months_held"] += 1
        carry = int(o["value"] * 0.004)
        if carry > 0:
            L.post(bank["ledger"], date, "OREO carrying costs",
                   [["5210", carry, 0], ["1000", 0, carry]], tag="credit")
        if o["months_held"] > 3 and rng.chance(0.18):
            act = state["regions"][o["market"]]["local_activity"]
            haircut = max(0.0, min(0.4, 0.18 - (act - 1.0) * 0.5))
            proceeds = int(o["value"] * (1 - haircut))
            loss = o["value"] - proceeds
            lines = [["1000", proceeds, 0], ["1550", 0, o["value"]]]
            if loss > 0:
                lines.append(["5210", loss, 0])
            elif loss < 0:
                lines.append(["4150", 0, -loss])
            L.post(bank["ledger"], date, "OREO property sold", lines, tag="credit")
            sold.append(o)
    for o in sold:
        cfg["oreo"].remove(o)


def _prune_pools(cfg):
    cfg["pools"] = [p for p in cfg["pools"] if p["balance"] > 100]
    # merge very old vintages into a "seasoned" pool per product/market/tier
    if len(cfg["pools"]) > 2500:
        cfg["pools"].sort(key=lambda p: p["vint"])
        # merging handled implicitly by amortization; hard cap safety only


# --------------------------------------------------------------------- CECL

def quarterly_cecl(state):
    """Reset the allowance to lifetime expected losses; provision the delta."""
    bank = state["bank"]
    cfg = bank["loans"]
    econ = state["economy"]
    date = state["time"]["date"]
    required = 0
    forecast = 1.0 + 1.6 * econ["credit_stress"] + 0.25 * max(0.0, -econ["output_gap"]) / 2.0
    for p in cfg["pools"]:
        if p["balance"] <= 0:
            continue
        life_years = min((TERM_M[p["product"]] or 36) / 12.0, 5.0) * 0.6
        el = (BASE_PD[p["product"]] * TIER_PD_MULT[p["tier"]] * p["quality"]
              * LGD[p["product"]] * life_years * forecast)
        # delinquency-adjusted: troubled buckets carry specific reserves
        specific = (p["d30"] * 0.10 + p["d60"] * 0.25 + p["d90"] * 0.45
                    + p["npl"] * LGD[p["product"]])
        required += int(p["balance"] * min(0.6, el + specific))
    for l in cfg["large"]:
        if l["status"] in ("paid", "defaulted"):
            continue
        base = BASE_PD[l["product"]] * TIER_PD_MULT[l["tier"]] * LGD[l["product"]] * 2.2 * forecast
        stat_add = {"current": 0.0, "d30": 0.08, "d60": 0.2, "d90": 0.4,
                    "npl": LGD[l["product"]]}[l["status"]]
        required += int(l["balance"] * min(0.7, base + stat_add))
    cfg["reserve_required"] = required
    current = L.allowance(bank["ledger"])
    delta = required - current
    if delta > 0:
        L.post(bank["ledger"], date, "Provision for credit losses (CECL)",
               [["5150", delta, 0], ["1350", 0, delta]], tag="credit")
    elif delta < 0:
        release = min(-delta, current)
        if release > 0:
            L.post(bank["ledger"], date, "Release of credit reserves (CECL)",
                   [["1350", release, 0], ["5150", 0, release]], tag="credit")
    return required


def portfolio_stats(state):
    cfg = state["bank"]["loans"]
    by_prod = {}
    for p in cfg["pools"]:
        d = by_prod.setdefault(p["product"], {"balance": 0, "npl": 0, "d3090": 0,
                                              "rate_w": 0.0})
        d["balance"] += p["balance"]
        d["npl"] += int(p["balance"] * p["npl"])
        d["d3090"] += int(p["balance"] * (p["d30"] + p["d60"] + p["d90"]))
        d["rate_w"] += p["balance"] * p["rate"]
    for l in cfg["large"]:
        if l["status"] in ("paid", "defaulted"):
            continue
        d = by_prod.setdefault(l["product"], {"balance": 0, "npl": 0, "d3090": 0,
                                              "rate_w": 0.0})
        d["balance"] += l["balance"]
        if l["status"] == "npl":
            d["npl"] += l["balance"]
        elif l["status"] != "current":
            d["d3090"] += l["balance"]
        d["rate_w"] += l["balance"] * l["rate"]
    for prod, d in by_prod.items():
        d["rate"] = round(d["rate_w"] / d["balance"], 5) if d["balance"] else 0
        del d["rate_w"]
    return by_prod
