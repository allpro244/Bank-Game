"""Double-entry general ledger.

Rules that hold everywhere, no exceptions:
  * All monetary amounts are INTEGER CENTS.
  * Every posting balances: sum of debits == sum of credits.
  * Account balances are stored as (debits - credits), so the invariant
    "the books balance" is simply: sum of all account balances == 0.
  * Income/expense accounts accumulate during a month and are closed to
    Retained Earnings at month end; the closed month is archived so
    financial statements can always be rebuilt.

Display convention: asset/expense accounts are debit-normal (shown as
stored), liability/equity/income accounts are credit-normal (shown
negated).
"""

# ---- Chart of accounts ----------------------------------------------------
# code: (name, type)  type in {A, L, Q, I, X}  (Q=equity, I=income, X=expense)
CHART = {
    # Assets
    "1000": ("Cash and due from banks", "A"),
    "1010": ("Interest-bearing balances at Fed", "A"),
    "1100": ("Fed funds sold", "A"),
    "1200": ("Securities available-for-sale", "A"),
    "1210": ("Securities held-to-maturity", "A"),
    "1300": ("Loans, gross", "A"),
    "1350": ("Allowance for credit losses", "A"),   # contra-asset (credit balance)
    "1400": ("Accrued interest receivable", "A"),
    "1500": ("Premises and equipment", "A"),
    "1550": ("Other real estate owned", "A"),
    "1600": ("Goodwill and intangibles", "A"),
    "1700": ("Other assets", "A"),
    # Liabilities
    "2000": ("Noninterest-bearing demand deposits", "L"),
    "2010": ("Interest checking (NOW)", "L"),
    "2020": ("Savings deposits", "L"),
    "2030": ("Money market deposits", "L"),
    "2040": ("Time deposits (CDs)", "L"),
    "2050": ("Brokered deposits", "L"),
    "2100": ("FHLB advances", "L"),
    "2110": ("Fed funds purchased", "L"),
    "2120": ("Discount window borrowings", "L"),
    "2200": ("Subordinated debt", "L"),
    "2300": ("Accrued interest payable", "L"),
    "2400": ("Other liabilities", "L"),
    "2500": ("Income tax payable", "L"),
    # Equity
    "3000": ("Common stock and surplus", "Q"),
    "3050": ("Preferred stock", "Q"),
    "3100": ("Retained earnings", "Q"),
    "3200": ("Accumulated other comprehensive income", "Q"),
    # Income
    "4000": ("Interest and fees on loans", "I"),
    "4010": ("Interest on securities", "I"),
    "4020": ("Interest on cash and fed funds sold", "I"),
    "4100": ("Service charges on deposits", "I"),
    "4110": ("Card interchange income", "I"),
    "4120": ("Wire, ACH and treasury mgmt fees", "I"),
    "4130": ("Trust and wealth management fees", "I"),
    "4140": ("Gains on securities sold", "I"),
    "4150": ("Other noninterest income", "I"),
    "4160": ("Mortgage banking income", "I"),
    "4170": ("Investment banking and capital markets", "I"),
    # Expense
    "5000": ("Interest on deposits", "X"),
    "5010": ("Interest on borrowings", "X"),
    "5020": ("Interest on subordinated debt", "X"),
    "5100": ("Salaries and benefits", "X"),
    "5110": ("Occupancy and equipment", "X"),
    "5120": ("Technology and data processing", "X"),
    "5130": ("Marketing and business development", "X"),
    "5140": ("FDIC insurance assessment", "X"),
    "5150": ("Provision for credit losses", "X"),
    "5160": ("Fraud and operational losses", "X"),
    "5170": ("Other operating expense", "X"),
    "5180": ("Losses on securities sold", "X"),
    "5190": ("Income tax expense", "X"),
    "5200": ("Regulatory fines and penalties", "X"),
    "5210": ("OREO and collection expense", "X"),
    "5220": ("Amortization of intangibles", "X"),
}

DEPOSIT_ACCOUNTS = ["2000", "2010", "2020", "2030", "2040", "2050"]
BORROWING_ACCOUNTS = ["2100", "2110", "2120"]

ENTRY_LOG_CAP = 6000  # most recent journal entries retained for drill-down


class LedgerError(Exception):
    pass


def new_ledger():
    return {
        "balances": {code: 0 for code in CHART},   # debits - credits, cents
        "entries": [],                              # recent journal entries
        "entry_seq": 0,
        "months": [],   # archived month closes: {"month": "2000-01", "pl": {code: amount}, "net_income": int}
        "mtd": {},      # not used; MTD read directly from I/X balances
    }


