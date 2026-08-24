"""Operations: branches, people, marketing and brand, technology.

Staff capacity is real: lenders cap loan production, ops staff drive
service quality and fraud catch rates, compliance staffing shows up in
your exam ratings. People have skill, salary and morale; underpay or
overwork them and they leave -- your best lender can defect to a rival
and take business with him.
"""

from . import ledger as L

ROLES = ["tellers", "lenders", "credit_analysts", "ops", "compliance", "it", "execs"]

MARKET_SALARY = {  # annual cents, skill-2 baseline (scales with skill and inflation)
    "tellers": 34_000_00, "lenders": 95_000_00, "credit_analysts": 72_000_00,
    "ops": 52_000_00, "compliance": 88_000_00, "it": 98_000_00, "execs": 210_000_00,
}

BRANCH_OPEN_COST = 1_800_000_00
BRANCH_MONTHLY = 15_000_00
BRANCH_CLOSE_COST = 350_000_00

KIND_ORDER = ("rural", "small_metro", "suburb", "metro", "money_center")


def branch_open_cost(region):
    kind = region["kind"]
    return int(BRANCH_OPEN_COST * (2.5 if kind == "money_center"
                                   else 1.6 if kind == "metro" else 1.0))


def branch_monthly_cost(region, quality=2):
    kind = region["kind"]
    return int(BRANCH_MONTHLY * (1 + 0.3 * (quality - 2))
               * (3.0 if kind == "money_center"
                  else 1.8 if kind == "metro" else 1.0))


def preview_branch(state, market_id, quality=2):
    """What opening a branch here would do. Numbers use the same share
    helpers as the monthly deposit flow."""
    region = state["regions"].get(market_id)
    if region is None:
        return {"error": "unknown market"}
    from . import ledger as L
    from . import deposits as DEP
    from .regulation import capital_ratios, pca_category

    cost = branch_open_cost(region)
    monthly = branch_monthly_cost(region, quality)
    cash_now = (state["bank"]["ledger"]["balances"]["1000"]
                + state["bank"]["ledger"]["balances"]["1010"]
                + state["bank"]["ledger"]["balances"]["1100"])
    # ensure_cash is mutating — compute affordability without calling it
    can_fund = cash_now >= cost

    already = any(b.get("market") == market_id and b.get("open")
                  for b in state["bank"]["ops"]["branches"])
    # Estimate as if we had one more standard branch in this market.
    gather = DEP.year1_gather_estimate(state, market_id)
    if not already:
        # year1_gather_estimate already pretends presence=1 when score is 0
        pass

    r = capital_ratios(state)
    assets = max(1, r["assets"])
    te = r.get("cet1") or L.total_equity(state["bank"]["ledger"])
    # Branch: cash → premises (assets unchanged). Then deposits gather:
    # assets rise by the new deposits, equity does not.
    new_assets = assets + gather
    te_ratio = te / max(1, new_assets)
    cet1 = r["cet1_ratio"]
    # CET1/RWA barely moves (deposits are not RWA); leverage is the tell.
    lev = te / max(1, new_assets)

    if not can_fund:
        verdict = "cannot_fund"
    elif te_ratio <= 0.03 or lev < 0.03:
        verdict = "lethal"
    elif lev < 0.055 or cet1 < 0.07:
        verdict = "stretch"
    else:
        verdict = "safe"

    return {
        "market": market_id,
        "name": region["name"],
        "kind": region["kind"],
        "cost": cost,
        "monthly": monthly,
        "can_fund": can_fund,
        "already": already,
        "year1_gather": gather,
        "pool": region["deposit_pool"],
        "proforma_leverage": round(lev, 5),
        "proforma_te_ratio": round(te_ratio, 5),
        "cet1_now": round(cet1, 5),
        "pca_now": pca_category(r),
        "verdict": verdict,
    }


def new_ops():
    return {
        "branches": [],
        "next_branch_id": 1,
        "staff": {r: {"count": 0, "skill": 2.0, "salary": MARKET_SALARY[r],
                      "morale": 0.8} for r in ROLES},
        "marketing": {},          # market_id -> monthly spend cents
        "brand": {},              # market_id -> 0..100
        "digital_level": 0,       # 0..5
        "core_system_age": 2,     # years; old cores break
        "cyber_spend": 2_000_00,  # monthly
        "audit_spend": 1_500_00,  # monthly internal audit
        "service_quality": 1.0,
        "salary_multiplier": 1.0,  # player lever: pay vs market
        "auto_backfill": True,     # replace routine departures automatically
    }


