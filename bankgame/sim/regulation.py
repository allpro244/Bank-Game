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
        "fdic_special": 0.0,
        "seized": False,
        "stress_test_buffer": 0.0,
    }


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
    reg = state["regulation"]
    events = []

    # BSA/AML: program adequacy vs bank size and activity. In a small bank
    # ops staff double as the BSA function; big banks need dedicated FTEs.
    assets = bank["cached_assets"]
    need = max(0.5, (assets / 100 / 1_000_000_000) * 2.5)   # compliance FTE need per $B
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
    return events


def run_exam(state, rng):
    bank = state["bank"]
    reg = state["regulation"]
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

    comp_need = max(0.5, (assets / 100 / 1_000_000_000) * 2.5)
    comp_have = bank["ops"]["staff"]["compliance"]["count"] \
        + 0.35 * bank["ops"]["staff"]["ops"]["count"]
    M = 2
    if comp_have < comp_need * 0.5 or reg["bsa"]["score"] < 0.5:
        M += 1
    if bank["loans"]["auto_policy"] == "approve_ab":
        M += 0   # acceptable with analysts
        if bank["ops"]["staff"]["credit_analysts"]["count"] < 1:
            M += 1
    if len(reg["orders"]) > 0:
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
    report = _write_report(state, comps, composite, r, npa_ratio, lr, wd, rate_risk, cre_conc)
    reg["exam_reports"].append({"date": state["time"]["date"], "composite": composite,
                                "components": comps, "text": report})
    if len(reg["exam_reports"]) > 40:
        del reg["exam_reports"][0]
    tone = {1: "they are delighted", 2: "they are calm", 3: "they are watching",
            4: "they are not happy", 5: "they are taking the keys"}[composite]
    events.append({"type": "exam", "blocking": True,
                   "composite": composite,
                   "components": dict(comps),
                   "title": "EXAMINATION COMPLETE — Composite rating: %d" % composite,
                   "owner_title": "Report card: %d — %s" % (composite, tone),
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
                     "has been executed with the board. Address criticized items before the "
                     "next examination.")
    else:
        lines.append("The institution's condition is unsafe and unsound. A consent order is in "
                     "effect: capital distributions are PROHIBITED and asset growth is "
                     "RESTRICTED until ratings improve. Failure to comply will result in "
                     "further action, including receivership.")
    return "\n".join(lines)
