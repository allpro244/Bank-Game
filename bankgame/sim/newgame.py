"""Construct a fresh game: one small bank on a West Texas courthouse square."""

from . import ledger as L
from . import rng as R
from . import economy, regions, competitors, deposits, loans, securities
from . import funding, operations, regulation, fraud, crises

START_DATE = "2000-01-03"   # a Monday

RNG_STREAMS = ["econ", "region", "credit", "deposit", "fraud", "comp", "ops",
               "crisis", "event", "misc"]


def new_game(name="First National Bank of Caprock", seed=12345):
    streams = R.make_streams(seed, RNG_STREAMS)
    rng_econ = R.Rng(streams["econ"])

    state = {
        "meta": {"name": name, "seed": seed, "version": 1},
        "time": {"date": START_DATE, "day_index": 0},
        "rng": streams,
        "economy": economy.new_economy(rng_econ),
        "regions": regions.new_regions(rng_econ),
        "competitors": competitors.new_competitors(rng_econ),
        "regulation": regulation.new_regulation(),
        "crisis": crises.new_crisis(),
        "metrics": [],
        "events": {"pending": [], "log": [], "next_id": 1},
        "call_reports": [],
        "game_over": None,
        "audit_alarm": None,
        "bank": None,
    }

    bank = {
        "name": name,
        "ledger": L.new_ledger(),
        "deposits": deposits.default_config(state["economy"]),
        "loans": loans.default_config(),
        "securities": securities.new_book(),
        "funding": funding.new_funding(),
        "ops": operations.new_ops(),
        "fraud": fraud.new_fraud(),
        "policies": {"dividend_payout": 35, "charter": "state"},
        "products_enabled": ["checking", "savings", "cds", "auto", "mortgage",
                            "small_business", "ci", "cre", "ag"],
        "business_lines": [],
        "shares": 220_000,
        "preferred_rate": 0.07,
        "cached_assets": 0,
        "cached_htm_unrealized": 0,
        "last_quarter_net_income": 0,
        "roa_ttm": 0.011, "roe_ttm": 0.10,
        "tax_loss_carry": 0,
        "acquisitions": [],
    }
    state["bank"] = bank

    _seed_balance_sheet(state)
    _seed_operations(state)
    bank["cached_assets"] = L.total_assets(bank["ledger"])
    from .regulation import capital_ratios, pca_category
    r = capital_ratios(state)
    state["regulation"]["last_ratios"] = {k: (round(v, 5) if isinstance(v, float) else v)
                                          for k, v in r.items()}
    state["regulation"]["pca"] = pca_category(r)
    return state


def _seed_balance_sheet(state):
    bank = state["bank"]
    econ = state["economy"]
    ledger = bank["ledger"]

    # ---- deposits: $17.2M across the home market ----
    dep_seed = {
        "checking": 5_500_000_00, "checking_int": 1_200_000_00,
        "savings": 3_000_000_00, "money_market": 4_000_000_00,
        "cd_3m": 500_000_00, "cd_1y": 1_600_000_00,
        "cd_2y": 900_000_00, "cd_5y": 500_000_00,
    }
    nat = competitors.national_deposit_rates(econ)
    for prod, amt in dep_seed.items():
        rate = 0.0 if prod == "checking" else nat.get(prod, nat["savings"])
        deposits.seed_pool(bank["deposits"], "caprock", prod, amt, rate)
    total_dep = sum(dep_seed.values())

    # ---- loans: $13.2M seasoned home-market book ----
    loan_seed = [
        ("ag", "B", 2_400_000_00), ("ag", "A", 1_100_000_00),
        ("ci", "B", 1_400_000_00), ("ci", "A", 600_000_00),
        ("cre", "B", 1_700_000_00), ("cre", "A", 800_000_00),
        ("mortgage", "A", 1_900_000_00), ("mortgage", "B", 1_100_000_00),
        ("auto", "B", 800_000_00), ("auto", "C", 400_000_00),
        ("small_business", "B", 700_000_00), ("small_business", "C", 300_000_00),
    ]
    total_loans = 0
    for prod, tier, amt in loan_seed:
        rate = loans.offer_rate(state, prod, tier, "caprock")
        pool = loans.add_to_pool(bank["loans"], prod, "caprock", tier, "1997",
                                 amt, rate, 1.0)
        pool["age_m"] = 30
        total_loans += amt

    # ---- securities: $4.0M ----
    sec_seed = [("treasury", 2.0, 1_500_000_00, "AFS"),
                ("treasury", 5.0, 1_000_000_00, "AFS"),
                ("agency", 3.0, 500_000_00, "AFS"),
                ("mbs", 7.0, 1_000_000_00, "HTM")]
    total_sec_afs = 0
    total_sec_htm = 0
    for typ, tenor, par, cls in sec_seed:
        coupon = securities.type_yield(econ, typ, tenor)
        lot = {"id": bank["securities"]["next_id"], "type": typ, "tenor0": tenor,
               "maturity_m": int(tenor * 12), "coupon": coupon, "par": par,
               "book": par, "cls": cls, "mv": par, "bought": START_DATE}
        bank["securities"]["next_id"] += 1
        bank["securities"]["lots"].append(lot)
        if cls == "AFS":
            total_sec_afs += par
        else:
            total_sec_htm += par

    cash = 1_400_000_00
    fed_bal = 800_000_00
    premises = 500_000_00
    allowance = int(total_loans * 0.0125)

    assets = cash + fed_bal + total_sec_afs + total_sec_htm + total_loans \
        - allowance + premises
    common = 1_200_000_00
    retained = assets - total_dep - common
    assert retained > 0, "opening equity plug went negative"

    lines = [
        ["1000", cash, 0], ["1010", fed_bal, 0],
        ["1200", total_sec_afs, 0], ["1210", total_sec_htm, 0],
        ["1300", total_loans, 0], ["1350", 0, allowance],
        ["1500", premises, 0],
        ["2000", 0, dep_seed["checking"]], ["2010", 0, dep_seed["checking_int"]],
        ["2020", 0, dep_seed["savings"]], ["2030", 0, dep_seed["money_market"]],
        ["2040", 0, dep_seed["cd_3m"] + dep_seed["cd_1y"] + dep_seed["cd_2y"]
                    + dep_seed["cd_5y"]],
        ["3000", 0, common], ["3100", 0, retained],
    ]
    L.post(ledger, START_DATE, "Opening balance sheet", lines, tag="open")


def _seed_operations(state):
    bank = state["bank"]
    ops = bank["ops"]
    ops["branches"].append({"id": 1, "market": "caprock", "open": True, "quality": 2,
                            "monthly_cost": operations.BRANCH_MONTHLY,
                            "opened": START_DATE})
    ops["next_branch_id"] = 2
    # three employees; the owner (you) works free
    ops["staff"]["tellers"]["count"] = 1
    ops["staff"]["lenders"]["count"] = 1
    ops["staff"]["lenders"]["skill"] = 2.6
    ops["staff"]["ops"]["count"] = 1
    ops["brand"]["caprock"] = 24.0
    ops["marketing"]["caprock"] = 1_500_00