def post(ledger, date, memo, lines, tag=""):
    """Post a journal entry.

    lines: list of (account_code, debit_cents, credit_cents) with ints.
    Zero-amount lines are dropped. Raises LedgerError if unbalanced.
    """
    total_dr = 0
    total_cr = 0
    clean = []
    for code, dr, cr in lines:
        if code not in CHART:
            raise LedgerError("unknown account %s" % code)
        if not (isinstance(dr, int) and isinstance(cr, int)):
            raise LedgerError("non-integer amount in %s: %r/%r" % (code, dr, cr))
        if dr < 0 or cr < 0:
            raise LedgerError("negative amount in %s" % code)
        if dr == 0 and cr == 0:
            continue
        total_dr += dr
        total_cr += cr
        clean.append([code, dr, cr])
    if total_dr != total_cr:
        raise LedgerError(
            "unbalanced entry '%s': dr=%d cr=%d" % (memo, total_dr, total_cr))
    if not clean:
        return None
    for code, dr, cr in clean:
        ledger["balances"][code] += dr - cr
    ledger["entry_seq"] += 1
    entry = {"id": ledger["entry_seq"], "date": date, "memo": memo,
             "tag": tag, "lines": clean}
    ledger["entries"].append(entry)
    if len(ledger["entries"]) > ENTRY_LOG_CAP:
        del ledger["entries"][:len(ledger["entries"]) - ENTRY_LOG_CAP]
    return entry


def trial_balance(ledger):
    """Returns sum of all balances; must be exactly 0."""
    return sum(ledger["balances"].values())


def display_balance(ledger, code):
    """Balance in the account's natural sign (positive = normal)."""
    bal = ledger["balances"][code]
    if CHART[code][1] in ("A", "X"):
        return bal
    return -bal


def balances_view(ledger):
    return {code: display_balance(ledger, code) for code in CHART}


def total_assets(ledger):
    return sum(ledger["balances"][c] for c, (_, t) in CHART.items() if t == "A")


def total_liabilities(ledger):
    return -sum(ledger["balances"][c] for c, (_, t) in CHART.items() if t == "L")


def total_equity(ledger):
    """Book equity including income/expense not yet closed."""
    q = -sum(ledger["balances"][c] for c, (_, t) in CHART.items() if t == "Q")
    return q + net_income_open(ledger)


def net_income_open(ledger):
    """Net income accumulated in open (un-closed) income/expense accounts."""
    inc = -sum(ledger["balances"][c] for c, (_, t) in CHART.items() if t == "I")
    exp = sum(ledger["balances"][c] for c, (_, t) in CHART.items() if t == "X")
    return inc - exp


def total_deposits(ledger):
    return -sum(ledger["balances"][c] for c in DEPOSIT_ACCOUNTS)


def total_loans_gross(ledger):
    return ledger["balances"]["1300"]


def allowance(ledger):
    return -ledger["balances"]["1350"]  # stored as credit balance


def close_month(ledger, month_label, date):
    """Close income/expense accounts to retained earnings; archive the month."""
    pl = {}
    lines = []
    net = 0
    for code, (_, t) in CHART.items():
        if t not in ("I", "X"):
            continue
        bal = ledger["balances"][code]
        if bal == 0:
            pl[code] = 0
            continue
        # natural amount for the archive
        pl[code] = -bal if t == "I" else bal
        # zero the account
        if bal > 0:
            lines.append([code, 0, bal])
        else:
            lines.append([code, -bal, 0])
        if t == "I":
            net += -bal
        else:
            net -= bal
    # offset to retained earnings
    if net > 0:
        lines.append(["3100", 0, net])
    elif net < 0:
        lines.append(["3100", -net, 0])
    if lines:
        post(ledger, date, "Month-end close %s" % month_label, lines, tag="close")
    ledger["months"].append({"month": month_label, "pl": pl, "net_income": net})
    if len(ledger["months"]) > 1200:  # 100 years of months
        del ledger["months"][:len(ledger["months"]) - 1200]
    return net


def audit(ledger):
    """Every-turn integrity check. Returns list of problem strings (empty = clean)."""
    problems = []
    tb = trial_balance(ledger)
    if tb != 0:
        problems.append("TRIAL BALANCE BROKEN: debits-credits = %d cents" % tb)
    if allowance(ledger) < 0:
        problems.append("Allowance for credit losses is negative")
    if display_balance(ledger, "1300") < 0:
        problems.append("Gross loans negative")
    for code in DEPOSIT_ACCOUNTS:
        if display_balance(ledger, code) < 0:
            problems.append("Deposit account %s negative" % code)
    return problems
