"""Deposit franchise: pools by market x product, priced by you, fought
over by rivals, money funds and fintechs.

Deposit beta is EMERGENT here: when the Fed hikes and you lag, your money
market and CD balances walk out the door at a speed set by each product's
"heat" (hot-money factor), your local competition, your brand, and your
digital reach. Checking is sticky; CDs and MMDA are not.

All pool balance changes post matching ledger entries, so the ledger's
deposit accounts always tie to the sum of the pools.
"""

from . import ledger as L
from . import competitors as C

PRODUCTS = ["checking", "checking_int", "savings", "money_market",
            "cd_3m", "cd_1y", "cd_2y", "cd_5y"]

ACCT = {"checking": "2000", "checking_int": "2010", "savings": "2020",
        "money_market": "2030", "cd_3m": "2040", "cd_1y": "2040",
        "cd_2y": "2040", "cd_5y": "2040"}

CD_TERM_MONTHS = {"cd_3m": 3, "cd_1y": 12, "cd_2y": 24, "cd_5y": 60}

# share of a market's total deposit pool sitting in each product
MIX = {"checking": 0.30, "checking_int": 0.10, "savings": 0.17,
       "money_market": 0.23, "cd_3m": 0.05, "cd_1y": 0.08,
       "cd_2y": 0.04, "cd_5y": 0.03}

# price sensitivity (target multiplier per 100bp of rate edge) and
# adjustment speed (fraction of gap closed per month)
SENS = {"checking": 0.0, "checking_int": 0.12, "savings": 0.30,
        "money_market": 0.85, "cd_3m": 1.10, "cd_1y": 1.00,
        "cd_2y": 0.90, "cd_5y": 0.80}
SPEED = {"checking": 0.035, "checking_int": 0.045, "savings": 0.06,
         "money_market": 0.16, "cd_3m": 0.30, "cd_1y": 0.12,
         "cd_2y": 0.07, "cd_5y": 0.045}

AVG_BAL = {"checking": 6200_00, "checking_int": 11000_00, "savings": 9500_00,
           "money_market": 42000_00, "cd_3m": 30000_00, "cd_1y": 28000_00,
           "cd_2y": 32000_00, "cd_5y": 35000_00}

UNINSURED_BY_KIND = {"rural": 0.13, "small_metro": 0.20, "suburb": 0.22,
                     "metro": 0.30, "money_center": 0.52}


def default_config(econ):
    return {
        # pricing lever: basis points vs the prevailing national market rate
        # for each product (0 = match market; +50 = pay 50bp over)
        "offsets_bp": {p: 0 for p in PRODUCTS},
        "fees": {  # cents
            "monthly_fee": 500, "overdraft_fee": 2800, "nsf_fee": 2800,
            "atm_fee": 200, "wire_fee": 2000, "foreign_txn_pct": 200,  # bp
            "safe_deposit_annual": 4500,
        },
        "promo_cd_bonus": 0.0,     # extra rate on all CDs (promo lever)
        # Optional per-town override of offsets_bp. Missing product = franchise default.
        "market_offsets_bp": {},
        "pools": {},               # market -> product -> {balance, accounts, wavg_rate, accrued}
    }


def open_market(bank_deps, market_id):
    if market_id not in bank_deps["pools"]:
        bank_deps["pools"][market_id] = {
            p: {"balance": 0, "accounts": 0, "wavg_rate": 0.0, "accrued": 0}
            for p in PRODUCTS}