def open_branch(state, market_id, quality=2):
    bank = state["bank"]
    ops = bank["ops"]
    region = state["regions"].get(market_id)
    if region is None:
        return "unknown market"
    cost = branch_open_cost(region)
    from .funding import ensure_cash
    if ensure_cash(state, cost) < cost:
        return "not enough cash ($%s needed)" % f"{cost // 100:,}"
    if any(b.get("market") == market_id and b.get("open") for b in ops["branches"]):
        return "already have a branch in this market"
    if state["regulation"].get("growth_cap_active") and len(ops["branches"]) > 2:
        return "growth restrictions under your enforcement action block new branches"
    b = {"id": ops["next_branch_id"], "market": market_id, "open": True,
         "quality": quality, "monthly_cost": branch_monthly_cost(region, quality),
         "opened": state["time"]["date"]}
    ops["next_branch_id"] += 1
    ops["branches"].append(b)
    L.post(bank["ledger"], state["time"]["date"],
           "Branch opened in %s" % region["name"],
           [["1500", cost, 0], ["1000", 0, cost]], tag="ops")
    from .deposits import open_market
    open_market(bank["deposits"], market_id)
    ops["brand"].setdefault(market_id, 3.0)
    ops["marketing"].setdefault(market_id, 0)
    return b


def digital_upgrade_cost(level):
    return int(1_500_000_00 * (1 + level) ** 1.6)


def core_upgrade_cost(assets):
    return int(max(assets, 20_000_000_00) * 0.004) + 500_000_00


def close_branch(state, branch_id):
    bank = state["bank"]
    ops = bank["ops"]
    open_n = sum(1 for x in ops["branches"] if x.get("open"))
    for b in ops["branches"]:
        if b["id"] == branch_id and b["open"]:
            if open_n <= 1:
                return "cannot close your last branch"
            residual = BRANCH_CLOSE_COST - min(BRANCH_CLOSE_COST,
                                              bank["ledger"]["balances"]["1500"])
            from .funding import ensure_cash
            if residual > 0 and ensure_cash(state, residual) < residual:
                return "not enough cash to close this branch ($%s)" % \
                    f"{residual // 100:,}"
            writeoff = min(BRANCH_CLOSE_COST, bank["ledger"]["balances"]["1500"])
            L.post(bank["ledger"], state["time"]["date"],
                   "Branch closed (%s)" % b["market"],
                   [["5170", BRANCH_CLOSE_COST, 0],
                    ["1500", 0, writeoff],
                    ["1000", 0, BRANCH_CLOSE_COST - writeoff]], tag="ops")
            b["open"] = False
            ops["branches"].remove(b)
            return {}
    return "branch not found"


def hire(state, role, count=1):
    ops = state["bank"]["ops"]
    if role not in ROLES:
        return "unknown role"
    s = ops["staff"][role]
    s["count"] += count
    # new hires dilute average skill slightly, cost market salary
    s["skill"] = round((s["skill"] * (s["count"] - count) + 2.0 * count) / s["count"], 2)
    return {"count": s["count"]}


def fire(state, role, count=1):
    bank = state["bank"]
    ops = bank["ops"]
    if role not in ROLES:
        return "unknown role"
    s = ops["staff"][role]
    count = min(count, s["count"])
    if count <= 0:
        return "nobody to let go"
    severance = int(s["salary"] * ops["salary_multiplier"] * count * 0.25)
    from .funding import ensure_cash
    if ensure_cash(state, severance) < severance:
        return "not enough cash for severance"
    s["count"] -= count
    s["morale"] = max(0.2, s["morale"] - 0.08 * count / max(1, s["count"] + count))
    L.post(bank["ledger"], state["time"]["date"], "Severance paid (%s)" % role,
           [["5100", severance, 0], ["1000", 0, severance]], tag="ops")
    return {"count": s["count"]}


def train(state, role):
    bank = state["bank"]
    ops = bank["ops"]
    s = ops["staff"][role]
    if s["count"] <= 0:
        return "no staff in that role"
    cost = int(s["count"] * 3_000_00)
    from .funding import ensure_cash
    if ensure_cash(state, cost) < cost:
        return "not enough cash"
    L.post(bank["ledger"], state["time"]["date"], "Training program (%s)" % role,
           [["5100", cost, 0], ["1000", 0, cost]], tag="ops")
    s["skill"] = round(min(5.0, s["skill"] + 0.25), 2)
    s["morale"] = min(1.0, s["morale"] + 0.05)
    return {"skill": s["skill"]}


