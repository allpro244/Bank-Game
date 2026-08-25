"""Regulation: capital ratios, prompt corrective action, CAMELS exams,
FDIC assessments, size thresholds, BSA/AML, CRA.

The examiners are a core antagonist. Slip below well-capitalized and
doors start closing (brokered deposits, buybacks). Draw a 4-rated exam
and you're under a consent order: dividends banned, growth capped. Let
tangible equity reach 2% of assets and the FDIC takes the keys.
"""

from . import ledger as L

RISK_WEIGHTS_LOANS = {
    "auto": 0.75, "mortgage": 0.50, "heloc": 0.75, "credit_card": 1.00,
    "small_business": 1.00, "ci": 1.00, "cre": 1.00, "construction": 1.50,
    "ag": 1.00, "sba": 0.50,   # SBA guaranteed portion
}
RISK_WEIGHTS_SEC = {"treasury": 0.0, "agency": 0.20, "mbs": 0.20,
                    "muni": 0.20, "corporate": 1.00}


def new_regulation():
    return {
        "camels": {"composite": 2, "C": 2, "A": 2, "M": 2, "E": 2, "L": 2, "S": 2},
        "pca": "well",
        "months_to_exam": 14,
        "orders": [],                # active enforcement actions (strings)
        "dividend_ban": False,
        "growth_cap_active": False,
        "durbin_capped": False,
        "enhanced_prudential": False,
        "lcr_required": False,
        "gsib": False,
        "bsa": {"program_spend": 2_000_00, "score": 0.8, "weak_months": 0,
                "sars_filed": 0, "ctrs_filed": 0, "fined": False},
        "cra": "Satisfactory",
        "exam_reports": [],
        "mras": [],                  # examiner matters requiring attention
        "next_mra_id": 1,
        "idle_letter_month": 0,
        "fdic_special": 0.0,
        "seized": False,
        "stress_test_buffer": 0.0,
    }


def ensure(state):
    """Old saves may lack MRA fields. No other mutation."""
    reg = state["regulation"]
    reg.setdefault("mras", [])
    reg.setdefault("next_mra_id", 1)
    return reg