def seed_pool(bank_deps, market_id, product, balance, rate):
    open_market(bank_deps, market_id)
    pool = bank_deps["pools"][market_id][product]
    pool["balance"] += balance
    pool["accounts"] += max(1, balance // AVG_BAL[product])
    pool["wavg_rate"] = rate


def totals(bank_deps):
    out = {p: 0 for p in PRODUCTS}
    naccts = 0
    for mkt in bank_deps["pools"].values():
        for p in PRODUCTS:
            out[p] += mkt[p]["balance"]
            naccts += mkt[p]["accounts"]
    out["_total"] = sum(out[p] for p in PRODUCTS)
    out["_accounts"] = naccts
    return out


def offset_bp(state, product, market_id=None):
    """Franchise offset, or a town override when one is set."""
    deps = state["bank"]["deposits"]
    base = int(deps["offsets_bp"].get(product, 0) or 0)
    if not market_id:
        return base
    town = (deps.get("market_offsets_bp") or {}).get(market_id) or {}
    if product in town and town[product] is not None:
        return int(town[product])
    return base


def effective_rate(state, product, market_id=None):
    """The rate you are actually paying: market rate + your offset."""
    if product == "checking":
        return 0.0
    deps = state["bank"]["deposits"]
    nat = C.national_deposit_rates(state["economy"])
    r = nat.get(product, nat["savings"]) + offset_bp(state, product, market_id) / 10000.0
    if product.startswith("cd_"):
        r += deps.get("promo_cd_bonus", 0.0)
    return max(0.0, round(r, 5))


# How many times THIS bank's assets it can reasonably hold as deposits
# in one market at steady state. Rural towns are small enough that a
# $20M bank can be a real player; Dallas is not.
KIND_ASSET_MULT = {
    "rural": 1.8, "small_metro": 1.1, "suburb": 0.85,
    "metro": 0.40, "money_center": 0.20,
}

# A branch serves a trade area, not the entire metro pool. Rural towns
# are the whole town. Dallas is a few miles, not $100B.
CATCHMENT = {
    "rural": None,
    "small_metro": 2_500_000_000_00,
    "suburb": 1_800_000_000_00,
    "metro": 1_200_000_000_00,
    "money_center": 900_000_000_00,
}


def office_count(state, market_id):
    return sum(1 for b in state["bank"]["ops"]["branches"]
               if b.get("market") == market_id and b.get("open"))


def office_effective(n_offices):
    """How many full catchments N windows actually contest.

    First office is a full trade area. Extra windows overlap the same
    streets — five Houston branches are not five Dallases.
    """
    n = max(1, int(n_offices))
    return 1.0 + 0.42 * (n - 1) ** 0.65


def office_size_boost(n_offices):
    """First office is 1.0× so A1 size caps do not move."""
    n = max(0, int(n_offices))
    return min(1.28, 1.0 + 0.10 * max(0, n - 1))


def trade_pool(state, market_id, extra_offices=0):
    """Deposit pool this franchise can actually contest in `market_id`."""
    region = state["regions"][market_id]
    pool = max(1, region["deposit_pool"])
    cap_one = CATCHMENT.get(region["kind"])
    if not cap_one:
        return pool
    n = office_count(state, market_id) + extra_offices
    if n <= 0:
        n = 1
    digital = state["bank"]["ops"].get("digital_level", 0)
    catch = int(cap_one * office_effective(n) * (1.0 + 0.12 * digital))
    return max(1, min(pool, catch))


def presence_score(state, market_id, extra_offices=0):
    """How visible/reachable the bank is in a market: branches + digital."""
    bank = state["bank"]
    branches = [b for b in bank["ops"]["branches"]
                if b["market"] == market_id and b["open"]]
    digital = bank["ops"]["digital_level"]          # 0..5
    score = 0.0
    for b in branches:
        score += 1.0 * (0.8 + 0.1 * b.get("quality", 2))
    score += extra_offices * 1.0
    score = score ** 0.72 if score > 0 else 0.0     # diminishing returns
    score += digital * 0.35                          # digital reaches everywhere
    return score


def market_deposits(state, market_id):
    """Deposit balances already booked in this market (cents)."""
    pools = state["bank"]["deposits"]["pools"].get(market_id)
    if not pools:
        return 0
    return sum(pools[p]["balance"] for p in PRODUCTS)


def months_in_market(state, market_id):
    """Months since the first open branch (0 if none)."""
    import datetime
    opened = [b.get("opened") for b in state["bank"]["ops"]["branches"]
              if b.get("market") == market_id and b.get("open") and b.get("opened")]
    if not opened:
        return 0
    cur = datetime.date.fromisoformat(state["time"]["date"])
    earliest = min(datetime.date.fromisoformat(d) for d in opened)
    return max(0, (cur.year - earliest.year) * 12 + cur.month - earliest.month)


def market_is_established(state, market_id):
    """A real franchise already — don't ramp a seeded home market from zero."""
    region = state["regions"][market_id]
    here = market_deposits(state, market_id)
    floor = max(5_000_000_00, int(region["deposit_pool"] * 0.02))
    return here >= floor


def market_maturity(state, market_id):
    """0..1 ramp for a new market. Established books are 1."""
    if market_is_established(state, market_id):
        return 1.0
    return min(1.0, (months_in_market(state, market_id) + 4) / 30.0)


def size_share_cap(state, market_id, assets=None, extra_offices=0):
    """Max share of the *trade* pool a bank this size can hold."""
    region = state["regions"][market_id]
    pool = trade_pool(state, market_id, extra_offices=extra_offices)
    if assets is None:
        assets = max(1, state["bank"].get("cached_assets") or 1)
        if assets <= 1:
            from . import ledger as _L
            assets = max(1, _L.total_assets(state["bank"]["ledger"]))
    assets = max(1, assets)
    mult = KIND_ASSET_MULT.get(region["kind"], 0.6)
    n = office_count(state, market_id) + extra_offices
    # Extra windows lift how much of the town you can actually hold.
    # First office is 1.0× so A1 size caps do not move.
    return (assets * mult * office_size_boost(n)) / pool


def share_of_full_pool(state, market_id, extra_offices=0, maturity=None):
    """Attractiveness vs the trade area, expressed as a share of the full pool.

    A Dallas office contests a catchment, not $100B. Size caps still apply
    so a $20M bank cannot own the catchment overnight.
    """
    region = state["regions"][market_id]
    extra = extra_offices if extra_offices else 0
    pres = presence_score(state, market_id, extra_offices=extra)
    if pres <= 0:
        return 0.0
    comp_weight = 6.0 * region["competition"]
    raw = pres / (pres + comp_weight)
    trade = trade_pool(state, market_id, extra_offices=extra)
    capped_trade = min(raw, size_share_cap(state, market_id, extra_offices=extra))
    full = max(1, region["deposit_pool"])
    share = capped_trade * (trade / full)
    if maturity is None:
        maturity = market_maturity(state, market_id)
    return share * maturity


def natural_share(state, market_id):
    """Target deposit share of the full local pool (trade-area, then size cap)."""
    return share_of_full_pool(state, market_id)


def year1_gather_estimate(state, market_id):
    """Rough year-1 deposit gather (cents) if we open one more office here.

    Used by the branch-open preview. Same helpers as the monthly flow, so
    the UI cannot invent a different number than the engine.
    """
    region = state["regions"].get(market_id)
    if region is None:
        return 0
    already_here = office_count(state, market_id)
    extra = 1
    pres = presence_score(state, market_id, extra_offices=extra)
    if pres <= 0:
        pres = 1.0 ** 0.72
    comp_weight = 6.0 * region["competition"]
    raw = pres / (pres + comp_weight)
    trade = trade_pool(state, market_id, extra_offices=extra)
    capped_trade = min(raw, size_share_cap(state, market_id, extra_offices=extra))
    # New markets ramp; a second office in a town you already serve does not.
    ramp = 1.0 if already_here > 0 else min(1.0, 16.0 / 30.0)
    share_trade = capped_trade * ramp
    brand = state["bank"]["ops"]["brand"].get(market_id, 8.0)
    brand_mult = 0.55 + 0.9 * (brand / 100.0)
    already = market_deposits(state, market_id)
    target = int(trade * share_trade * brand_mult)
    return max(0, target - already)


def step_day(state, days):
    """Accrue deposit interest for `days` calendar days."""
    bank = state["bank"]
    deps = bank["deposits"]
    total_accrual = 0
    for market_id, mkt in deps["pools"].items():
        for p in PRODUCTS:
            pool = mkt[p]
            if pool["balance"] <= 0:
                continue
            rate = pool["wavg_rate"] if p.startswith("cd_") else effective_rate(state, p, market_id)
            if rate <= 0:
                continue
            a = int(round(pool["balance"] * rate * days / 365.0))
            pool["accrued"] += a
            total_accrual += a
    # brokered handled by funding module
    if total_accrual > 0:
        L.post(bank["ledger"], state["time"]["date"], "Deposit interest accrual",
               [["5000", total_accrual, 0], ["2300", 0, total_accrual]], tag="int")
    return total_accrual


def pay_monthly_interest(state):
    """Credit accrued interest to customer balances (capitalized)."""
    bank = state["bank"]
    deps = bank["deposits"]
    by_acct = {}
    total = 0
    for mkt in deps["pools"].values():
        for p in PRODUCTS:
            pool = mkt[p]
            a = pool["accrued"]
            if a <= 0:
                continue
            pool["balance"] += a
            pool["accrued"] = 0
            by_acct[ACCT[p]] = by_acct.get(ACCT[p], 0) + a
            total += a
    if total > 0:
        lines = [["2300", total, 0]] + [[acct, 0, amt] for acct, amt in sorted(by_acct.items())]
        L.post(bank["ledger"], state["time"]["date"], "Deposit interest credited",
               lines, tag="int")


def step_month(state, rng):
    """Monthly deposit flows, CD maturities, fees, interchange."""
    bank = state["bank"]
    deps = bank["deposits"]
    econ = state["economy"]
    events = []
    pay_monthly_interest(state)

    fee_norm = 800  # $8 typical monthly fee
    my_fee = deps["fees"]["monthly_fee"]
    fee_mult = max(0.55, min(1.15, 1.0 - (my_fee - fee_norm) / 100.0 * 0.02))
    od_annoyance = max(0.0, (deps["fees"]["overdraft_fee"] - 3000) / 1000.0 * 0.01)
    svc = state["bank"]["ops"].get("service_quality", 1.0)
    fp_drag = state["bank"]["fraud"].get("false_positive_drag", 0.0)

    flows_by_acct = {}
    net_flow_total = 0
    for market_id in sorted(deps["pools"].keys()):
        region = state["regions"][market_id]
        mrates = C.market_rates(state, market_id)["deposit"]
        nat_share = natural_share(state, market_id)
        brand = bank["ops"]["brand"].get(market_id, 5.0)
        brand_mult = 0.55 + 0.9 * (brand / 100.0)
        pools = deps["pools"][market_id]
        for p in PRODUCTS:
            pool = pools[p]
            my_rate = effective_rate(state, p, market_id)
            mkt_rate = mrates.get(p, mrates.get("savings", 0.01))
            edge_100bp = (my_rate - mkt_rate) / 0.01
            price_mult = 2.718281828 ** (SENS[p] * edge_100bp)
            price_mult = max(0.15, min(3.5, price_mult))
            pm = fee_mult if p in ("checking", "checking_int") else 1.0
            pm *= max(0.7, 1.0 - od_annoyance - fp_drag) * svc
            target = int(region["deposit_pool"] * MIX[p] * nat_share
                         * price_mult * brand_mult * pm)
            # money-fund drain: badly lagging MMF yield bleeds MMDA/savings
            if p in ("money_market", "savings"):
                lag = econ["mmf_rate"] - my_rate
                if lag > 0.01:
                    target = int(target * max(0.45, 1.0 - (lag - 0.01) * 22))
            speed = SPEED[p]
            if econ["credit_stress"] > 0.4:      # flight matters more in stress
                speed *= 1.4
            if p.startswith("cd_"):
                flow = _cd_flow(pool, p, my_rate, mkt_rate, target, speed, rng)
            else:
                gap = target - pool["balance"]
                flow = int(gap * speed)
                pool["balance"] += flow
                if flow != 0 and pool["balance"] > 0:
                    pass
            pool["accounts"] = max(0, pool["balance"] // AVG_BAL[p]) if pool["balance"] > 0 else 0
            if flow != 0:
                flows_by_acct[ACCT[p]] = flows_by_acct.get(ACCT[p], 0) + flow
                net_flow_total += flow

    # post net flows: inflow = debit cash / credit deposits
    lines = []
    for acct, amt in sorted(flows_by_acct.items()):
        if amt > 0:
            lines.append([acct, 0, amt])
        elif amt < 0:
            lines.append([acct, -amt, 0])
    if net_flow_total > 0:
        lines.append(["1000", net_flow_total, 0])
    elif net_flow_total < 0:
        lines.append(["1000", 0, -net_flow_total])
    if lines:
        L.post(bank["ledger"], state["time"]["date"], "Net deposit flows (month)",
               lines, tag="flow")

    _monthly_fees(state, rng)
    return events


def _cd_flow(pool, p, my_rate, mkt_rate, target, speed, rng):
    """CDs: a slice matures each month; it rolls at today's rate or leaves.
    New money arrives toward target at the offered rate."""
    term = CD_TERM_MONTHS[p]
    bal = pool["balance"]
    matured = bal // term
    edge = (my_rate - mkt_rate) / 0.01
    stay_frac = max(0.25, min(0.97, 0.78 + 0.10 * edge))
    stays = int(matured * stay_frac)
    leaves = matured - stays
    new_money = 0
    gap = target - (bal - leaves)
    if gap > 0:
        new_money = int(gap * min(0.5, speed * 2.2))
    old_bal = bal
    new_bal = bal - leaves + new_money
    # weighted average booked rate: matured slice + new money reprice to my_rate
    if new_bal > 0:
        repriced = stays + new_money
        kept = new_bal - repriced
        kept = max(0, min(kept, old_bal - matured))
        wr = (pool["wavg_rate"] * kept + my_rate * repriced) / max(1, kept + repriced)
        pool["wavg_rate"] = round(wr, 6)
    else:
        pool["wavg_rate"] = my_rate
    pool["balance"] = new_bal
    return new_bal - old_bal


def _monthly_fees(state, rng):
    """Service charges, overdraft/NSF, interchange, wire/treasury fees."""
    bank = state["bank"]
    deps = bank["deposits"]
    econ = state["economy"]
    t = totals(deps)
    date = state["time"]["date"]

    chk_accounts = 0
    for mkt in deps["pools"].values():
        chk_accounts += mkt["checking"]["accounts"] + mkt["checking_int"]["accounts"]

    fees = deps["fees"]
    # maintenance fees (60% waived by balance/relationship)
    maint = int(chk_accounts * fees["monthly_fee"] * 0.40)
    # overdraft/NSF: incidence rises when the economy hurts, falls with fee shock
    od_rate = 0.055 + 0.02 * max(0.0, -econ["output_gap"]) / 3.0
    od_events = int(chk_accounts * od_rate)
    od_inc = od_events * (fees["overdraft_fee"] + fees["nsf_fee"]) // 2
    # ATM / misc
    atm = int(chk_accounts * 1.9 * fees["atm_fee"] * 0.35)
    svc_total = maint + od_inc + atm
    if svc_total > 0:
        # fees are drawn from customer balances
        take = min(svc_total, max(0, t["checking"]))
        L.post(bank["ledger"], date, "Deposit service charges",
               [["2000", take, 0], ["1000", svc_total - take, 0] if svc_total > take else ["1000", 0, 0],
                ["4100", 0, svc_total]], tag="fee")
        _drain_pools(deps, "checking", take)

    # interchange: debit card spend ~ $340/checking acct/mo; 1.30% -> bank keeps ~0.95%
    durbin = state["regulation"].get("durbin_capped", False)
    rate_bp = 45 if durbin else 95
    interchange = int(chk_accounts * 340_00 * rate_bp / 10000)
    if interchange > 0:
        L.post(bank["ledger"], date, "Card interchange income",
               [["1000", interchange, 0], ["4110", 0, interchange]], tag="fee")

    # wire / treasury management on business balances (approx: MMDA+checking share)
    biz_bal = int(t["checking"] * 0.35 + t["money_market"] * 0.40)
    tm_enabled = "treasury_mgmt" in bank["products_enabled"]
    tm = int(biz_bal * (0.0022 if tm_enabled else 0.0008) / 12)
    wires = int((biz_bal / 50_000_00) * fees["wire_fee"] * 0.5) if biz_bal > 0 else 0
    twt = tm + wires
    if twt > 0:
        L.post(bank["ledger"], date, "Wire and treasury management fees",
               [["1000", twt, 0], ["4120", 0, twt]], tag="fee")


def _drain_pools(deps, product, amount):
    """Reduce pool balances pro-rata after fee collection."""
    total = sum(m[product]["balance"] for m in deps["pools"].values())
    if total <= 0 or amount <= 0:
        return
    left = amount
    mkts = sorted(deps["pools"].keys())
    for i, mid in enumerate(mkts):
        pool = deps["pools"][mid][product]
        if i == len(mkts) - 1:
            take = min(left, pool["balance"])
        else:
            take = min(left, int(amount * pool["balance"] / total))
        pool["balance"] -= take
        left -= take
        if left <= 0:
            break


def uninsured_share(state):
    """Estimated share of deposits above the $250k FDIC limit."""
    deps = state["bank"]["deposits"]
    total = 0
    unins = 0
    for mid, mkt in deps["pools"].items():
        kind = state["regions"][mid]["kind"]
        base = UNINSURED_BY_KIND[kind]
        for p in PRODUCTS:
            b = mkt[p]["balance"]
            total += b
            w = base * (1.6 if p == "money_market" else 0.8 if p.startswith("cd") else 1.0)
            unins += int(b * min(0.9, w))
    # brokered is fully insured (packaged under limits)
    if total <= 0:
        return 0.0
    return round(unins / total, 4)


def cost_of_deposits(state):
    """Weighted average rate currently being paid."""
    deps = state["bank"]["deposits"]
    tot = 0
    wsum = 0.0
    for market_id, mkt in deps["pools"].items():
        for p in PRODUCTS:
            b = mkt[p]["balance"]
            if b <= 0:
                continue
            r = mkt[p]["wavg_rate"] if p.startswith("cd_") else effective_rate(state, p, market_id)
            tot += b
            wsum += b * r
    return (wsum / tot) if tot else 0.0