def invest_digital(state):
    bank = state["bank"]
    ops = bank["ops"]
    if ops["digital_level"] >= 5:
        return "digital platform already best-in-class"
    cost = digital_upgrade_cost(ops["digital_level"])
    from .funding import ensure_cash
    if ensure_cash(state, cost) < cost:
        return "not enough cash ($%s needed)" % f"{cost // 100:,}"
    L.post(bank["ledger"], state["time"]["date"],
           "Digital banking build-out (level %d)" % (ops["digital_level"] + 1),
           [["5120", cost, 0], ["1000", 0, cost]], tag="ops")
    ops["digital_level"] += 1
    return {"level": ops["digital_level"]}


def upgrade_core(state):
    bank = state["bank"]
    ops = bank["ops"]
    assets = max(bank["cached_assets"], 20_000_000_00)
    cost = core_upgrade_cost(assets)
    from .funding import ensure_cash
    if ensure_cash(state, cost) < cost:
        return "not enough cash ($%s needed)" % f"{cost // 100:,}"
    L.post(bank["ledger"], state["time"]["date"], "Core system replacement",
           [["5120", cost, 0], ["1000", 0, cost]], tag="ops")
    ops["core_system_age"] = 0
    return {}


def monthly_opex(state, rng):
    """Salaries, occupancy, tech, marketing; brand and morale updates."""
    bank = state["bank"]
    ops = bank["ops"]
    econ = state["economy"]
    date = state["time"]["date"]
    events = []

    from .funding import ensure_cash

    # salaries (inflation-indexed drift annually via salary bases)
    sal_total = 0
    for r in ROLES:
        s = ops["staff"][r]
        sal_total += int(s["count"] * s["salary"] * ops["salary_multiplier"]
                         * (1 + 0.06 * (s["skill"] - 2)) / 12)
    # benefits load
    sal_total = int(sal_total * 1.38)
    if sal_total > 0:
        ensure_cash(state, sal_total)
        L.post(bank["ledger"], date, "Payroll and benefits",
               [["5100", sal_total, 0], ["1000", 0, sal_total]], tag="ops")

    occ = sum(b["monthly_cost"] for b in ops["branches"] if b["open"])
    # depreciation on premises
    prem = bank["ledger"]["balances"]["1500"]
    dep = int(prem * 0.03 / 12)
    if occ > 0:
        ensure_cash(state, occ)
        L.post(bank["ledger"], date, "Occupancy and equipment",
               [["5110", occ, 0], ["1000", 0, occ]], tag="ops")
    if dep > 0:
        L.post(bank["ledger"], date, "Depreciation",
               [["5110", dep, 0], ["1500", 0, dep]], tag="ops")

    assets = max(bank["cached_assets"], 20_000_000_00)
    tech = int(assets * 0.0026 / 12) + ops["cyber_spend"] \
        + int(ops["digital_level"] * 25_000_00) + ops["audit_spend"]
    ensure_cash(state, tech)
    L.post(bank["ledger"], date, "Technology, data processing, audit",
           [["5120", tech, 0], ["1000", 0, tech]], tag="ops")

    # everything else it takes to run a bank: insurance, legal, supplies,
    # exams, professional fees, franchise taxes. Sized so a passive
    # community book lands near a real 1% ROA, not a 2.5% printer.
    other = int(assets * 0.0110 / 12) + 12_000_00
    ensure_cash(state, other)
    L.post(bank["ledger"], date, "Other operating expense",
           [["5170", other, 0], ["1000", 0, other]], tag="ops")

    mkt_total = sum(ops["marketing"].values())
    if mkt_total > 0:
        cash = bank["ledger"]["balances"]["1000"]
        mkt_total = min(mkt_total, max(0, cash))
        if mkt_total > 0:
            L.post(bank["ledger"], date, "Marketing spend",
                   [["5130", mkt_total, 0], ["1000", 0, mkt_total]], tag="ops")

    # brand: build with marketing (log returns), decay without
    for mid in list(bank["deposits"]["pools"].keys()):
        ops["brand"].setdefault(mid, 3.0)
        spend = ops["marketing"].get(mid, 0)
        region = state["regions"][mid]
        eff_scale = max(1.0, (region["pop"] / 40000.0) ** 0.8)
        gain = 0.0
        if spend > 0:
            import math
            gain = 2.4 * math.log1p(spend / 100 / (9000.0 * eff_scale))
        b = ops["brand"][mid]
        ops["brand"][mid] = round(max(0.0, min(100.0, b * 0.988 + gain)), 2)

    # morale and turnover
    for r in ROLES:
        s = ops["staff"][r]
        if s["count"] <= 0:
            continue
        pay_gap = ops["salary_multiplier"] - 1.0
        target_morale = 0.75 + pay_gap * 1.5
        if r == "lenders":
            from .loans import lender_capacity
            util = 0.0
            cap = lender_capacity(state)
            if cap > 0:
                util = bank["loans"]["stats"].get("originated_mtd", 0) / cap
            if util > 0.92:
                target_morale -= 0.15
        s["morale"] = round(max(0.2, min(1.0, s["morale"] + 0.15 * (target_morale - s["morale"])
                                         + rng.normal(0, 0.02))), 3)
        # turnover: departures are auto-backfilled at market (skill dilutes,
        # recruiting costs hit payroll) unless the player freezes hiring
        quit_p = max(0.0, (0.010 + (0.75 - s["morale"]) * 0.05)) * s["count"]
        quits = min(s["count"], rng.poisson(quit_p))
        if quits > 0:
            if ops.get("auto_backfill", True):
                recruit = int(s["salary"] * 0.15) * quits
                if bank["ledger"]["balances"]["1000"] > recruit > 0:
                    L.post(bank["ledger"], date, "Recruiting/backfill (%s)" % r,
                           [["5100", recruit, 0], ["1000", 0, recruit]], tag="ops")
                s["skill"] = round(max(1.5, (s["skill"] * (s["count"] - quits)
                                             + 2.0 * quits) / s["count"]), 2)
            else:
                s["count"] -= quits
            if r == "lenders" and s["skill"] >= 3.2 and rng.chance(0.4):
                events.append({"type": "lender_defection", "blocking": False,
                               "title": "A senior lender walked",
                               "text": ("One of your best lenders just took a rival's offer — "
                                        "and their book of relationships goes with them. Loan "
                                        "production and some deposits will follow unless you "
                                        "raise pay (Operations > salary multiplier) or rebuild.")})
                # customers follow the lender
                for mid in ops["brand"]:
                    ops["brand"][mid] = max(0.0, ops["brand"][mid] * 0.94)

    # service quality: tellers+ops per branch and digital
    n_br = max(1, len([b for b in ops["branches"] if b["open"]]))
    cover = (ops["staff"]["tellers"]["count"] + ops["staff"]["ops"]["count"] * 0.5) / (n_br * 4.0)
    ops["service_quality"] = round(max(0.7, min(1.12,
        0.8 + 0.25 * min(1.3, cover) + 0.02 * ops["digital_level"])), 3)

    # core system aging & outage risk
    ops["core_system_age"] += 1 / 12.0
    outage_p = max(0.0, (ops["core_system_age"] - 8) * 0.004) \
        * (0.5 if ops["staff"]["it"]["count"] >= n_br else 1.0)
    if rng.chance(outage_p):
        loss = int(assets * 0.0006) + 50_000_00
        L.post(bank["ledger"], date, "CORE SYSTEM OUTAGE remediation",
               [["5160", loss, 0], ["1000", 0, loss]], tag="ops")
        for mid in ops["brand"]:
            ops["brand"][mid] = max(0.0, ops["brand"][mid] - 4.0)
        events.append({"type": "outage", "blocking": True,
                       "title": "CORE SYSTEM OUTAGE",
                       "text": ("Your %d-year-old core banking system went down for two days. "
                                "Branches ran on paper. Remediation cost $%s and customers are "
                                "furious. Replace the core (Operations tab) before it happens again.")
                               % (int(ops["core_system_age"]), f"{loss // 100:,}")})

    # annual-ish wage inflation
    if econ["months"] % 12 == 0:
        for r in ROLES:
            ops["staff"][r]["salary"] = int(ops["staff"][r]["salary"]
                                            * (1 + max(0.0, econ["inflation"]) / 100.0))
    return events
