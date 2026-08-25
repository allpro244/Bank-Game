"""Financial statements and metrics, generated from the ledger.

Nothing here is a cosmetic stat: every line is a sum of ledger account
balances or archived month-close P&L, and the drill-down in the UI goes
account -> journal entries.
"""

from . import ledger as L


def balance_sheet(state):
    ledger = state["bank"]["ledger"]
    b = lambda c: L.display_balance(ledger, c)
    loans_gross = b("1300")
    alw = L.allowance(ledger)
    bs = {
        "assets": [
            ("Cash and due from banks", b("1000")),
            ("Interest-bearing balances at Fed", b("1010")),
            ("Fed funds sold", b("1100")),
            ("Securities available-for-sale (fair value)", b("1200")),
            ("Securities held-to-maturity (amortized cost)", b("1210")),
            ("Loans, gross", loans_gross),
            ("  less: allowance for credit losses", -alw),
            ("Loans, net", loans_gross - alw),
            ("Accrued interest receivable", b("1400")),
            ("Premises and equipment", b("1500")),
            ("Other real estate owned", b("1550")),
            ("Goodwill and intangibles", b("1600")),
            ("Other assets", b("1700")),
        ],
        "liabilities": [
            ("Noninterest-bearing demand deposits", b("2000")),
            ("Interest checking (NOW)", b("2010")),
            ("Savings deposits", b("2020")),
            ("Money market deposits", b("2030")),
            ("Time deposits (CDs)", b("2040")),
            ("Brokered deposits", b("2050")),
            ("Total deposits", L.total_deposits(ledger)),
            ("FHLB advances", b("2100")),
            ("Fed funds purchased", b("2110")),
            ("Discount window", b("2120")),
            ("Subordinated debt", b("2200")),
            ("Accrued interest payable", b("2300")),
            ("Other liabilities", b("2400") + b("2500")),
        ],
        "equity": [
            ("Common stock and surplus", b("3000")),
            ("Preferred stock", b("3050")),
            ("Retained earnings", b("3100") + L.net_income_open(ledger)),
            ("Accumulated other comprehensive income", b("3200")),
        ],
        "total_assets": L.total_assets(ledger),
        "total_liabilities": L.total_liabilities(ledger),
        "total_equity": L.total_equity(ledger),
    }
    return bs


INCOME_LAYOUT = [
    ("Interest income", ["4000", "4010", "4020"]),
    ("Interest expense", ["5000", "5010", "5020"]),
    ("Net interest income", None),                      # computed
    ("Provision for credit losses", ["5150"]),
    ("Service charges on deposits", ["4100"]),
    ("Card interchange", ["4110"]),
    ("Wire and treasury management", ["4120"]),
    ("Trust and wealth management", ["4130"]),
    ("Mortgage banking", ["4160"]),
    ("Loan sales", ["4165", "-5185"]),
    ("Securities gains (losses)", ["4140", "-5180"]),
    ("Investment banking", ["4170"]),
    ("Other noninterest income", ["4150"]),
    ("Salaries and benefits", ["5100"]),
    ("Occupancy and equipment", ["5110"]),
    ("Technology", ["5120"]),
    ("Marketing", ["5130"]),
    ("FDIC assessment", ["5140"]),
    ("Fraud and operational losses", ["5160"]),
    ("Regulatory fines", ["5200"]),
    ("OREO and collection", ["5210"]),
    ("Amortization of intangibles", ["5220"]),
    ("Other expense", ["5170"]),
    ("Income tax expense", ["5190"]),
]


def _sum_codes(pl, codes):
    total = 0
    for c in codes:
        if c.startswith("-"):
            total -= pl.get(c[1:], 0)
        else:
            total += pl.get(c, 0)
    return total


def income_statement(state, months_back=3):
    """Aggregate the last N archived months (plus nothing open)."""
    ledger = state["bank"]["ledger"]
    months = ledger["months"][-months_back:] if months_back else []
    agg = {}
    for m in months:
        for code, amt in m["pl"].items():
            agg[code] = agg.get(code, 0) + amt
    return _layout_income(agg, [m["month"] for m in months])


def income_statement_mtd(state):
    """The open month, straight from un-closed I/X balances."""
    ledger = state["bank"]["ledger"]
    agg = {}
    for code, (_, t) in L.CHART.items():
        if t in ("I", "X"):
            agg[code] = L.display_balance(ledger, code)
    return _layout_income(agg, ["month to date"])


def _layout_income(agg, labels):
    out = {"period": labels, "lines": []}
    int_inc = _sum_codes(agg, ["4000", "4010", "4020"])
    int_exp = _sum_codes(agg, ["5000", "5010", "5020"])
    nii = int_inc - int_exp
    fee_inc = _sum_codes(agg, ["4100", "4110", "4120", "4130", "4150", "4160", "4165", "4170"])
    sec_gl = _sum_codes(agg, ["4140", "-5180"])
    provision = agg.get("5150", 0)
    opex = _sum_codes(agg, ["5100", "5110", "5120", "5130", "5140", "5160",
                            "5170", "5185", "5200", "5210", "5220"])
    tax = agg.get("5190", 0)
    pretax = nii - provision + fee_inc + sec_gl - opex
    net = pretax - tax
    out["lines"] = [
        ("Interest income", int_inc),
        ("Interest expense", -int_exp),
        ("NET INTEREST INCOME", nii),
        ("Provision for credit losses", -provision),
        ("Noninterest income", fee_inc),
        ("Securities gains (losses)", sec_gl),
        ("Noninterest expense", -opex),
        ("PRETAX INCOME", pretax),
        ("Income tax", -tax),
        ("NET INCOME", net),
    ]
    out["detail"] = [(label, _sum_codes(agg, codes)) for label, codes in INCOME_LAYOUT
                     if codes is not None]
    out["net_income"] = net
    out["nii"] = nii
    out["opex"] = opex
    out["fee_income"] = fee_inc
    return out