def capital_ratios(state):
    bank = state["bank"]
    ledger = bank["ledger"]
    from .loans import portfolio_stats
    stats = portfolio_stats(state)
    rwa = 0
    for prod, d in stats.items():
        w = RISK_WEIGHTS_LOANS.get(prod, 1.0)
        perf = d["balance"] - d["npl"]
        rwa += int(perf * w) + int(d["npl"] * 1.5)
    for lot in bank["securities"]["lots"]:
        rwa += int(lot["mv"] * RISK_WEIGHTS_SEC[lot["type"]])
    rwa += int(ledger["balances"]["1100"] * 0.20)       # fed funds sold
    rwa += ledger["balances"]["1500"] + ledger["balances"]["1550"]
    rwa += ledger["balances"]["1700"] + int(ledger["balances"]["1400"] * 0.2)
    rwa = max(1, rwa)

    equity = L.total_equity(ledger)
    aoci = -ledger["balances"]["3200"]
    preferred = -ledger["balances"]["3050"]
    goodwill = ledger["balances"]["1600"]
    # AOCI opt-out for banks under $250B (like nearly all real banks)
    include_aoci = state["regulation"]["gsib"]
    cet1 = equity - preferred - goodwill - (0 if include_aoci else aoci)
    tier1 = cet1 + preferred
    subdebt = -ledger["balances"]["2200"]
    alw = L.allowance(ledger)
    total_cap = tier1 + min(subdebt, tier1 // 2) + min(alw, int(rwa * 0.0125))
    assets = L.total_assets(ledger)
    tangible_equity = equity - goodwill

    return {
        "rwa": rwa, "cet1": cet1, "tier1": tier1, "total": total_cap,
        "cet1_ratio": cet1 / rwa, "tier1_ratio": tier1 / rwa,
        "total_ratio": total_cap / rwa,
        "leverage_ratio": tier1 / max(1, assets),
        "tang_equity_ratio": tangible_equity / max(1, assets),
        "equity": equity, "assets": assets,
    }


def pca_category(r):
    if r["tang_equity_ratio"] <= 0.02:
        return "critical"
    if r["cet1_ratio"] >= 0.065 and r["tier1_ratio"] >= 0.08 and \
       r["total_ratio"] >= 0.10 and r["leverage_ratio"] >= 0.05:
        return "well"
    if r["cet1_ratio"] >= 0.045 and r["tier1_ratio"] >= 0.06 and \
       r["total_ratio"] >= 0.08 and r["leverage_ratio"] >= 0.04:
        return "adequate"
    if r["cet1_ratio"] >= 0.03:
        return "under"
    return "significant"


def liquidity_ratio(state):
    bank = state["bank"]
    ledger = bank["ledger"]
    liquid = (ledger["balances"]["1000"] + ledger["balances"]["1010"]
              + ledger["balances"]["1100"]
              + sum(l["mv"] for l in bank["securities"]["lots"] if l["cls"] == "AFS"))
    assets = max(1, L.total_assets(ledger))
    return liquid / assets, liquid


def wholesale_dependence(state):
    bank = state["bank"]
    ledger = bank["ledger"]
    wholesale = (-ledger["balances"]["2050"] - ledger["balances"]["2100"]
                 - ledger["balances"]["2110"] - ledger["balances"]["2120"])
    dep = max(1, L.total_deposits(ledger))
    return wholesale / (dep + wholesale) if wholesale > 0 else 0.0


def quarterly_update(state, rng):
    """Ratios, PCA, thresholds, FDIC premium. Returns events."""
    bank = state["bank"]
    reg = state["regulation"]
    econ = state["economy"]
    events = []
    r = capital_ratios(state)
    old_pca = reg["pca"]
    reg["pca"] = pca_category(r)
    reg["last_ratios"] = {k: (round(v, 5) if isinstance(v, float) else v)
                          for k, v in r.items()}

    if reg["pca"] == "critical":
        reg["seized"] = True
        events.append({"type": "seizure", "blocking": True,
                       "title": "SEIZED BY REGULATORS",
                       "text": ("Tangible equity fell to %.2f%% of assets — critically "
                                "undercapitalized. On Friday at close of business, examiners "
                                "walked into the lobby and the FDIC took receivership. "
                                "The %s is no more.") % (r["tang_equity_ratio"] * 100,
                                                         bank["name"])})
        return events

    if reg["pca"] != old_pca:
        events.append({"type": "pca_change", "blocking": True,
                       "title": "Capital category: %s → %s" % (old_pca.upper(), reg["pca"].upper()),
                       "text": _pca_text(reg["pca"])})

    # ---- size thresholds ----
    assets = r["assets"]
    if not reg["durbin_capped"] and assets > 10_000_000_000_00:
        reg["durbin_capped"] = True
        events.append({"type": "threshold", "blocking": True,
                       "title": "You crossed $10 billion",
                       "text": ("Welcome to the big leagues. The Durbin amendment now caps "
                                "your debit interchange (income drops roughly in half on that "
                                "line), and the CFPB is now your examiner for consumer "
                                "compliance. Expect higher compliance costs from here on.")})
    if not reg["enhanced_prudential"] and assets > 50_000_000_000_00:
        reg["enhanced_prudential"] = True
        events.append({"type": "threshold", "blocking": True,
                       "title": "You crossed $50 billion",
                       "text": ("Enhanced prudential standards now apply: annual supervisory "
                                "stress tests, a capital buffer requirement, resolution "
                                "planning. Your compliance bill just went up, permanently.")})
    if not reg["lcr_required"] and assets > 100_000_000_000_00:
        reg["lcr_required"] = True
        events.append({"type": "threshold", "blocking": True,
                       "title": "You crossed $100 billion",
                       "text": ("Liquidity coverage requirements now bind: you must hold "
                                "high-quality liquid assets against projected 30-day stress "
                                "outflows. Watch the liquidity panel; breaches bring findings.")})
    if not reg["gsib"] and assets > 250_000_000_000_00:
        reg["gsib"] = True
        events.append({"type": "threshold", "blocking": True,
                       "title": "You are now a G-SIB",
                       "text": ("At $250B+ you are a global systemically important bank. A "
                                "capital surcharge applies, AOCI now flows through regulatory "
                                "capital, and the Fed reads your emails. Congratulations?")})

    # ---- stress test buffer for large banks ----
    if reg["enhanced_prudential"]:
        sev = 0.01 + econ["credit_stress"] * 0.01
        reg["stress_test_buffer"] = round(0.025 + sev, 4)
        cost = int(assets * 0.00002)
        L.post(bank["ledger"], state["time"]["date"], "Stress testing and resolution planning",
               [["5170", cost, 0], ["1000", 0, cost]], tag="reg")

    # ---- FDIC assessment ----
    base = assets - max(0, r["equity"])
    camels = reg["camels"]["composite"]
    bp = {1: 3.5, 2: 5.0, 3: 12.0, 4: 25.0, 5: 40.0}[camels]
    if reg["pca"] != "well":
        bp += 6.0
    bp += reg["fdic_special"]
    premium = int(base * bp / 10000 / 4)
    if premium > 0:
        L.post(bank["ledger"], state["time"]["date"],
               "FDIC assessment (%.1fbp annualized)" % bp,
               [["5140", premium, 0], ["1000", 0, premium]], tag="reg")
    # special assessments after industry crises
    if econ["credit_stress"] > 0.55 and rng.chance(0.15):
        reg["fdic_special"] = 4.0
    elif reg["fdic_special"] > 0 and econ["credit_stress"] < 0.2:
        reg["fdic_special"] = 0.0

    # ---- LCR check ----
    if reg["lcr_required"]:
        lr, _ = liquidity_ratio(state)
        if lr < 0.10:
            events.append({"type": "lcr_breach", "blocking": False,
                           "title": "Liquidity coverage shortfall",
                           "text": "HQLA is below required coverage of stress outflows. "
                                   "Examiners have issued a matter requiring attention."})
    return events


def _pca_text(pca):
    return {
        "well": "You are well-capitalized again. All powers restored.",
        "adequate": ("Adequately capitalized: you may no longer accept brokered deposits "
                     "without a waiver, and deposit rate caps can apply. Rebuild capital."),
        "under": ("UNDERCAPITALIZED: growth restrictions apply, dividends are prohibited, "
                  "and you must file a capital restoration plan. Regulators can remove "
                  "officers. This is serious."),
        "significant": ("SIGNIFICANTLY UNDERCAPITALIZED: mandatory recapitalization or sale. "
                        "Seizure is imminent if capital falls further."),
        "critical": "Critically undercapitalized.",
    }[pca]


# ------------------------------------------------------------------- exams

def monthly_update(state, rng):
    """Exam countdown + BSA/AML program health."""
    bank = state["bank"]
    reg = ensure(state)
    events = []

    # BSA/AML spend is a real monthly bill, not a free slider.
    spend = int(reg["bsa"].get("program_spend") or 0)
    if spend > 0:
        from .funding import ensure_cash
        ensure_cash(state, spend)
        L.post(bank["ledger"], state["time"]["date"], "BSA/AML program",
               [["5170", spend, 0], ["1000", 0, spend]], tag="reg")

    # BSA/AML: program adequacy vs bank size and activity. In a small bank
    # ops staff double as the BSA function; big banks need dedicated FTEs.
    assets = max(1, bank.get("cached_assets") or 0)
    assets_b = assets / 100 / 1_000_000_000
    need = max(0.5, min(20.0, 0.55 + (max(0.0, assets_b) ** 0.55) * 1.15))
    have = bank["ops"]["staff"]["compliance"]["count"] \
        + 0.35 * bank["ops"]["staff"]["ops"]["count"]
    spend_ok = reg["bsa"]["program_spend"] >= assets * 0.000004
    score = min(1.0, 0.35 + 0.5 * min(1.5, have / need) + (0.15 if spend_ok else 0.0))
    reg["bsa"]["score"] = round(score, 3)
    reg["bsa"]["sars_filed"] += rng.poisson(0.5 + assets / 100 / 1_000_000_000 * 1.5)
    reg["bsa"]["ctrs_filed"] += rng.poisson(2 + assets / 100 / 1_000_000_000 * 8)
    if score < 0.6:
        reg["bsa"]["weak_months"] += 1
    else:
        reg["bsa"]["weak_months"] = max(0, reg["bsa"]["weak_months"] - 1)
    if reg["bsa"]["weak_months"] > 10 and rng.chance(0.06) and not reg["bsa"]["fined"]:
        fine = max(500_000_00, int(assets * 0.008))
        reg["bsa"]["fined"] = True
        reg["orders"].append("BSA/AML consent order")
        L.post(bank["ledger"], state["time"]["date"], "BSA/AML CIVIL MONEY PENALTY",
               [["5200", fine, 0], ["1000", 0, fine]], tag="reg")
        events.append({"type": "bsa_fine", "blocking": True,
                       "title": "BSA/AML enforcement action: $%s penalty" % f"{fine // 100:,}",
                       "text": ("Years of underinvestment in your anti-money-laundering "
                                "program caught up with you. FinCEN and your primary regulator "
                                "assessed a $%s civil money penalty and a consent order "
                                "requiring a program rebuild. Acquisitions are off the table "
                                "until it lifts. Staff up compliance and raise the BSA budget.")
                               % f"{fine // 100:,}"})
    if reg["bsa"]["fined"] and reg["bsa"]["score"] > 0.8 and rng.chance(0.05):
        reg["bsa"]["fined"] = False
        reg["orders"] = [o for o in reg["orders"] if "BSA" not in o]
        events.append({"type": "order_lifted", "blocking": False,
                       "title": "BSA consent order lifted",
                       "text": "Examiners validated your rebuilt AML program. The consent order is terminated."})

    reg["months_to_exam"] -= 1
    if reg["months_to_exam"] <= 0:
        events.extend(run_exam(state, rng))

    ev = _idle_capital_letter(state)
    if ev:
        events.append(ev)
    return events


def _idle_capital_letter(state):
    """Board / activist pulse when the owner is hoarding. At most every 18 months."""
    m = state["metrics"][-1] if state.get("metrics") else None
    if not m or not m.get("earnings_ready"):
        return None
    ea = m["equity"] / max(1, m["assets"])
    roe = m.get("roe")
    if roe is None or ea < 0.22 or roe > 0.08:
        return None
    if state["regulation"]["pca"] != "well":
        return None
    last = int(state["regulation"].get("idle_letter_month") or -99)
    mo = state["economy"]["months"]
    if mo - last < 18:
        return None
    state["regulation"]["idle_letter_month"] = mo
    payout = state["bank"]["policies"]["dividend_payout"]
    return {
        "type": "idle_capital", "blocking": True,
        "title": "The board wants the idle capital put to work",
        "text": ("Equity is %.0f%% of assets and trailing ROE is %.1f%%. "
                 "A fortress that does not grow or pay out is a savings "
                 "account with overhead. Dividend payout is %d%%. Raise it "
                 "toward 50%%, buy back stock, or put the money into offices "
                 "and loans. Sitting on it is how you lose the world race "
                 "without ever failing an exam."
                 % (ea * 100, roe * 100, payout)),
    }


# Orders this exam *writes* because of the composite. They must not
# grade Management next time — that is a self-sustaining trap.
SELF_ORDERS = (
    "Memorandum of understanding",
    "Consent order (safety & soundness)",
)


def independent_orders(reg):
    """Enforcement the player earned (BSA, etc.) — not the exam's own MOU/consent."""
    return [o for o in (reg.get("orders") or []) if o not in SELF_ORDERS]


def live_mras(reg):
    return [m for m in (reg.get("mras") or []) if m.get("status") in ("open", "missed")]


def missed_mra_outstanding(reg):
    return any(m.get("status") == "missed" for m in (reg.get("mras") or []))


def supervisory_metrics(state):
    """The numbers MRAs grade. Same formulas as the exam report. No mutation."""
    r = capital_ratios(state)
    from .loans import npl_balance
    npa = npl_balance(state["bank"]["loans"]) + state["bank"]["ledger"]["balances"]["1550"]
    assets = max(1, r["assets"])
    lr, _ = liquidity_ratio(state)
    htm_un = state["bank"].get("cached_htm_unrealized", 0)
    aoci = -state["bank"]["ledger"]["balances"]["3200"]
    rate_risk = -(min(0, htm_un) + min(0, aoci)) / max(1, r["cet1"])
    return {
        "liquidity_ratio": lr,
        "cet1_ratio": r["cet1_ratio"],
        "npa_ratio": npa / assets,
        "rate_risk": rate_risk,
        "roa_ttm": state["bank"].get("roa_ttm", 0.0),
        "bsa_score": state["regulation"]["bsa"]["score"],
    }


# Priority order. A 3+ exam writes at most two. A 1–2 writes none.
MRA_TEMPLATES = [
    {"kind": "liquidity", "comp": "L",
     "metric": "liquidity_ratio", "target": 0.10, "op": "gte",
     "text": "Raise liquid assets above 10 percent of total assets by the next examination.",
     "owner": "Cash and sellable bonds must be at least 10% of the book by the next visit."},
    {"kind": "capital", "comp": "C",
     "metric": "cet1_ratio", "target": 0.10, "op": "gte",
     "text": "Restore the CET1 capital ratio to at least 10.0 percent by the next examination.",
     "owner": "Core capital must be back above 10% of risk-weighted assets by the next visit."},
    {"kind": "npa", "comp": "A",
     "metric": "npa_ratio", "target": 0.015, "op": "lte",
     "text": "Reduce nonperforming assets to no more than 1.5 percent of total assets by the next examination.",
     "owner": "Bad loans and foreclosed property must be under 1.5% of assets by the next visit."},
    {"kind": "duration", "comp": "S",
     "metric": "rate_risk", "target": 0.15, "op": "lte",
     "text": "Reduce unrealized securities depreciation to no more than 15 percent of CET1 by the next examination.",
     "owner": "Paper losses on the bond book must be under 15% of capital by the next visit."},
    {"kind": "earnings", "comp": "E",
     "metric": "roa_ttm", "target": 0.009, "op": "gte",
     "need_earnings": True,
     "text": "Restore trailing return on assets to at least 0.90 percent by the next examination.",
     "owner": "A quiet year near 1% ROA. The next visit will check the trailing number."},
    {"kind": "bsa", "comp": "M",
     "metric": "bsa_score", "target": 0.75, "op": "gte",
     "text": "Raise the BSA/AML program score above 75 percent by the next examination.",
     "owner": "Staff compliance and fund the BSA program before they come back."},
]


def _mra_holds(item, metrics):
    val = metrics.get(item["metric"])
    if val is None:
        return False
    if item["op"] == "gte":
        return val + 1e-12 >= item["target"]
    return val <= item["target"] + 1e-12


def grade_open_mras(state):
    """Mark open/missed MRAs met or still missed. Returns items that changed."""
    ensure(state)
    metrics = supervisory_metrics(state)
    just = []
    for item in state["regulation"]["mras"]:
        if item["status"] not in ("open", "missed"):
            continue
        if _mra_holds(item, metrics):
            item["status"] = "met"
            item["resolved"] = state["time"]["date"]
            just.append(item)
        elif item["status"] == "open":
            item["status"] = "missed"
            item["resolved"] = state["time"]["date"]
            just.append(item)
    return just


def issue_mras(state, comps, composite):
    """After a 3+, write 1–2 items the player does not already meet.
    A 1 or 2 closes leftover open items and writes none."""
    ensure(state)
    reg = state["regulation"]
    if composite <= 2:
        for item in reg["mras"]:
            if item["status"] == "open":
                item["status"] = "closed"
                item["resolved"] = state["time"]["date"]
        return []
    live = live_mras(reg)
    live_kinds = {m["kind"] for m in live}
    slots = max(0, 2 - len(live))
    if slots <= 0:
        return []
    metrics = supervisory_metrics(state)
    mrow = state["metrics"][-1] if state.get("metrics") else {}
    issued = []
    for tmpl in MRA_TEMPLATES:
        if slots <= 0:
            break
        if tmpl["kind"] in live_kinds:
            continue
        if comps.get(tmpl["comp"], 2) < 3:
            continue
        if tmpl.get("need_earnings") and not mrow.get("earnings_ready"):
            continue
        if _mra_holds(tmpl, metrics):
            continue
        item = {
            "id": reg["next_mra_id"],
            "kind": tmpl["kind"],
            "metric": tmpl["metric"],
            "target": tmpl["target"],
            "op": tmpl["op"],
            "text": tmpl["text"],
            "owner": tmpl["owner"],
            "status": "open",
            "issued": state["time"]["date"],
            "due": "next examination",
        }
        reg["next_mra_id"] += 1
        reg["mras"].append(item)
        issued.append(item)
        slots -= 1
    return issued


def _trim_mras(reg):
    if len(reg["mras"]) <= 24:
        return
    live = live_mras(reg)
    done = [m for m in reg["mras"] if m.get("status") not in ("open", "missed")]
    keep = max(0, 24 - len(live))
    reg["mras"] = live + done[-keep:]


def run_exam(state, rng):
    bank = state["bank"]
    reg = ensure(state)
    econ = state["economy"]
    r = capital_ratios(state)
    from . import ledger as LL

    # --- component scores ---
    cr = r["cet1_ratio"]
    C = 1 if cr >= 0.13 else 2 if cr >= 0.10 else 3 if cr >= 0.075 else 4 if cr >= 0.05 else 5

    assets = max(1, r["assets"])
    from .loans import npl_balance, total_loans
    npa = npl_balance(bank["loans"]) + bank["ledger"]["balances"]["1550"]
    npa_ratio = npa / assets
    A = 1 if npa_ratio < 0.005 else 2 if npa_ratio < 0.015 else \
        3 if npa_ratio < 0.03 else 4 if npa_ratio < 0.055 else 5
    # CRE concentration adds risk
    from .loans import portfolio_stats
    stats = portfolio_stats(state)
    cre_bal = stats.get("cre", {}).get("balance", 0) + stats.get("construction", {}).get("balance", 0)
    cre_conc = cre_bal / max(1, r["total"])
    if cre_conc > 3.0:
        A = min(5, A + 1)

    mrow = state["metrics"][-1] if state.get("metrics") else {}
    if not mrow.get("earnings_ready"):
        # Do not invent a year rate from three quiet months (G2 / law 7).
        E = 2
    else:
        roa = bank.get("roa_ttm", 0.01)
        E = 1 if roa > 0.013 else 2 if roa > 0.009 else 3 if roa > 0.004 else 4 if roa > 0 else 5

    lr, _ = liquidity_ratio(state)
    wd = wholesale_dependence(state)
    window_uses = bank["funding"].get("discount_window_uses", 0)
    ldr = total_loans(bank["loans"]) / max(1, LL.total_deposits(bank["ledger"]))
    # Cash thinness alone is a 2, not a 4. L 3–4 is for decisions the
    # player made: window, wholesale, or running LDR hot.
    Lq = 1 if lr > 0.18 else 2 if lr > 0.10 else 3 if lr > 0.06 else 4 if lr > 0.04 else 5
    if window_uses == 0 and wd < 0.05 and ldr <= 1.05:
        Lq = min(Lq, 2)
    if window_uses >= 3:
        Lq = min(5, max(Lq, 3))
    if window_uses >= 8:
        Lq = min(5, max(Lq, 4))
    if wd > 0.15:
        Lq = min(5, Lq + 1)
    if ldr > 1.15:
        Lq = min(5, max(Lq, 3))
    if ldr > 1.30:
        Lq = min(5, Lq + 1)

    # sensitivity: HTM/AFS unrealized loss vs capital, duration
    htm_un = bank.get("cached_htm_unrealized", 0)
    aoci = -bank["ledger"]["balances"]["3200"]
    rate_risk = -(min(0, htm_un) + min(0, aoci)) / max(1, r["cet1"])
    S = 1 if rate_risk < 0.05 else 2 if rate_risk < 0.15 else \
        3 if rate_risk < 0.30 else 4 if rate_risk < 0.5 else 5

    # Compliance FTE need grows slower than assets. 2.5 per $1B made a
    # $50B bank "undermanaged" unless it hired a money-center BSA army.
    assets_b = assets / 100 / 1_000_000_000
    comp_need = max(0.5, min(20.0, 0.55 + (max(0.0, assets_b) ** 0.55) * 1.15))
    comp_have = bank["ops"]["staff"]["compliance"]["count"] \
        + 0.35 * bank["ops"]["staff"]["ops"]["count"]
    M = 2
    if comp_have < comp_need * 0.5 or reg["bsa"]["score"] < 0.5:
        M += 1
    if bank["loans"]["auto_policy"] == "approve_ab":
        M += 0   # acceptable with analysts
        if bank["ops"]["staff"]["credit_analysts"]["count"] < 1:
            M += 1
    # Grade outstanding MRAs before M so a miss is earned this visit,
    # not a leftover from the letter this exam is about to write.
    grade_open_mras(state)
    # Only independently earned orders grade M. The MOU/consent this
    # exam writes must not force the next composite. A missed MRA is
    # a real miss — not the MOU self-loop.
    if independent_orders(reg):
        M += 1
    if missed_mra_outstanding(reg):
        M += 1
    if bank["ops"]["audit_spend"] < assets * 0.0000015:
        M += 1
    M = max(1, min(5, M - (1 if bank["ops"]["staff"]["execs"]["count"] >= 2 and
                           bank["ops"]["staff"]["execs"]["skill"] >= 3 else 0)))

    comps = {"C": C, "A": A, "M": M, "E": E, "L": Lq, "S": S}
    avg = (0.24 * C + 0.22 * A + 0.14 * M + 0.14 * E + 0.14 * Lq + 0.12 * S)
    composite = int(round(avg))
    composite = max(composite, max(comps.values()) - 1)
    composite = max(1, min(5, composite))
    reg["camels"] = dict(comps, composite=composite)

    # --- consequences ---
    events = []
    was_banned = reg["dividend_ban"]
    if composite >= 4:
        reg["dividend_ban"] = True
        reg["growth_cap_active"] = True
        if "Consent order (safety & soundness)" not in reg["orders"]:
            reg["orders"].append("Consent order (safety & soundness)")
    elif composite == 3:
        reg["growth_cap_active"] = False
        reg["dividend_ban"] = False
        if "Memorandum of understanding" not in reg["orders"]:
            reg["orders"].append("Memorandum of understanding")
        reg["orders"] = [o for o in reg["orders"] if "Consent order (safety" not in o]
    else:
        reg["dividend_ban"] = False
        reg["growth_cap_active"] = False
        reg["orders"] = [o for o in reg["orders"]
                         if o not in ("Memorandum of understanding",
                                      "Consent order (safety & soundness)")]

    # CRA rating: community lending & presence
    ldr = total_loans(bank["loans"]) / max(1, LL.total_deposits(bank["ledger"]))
    rural_br = sum(1 for b in bank["ops"]["branches"]
                   if b["open"] and state["regions"][b["market"]]["kind"] in ("rural", "small_metro"))
    if ldr > 0.6 and rural_br >= 1:
        reg["cra"] = "Outstanding" if ldr > 0.8 else "Satisfactory"
    elif ldr > 0.45:
        reg["cra"] = "Satisfactory"
    else:
        reg["cra"] = "Needs to Improve"

    reg["months_to_exam"] = {1: 18, 2: 15, 3: 12, 4: 6, 5: 4}[composite]
    issue_mras(state, comps, composite)
    _trim_mras(reg)
    report = _write_report(state, comps, composite, r, npa_ratio, lr, wd, rate_risk, cre_conc)
    reg["exam_reports"].append({"date": state["time"]["date"], "composite": composite,
                                "components": comps, "text": report})
    if len(reg["exam_reports"]) > 40:
        del reg["exam_reports"][0]
    tone = {1: "they are delighted", 2: "they are calm", 3: "they are watching",
            4: "they are not happy", 5: "they are taking the keys"}[composite]
    if composite == 3:
        title = "EXAMINATION COMPLETE — Composite 3 (MOU: you can still grow)"
        owner_title = "Report card: 3 — they are watching. An MOU is not a freeze."
    elif composite >= 4:
        title = "EXAMINATION COMPLETE — Composite %d (CONSENT ORDER: growth capped)" % composite
        owner_title = "Report card: %d — %s. Growth is frozen until this moves." % (
            composite, tone)
    else:
        title = "EXAMINATION COMPLETE — Composite rating: %d" % composite
        owner_title = "Report card: %d — %s" % (composite, tone)
    events.append({"type": "exam", "blocking": True,
                   "composite": composite,
                   "components": dict(comps),
                   "title": title,
                   "owner_title": owner_title,
                   "owner_summary": (
                       "Capital %d · loans %d · management %d · earnings %d · "
                       "cash %d · rate risk %d."
                       % (comps["C"], comps["A"], comps["M"], comps["E"],
                          comps["L"], comps["S"])),
                   "text": report})
    return events


def _write_report(state, comps, composite, r, npa_ratio, lr, wd, rate_risk, cre_conc):
    bank = state["bank"]
    reg = state["regulation"]
    adj = {1: "strong", 2: "satisfactory", 3: "less than satisfactory",
           4: "deficient", 5: "critically deficient"}
    lines = [
        "REPORT OF EXAMINATION — %s" % bank["name"],
        "Examination date: %s   Composite rating: %d" % (state["time"]["date"], composite),
        "",
        "CAPITAL (%d): CET1 ratio %.2f%%, leverage %.2f%%. Capital is %s relative to the risk profile."
        % (comps["C"], r["cet1_ratio"] * 100, r["leverage_ratio"] * 100, adj[comps["C"]]),
        "ASSET QUALITY (%d): Nonperforming assets are %.2f%% of total assets. %s"
        % (comps["A"], npa_ratio * 100,
           ("CRE concentration of %.0f%% of total capital exceeds interagency guidance."
            % (cre_conc * 100)) if cre_conc > 3.0 else "Portfolio composition is within guidance."),
        "MANAGEMENT (%d): Board oversight and risk management are %s. %s"
        % (comps["M"], adj[comps["M"]],
           ("Active enforcement actions: " + "; ".join(reg["orders"]) + ".") if reg["orders"]
           else "No outstanding enforcement matters."),
        "EARNINGS (%d): Trailing return on assets of %.2f%% is %s."
        % (comps["E"], bank.get("roa_ttm", 0.0) * 100, adj[comps["E"]]),
        "LIQUIDITY (%d): Liquid assets are %.1f%% of total assets; wholesale funding dependence %.1f%%."
        % (comps["L"], lr * 100, wd * 100),
        "SENSITIVITY (%d): Unrealized securities depreciation equals %.0f%% of CET1 capital."
        % (comps["S"], rate_risk * 100),
        "",
    ]
    if composite <= 2:
        lines.append("The institution is fundamentally sound. Continue present policies.")
    elif composite == 3:
        lines.append("Weaknesses warrant supervisory attention. A memorandum of understanding "
                     "has been executed with the board. An MOU is not a consent order: "
                     "you may still open offices, hire, and bid. A 4 freezes growth. "
                     "Address criticized items before the next examination.")
    else:
        lines.append("The institution's condition is unsafe and unsound. A consent order is in "
                     "effect: capital distributions are PROHIBITED and asset growth is "
                     "RESTRICTED until ratings improve. Failure to comply will result in "
                     "further action, including receivership.")
    live = live_mras(reg)
    if live:
        lines.append("")
        lines.append("MATTERS REQUIRING ATTENTION:")
        for m in live:
            tag = "MISSED — " if m["status"] == "missed" else ""
            lines.append("  • %s%s" % (tag, m["text"]))
        lines.append("Missed items grade Management at the next examination. "
                     "Meeting them does not.")
    return "\n".join(lines)


COMP_OWNER = {
    "C": "Capital", "A": "Loan book", "M": "Management",
    "E": "Earnings", "L": "Cash", "S": "Rate risk",
}

# What number would move each component one grade, in owner language.
_RECOVERY = {
    "C": "Raise common (or shrink assets) until CET1 is back above 10%.",
    "A": "Work the criticized book and stop writing loose CRE / construction.",
    "M": "Staff compliance and fund BSA. An MOU written by this exam does not "
         "grade Management — only a BSA order or a real control failure does.",
    "E": "A quiet year of ~1% ROA. Hiring that loses money will not help.",
    "L": "Stop the window, pay down wholesale, and get LDR under 1.05.",
    "S": "Shorten the bond book or hedge. Unrealized losses vs CET1 are the tell.",
}


def exam_recovery_advice(state):
    """What would move a 3+ composite at the next exam. No mutation."""
    cam = state["regulation"].get("camels") or {}
    comps = {k: cam.get(k, 2) for k in "CAMELS"}
    composite = int(cam.get("composite") or 2)
    worst = max(comps, key=lambda k: comps[k])
    floor = comps[worst]
    actions = []
    for k, v in comps.items():
        if v >= 3:
            actions.append("%s is a %d — %s" % (COMP_OWNER[k], v, _RECOVERY[k]))
    for m in live_mras(state["regulation"]):
        tag = "Missed MRA: " if m.get("status") == "missed" else "MRA: "
        actions.append(tag + m.get("owner") or m.get("text") or "")
    return {
        "composite": composite,
        "components": comps,
        "floor": worst,
        "floor_grade": floor,
        "actions": actions,
        "needed": (
            "Composite is max(average, worst−1). The %s %d is the floor; "
            "fix that or the next exam stays a %d."
            % (COMP_OWNER[worst], floor, max(composite, floor - 1))),
    }