def compute_metrics(state):
    """Point-in-time + trailing metrics; called at each month close."""
    bank = state["bank"]
    ledger = bank["ledger"]
    from .loans import total_loans, npl_balance, yield_on_loans
    from .deposits import cost_of_deposits, uninsured_share
    from .regulation import capital_ratios, liquidity_ratio

    assets = L.total_assets(ledger)
    equity = L.total_equity(ledger)
    deposits = L.total_deposits(ledger)
    loans = total_loans(bank["loans"])
    npl = npl_balance(bank["loans"])
    oreo = ledger["balances"]["1550"]
    alw = L.allowance(ledger)

    last12 = ledger["months"][-12:]
    ni_12 = sum(m["net_income"] for m in last12)
    n = len(last12)
    # Do not invent a year rate from one January. Until six closed
    # months exist we report the actual window, not ×12, and the UI
    # must not quote it as ROA.
    earnings_ready = n >= 6
    if n == 0:
        scale = 1.0
        ni_ann = 0
    elif n < 6:
        scale = 1.0
        ni_ann = ni_12
    else:
        scale = 12 / n
        ni_ann = int(ni_12 * scale)

    agg = {}
    for m in last12:
        for code, amt in m["pl"].items():
            agg[code] = agg.get(code, 0) + amt
    int_inc = _sum_codes(agg, ["4000", "4010", "4020"]) * scale
    int_exp = _sum_codes(agg, ["5000", "5010", "5020"]) * scale
    fee_inc = _sum_codes(agg, ["4100", "4110", "4120", "4130", "4150", "4160", "4165", "4170"]) * scale
    opex = _sum_codes(agg, ["5100", "5110", "5120", "5130", "5140", "5160",
                            "5170", "5185", "5200", "5210", "5220"]) * scale
    ncos = 0  # tracked separately

    earning_assets = (loans + ledger["balances"]["1200"] + ledger["balances"]["1210"]
                      + ledger["balances"]["1100"] + ledger["balances"]["1010"])
    nim = (int_inc - int_exp) / max(1, earning_assets)
    eff = opex / max(1, (int_inc - int_exp) + fee_inc)
    roa = (ni_ann / max(1, assets)) if earnings_ready else None
    roe = (ni_ann / max(1, equity)) if earnings_ready else None
    ratios = capital_ratios(state)
    lr, liquid = liquidity_ratio(state)
    tbv = equity - ledger["balances"]["1600"]

    m = {
        "assets": assets, "equity": equity, "deposits": deposits, "loans": loans,
        "net_income_ttm": ni_ann,
        "nim": round(nim, 5), "efficiency": round(eff, 4),
        "roa": None if roa is None else round(roa, 5),
        "roe": None if roe is None else round(roe, 5),
        "cost_of_funds": round(cost_of_deposits(state), 5),
        "yield_loans": round(yield_on_loans(bank["loans"]), 5),
        "npa_ratio": round((npl + oreo) / max(1, assets), 5),
        "reserve_coverage": round(alw / max(1, loans), 5),
        "loan_to_deposit": round(loans / max(1, deposits), 4),
        "uninsured_pct": uninsured_share(state),
        "tbv_per_share": tbv // max(1, bank["shares"]),
        "cet1_ratio": round(ratios["cet1_ratio"], 5),
        "leverage_ratio": round(ratios["leverage_ratio"], 5),
        "liquidity_ratio": round(lr, 4),
        "shares": bank["shares"],
        "partial_window": n < 6,
        "window_months": n,
        "earnings_ready": earnings_ready,
    }
    if earnings_ready:
        bank["roa_ttm"] = roa
        bank["roe_ttm"] = roe
    return m


def record_metrics(state):
    m = compute_metrics(state)
    m["month"] = state["time"]["date"][:7]
    state["metrics"].append(m)
    if len(state["metrics"]) > 2400:
        del state["metrics"][:len(state["metrics"]) - 2400]
    return m


def call_report(state):
    """Quarterly call report: a compact regulatory snapshot."""
    bs = balance_sheet(state)
    inc = income_statement(state, months_back=3)
    reg = state["regulation"]
    ratios = reg.get("last_ratios", {})
    from .loans import portfolio_stats
    return {
        "date": state["time"]["date"],
        "balance_sheet": bs,
        "income": inc,
        "capital": ratios,
        "camels": reg["camels"],
        "pca": reg["pca"],
        "cra": reg["cra"],
        "orders": reg["orders"],
        "portfolio": portfolio_stats(state),
    }


def cash_flow_statement(state, months_back=3):
    """Simplified statement of cash flows derived from ledger archives."""
    inc = income_statement(state, months_back)
    ni = inc["net_income"]
    # for a bank, operating ~ NI + provision + depreciation; investing = loans/securities delta;
    # financing = deposits/borrowings/capital delta. We approximate from metric history.
    hist = state["metrics"]
    if len(hist) >= months_back + 1:
        now, then = hist[-1], hist[-months_back - 1]
        d_loans = now["loans"] - then["loans"]
        d_deposits = now["deposits"] - then["deposits"]
    else:
        d_loans = d_deposits = 0
    return {
        "net_income": ni,
        "operating": ni,
        "investing_loans": -d_loans,
        "financing_deposits": d_deposits,
    }
