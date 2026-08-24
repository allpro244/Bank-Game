"""The advisor layer: plain-English health gauges, recommendation cards,
and the guided first year.

This module never changes the simulation on its own. It reads state and
emits (a) six traffic-light gauges with sentences, (b) advisor cards
whose "Do it" buttons carry the exact policy paths / actions the player
could set by hand, and (c) tutorial steps that auto-complete as the
player actually does things. Depth is untouched -- this is the CFO
walking into your office, not an autopilot.
"""

from . import ledger as L
from . import deposits as DEP
from . import loans as LN
from . import regulation as REG
from . import competitors as C
from . import securities as SEC
from . import funding as FUND

DISMISS_MONTHS = 6      # a dismissed card stays quiet this long
TUTORIAL_MAX_MONTHS = 18


def _fm(cents):
    return f"${cents // 100:,}"


def ensure(state):
    adv = state.setdefault("advisor", {})
    adv.setdefault("dismissed", {})
    adv.setdefault("tutorial", {"active": True, "acked": []})
    return adv


# ------------------------------------------------------------------ gauges

def gauges(state):
    """Six traffic lights. status: 'g' | 'y' | 'r'."""
    bank = state["bank"]
    econ = state["economy"]
    reg = state["regulation"]
    m = state["metrics"][-1] if state["metrics"] else {}
    out = []

    # 1. Earnings
    roa = m.get("roa", bank.get("roa_ttm", 0.01))
    eff = m.get("efficiency", 0.6)
    if roa >= 0.008:
        st, head = "g", "Making money"
    elif roa >= 0:
        st, head = "y", "Thin profits"
    else:
        st, head = "r", "Losing money"
    out.append({
        "key": "earnings", "label": "Earnings", "status": st, "head": head,
        "tab": "reports",
        "detail": ("Return on assets is %.2f%% over the last year (healthy banks earn "
                   "0.9-1.3%%). You spend %.0f cents to make each dollar of revenue.")
                  % (roa * 100, eff * 100)})

    # 2. Capital
    r = REG.capital_ratios(state)
    pca = REG.pca_category(r)
    if pca == "well" and r["cet1_ratio"] >= 0.09:
        st, head = "g", "Well cushioned"
    elif pca == "well":
        st, head = "y", "Cushion is thinning"
    else:
        st, head = "r", "Regulatory trouble"
    out.append({
        "key": "capital", "label": "Capital", "status": st, "head": head,
        "tab": "risk",
        "detail": ("Core capital is %.1f%% of risk-weighted assets (regulators want "
                   "6.5%%+ to call you 'well-capitalized'; comfortable is 9%%+). "
                   "Capital is what absorbs losses before depositors get hurt. "
                   "Status: %s-capitalized.") % (r["cet1_ratio"] * 100, pca)})

    # 3. Liquidity
    lr, liquid = REG.liquidity_ratio(state)
    rumor = state["crisis"]["rumor"]
    run = state["crisis"]["run_active"]
    if run or lr < 0.06:
        st, head = "r", ("RUN IN PROGRESS" if run else "Dangerously tight")
    elif lr < 0.11 or rumor > 0.25:
        st, head = "y", "Watch your cash"
    else:
        st, head = "g", "Plenty of cash"
    out.append({
        "key": "liquidity", "label": "Liquidity", "status": st, "head": head,
        "tab": "treasury",
        "detail": ("Cash and sellable securities are %.1f%% of assets (%s). Below "
                   "~8%% you're relying on borrowed money if depositors want theirs "
                   "back. Depositor nervousness: %.0f%%.")
                  % (lr * 100, _fm(liquid), rumor * 100)})

    # 4. Credit quality
    npa = m.get("npa_ratio", 0.0)
    alw = L.allowance(bank["ledger"])
    req = bank["loans"]["reserve_required"]
    if npa < 0.01:
        st, head = "g", "Loans performing"
    elif npa < 0.03:
        st, head = "y", "Some strain showing"
    else:
        st, head = "r", "Serious loan problems"
    out.append({
        "key": "credit", "label": "Loan book", "status": st, "head": head,
        "tab": "lending",
        "detail": ("%.2f%% of assets are bad loans and foreclosed property (under 1%% "
                   "is clean, over 3%% draws examiners). Your loss reserve is %s "
                   "against an estimated need of %s.")
                  % (npa * 100, _fm(alw), _fm(req))})

    # 5. Regulators
    camels = reg["camels"]["composite"]
    if camels <= 2 and not reg["orders"]:
        st, head = "g", "Examiners are calm"
    elif camels == 3 or reg["orders"]:
        st, head = "y", "On their watch list"
    else:
        st, head = "r", "Enforcement action"
    if camels >= 4:
        st = "r"
    out.append({
        "key": "regulators", "label": "Regulators", "status": st, "head": head,
        "tab": "risk",
        "detail": ("Your exam report card (CAMELS) is a %d on a 1-5 scale — 1-2 is "
                   "good, 4-5 means forced restrictions. Next exam in about %d "
                   "months.%s") % (camels, max(0, reg["months_to_exam"]),
                                   (" Active actions: " + "; ".join(reg["orders"]) + ".")
                                   if reg["orders"] else "")})

    # 6. Interest-rate risk
    aoci = -bank["ledger"]["balances"]["3200"]
    htm_un = bank.get("cached_htm_unrealized", 0)
    unreal = min(0, aoci) + min(0, htm_un)
    cet1 = max(1, r["cet1"])
    ratio = -unreal / cet1
    if ratio < 0.10:
        st, head = "g", "Rate risk contained"
    elif ratio < 0.30:
        st, head = "y", "Paper losses growing"
    else:
        st, head = "r", "The SVB trap"
    out.append({
        "key": "raterisk", "label": "Rate risk", "status": st, "head": head,
        "tab": "treasury",
        "detail": ("Your bonds are worth %s %s than you paid — paper %s equal to "
                   "%.0f%% of your capital. This is what killed Silicon Valley Bank: "
                   "big paper losses plus nervous uninsured depositors. Over 30%% "
                   "is the danger zone.")
                  % (_fm(abs(unreal)), "less" if unreal < 0 else "more",
                     "losses" if unreal < 0 else "gains", ratio * 100)})
    return out


# ------------------------------------------------------------------- cards

def cards(state):
    """Up to 4 prioritized advisor cards. Each action button carries the
    exact policy set / action the player could do by hand."""
    adv = ensure(state)
    econ = state["economy"]
    months = econ["months"]
    found = []
    for rule in _RULES:
        try:
            card = rule(state)
        except Exception:
            card = None   # a broken rule must never take down the UI
        if card is None:
            continue
        when = adv["dismissed"].get(card["id"])
        if when is not None and months - when < DISMISS_MONTHS and card["sev"] < 2:
            continue
        found.append(card)
    found.sort(key=lambda c: -c["sev"])
    return found[:4]


def dismiss(state, card_id):
    adv = ensure(state)
    adv["dismissed"][str(card_id)] = state["economy"]["months"]


def _card(cid, sev, title, text, learn, tab, actions):
    return {"id": cid, "sev": sev, "title": title, "text": text,
            "learn": learn, "tab": tab, "actions": actions}


def _set(label, path, value):
    return {"label": label, "steps": [{"kind": "set", "path": path, "value": value}]}


def _act(label, action, payload):
    return {"label": label, "steps": [{"kind": "action", "action": action,
                                       "payload": payload}]}


def _plan(label, steps):
    return {"label": label, "steps": steps}


# ---- individual rules (each returns a card dict or None) ----

def _r_run_defense(state):
    if not state["crisis"]["run_active"]:
        return None
    bank = state["bank"]
    cap = FUND.fhlb_capacity(state)
    draw = min(cap, int(L.total_deposits(bank["ledger"]) * 0.10))
    draw = (draw // 10_000_00) * 10_000_00
    cur = bank["deposits"]["offsets_bp"]["money_market"]
    steps = [{"kind": "set", "path": "deposits.offsets_bp.money_market", "value": 300}]
    if draw >= 100_000_00:
        steps.append({"kind": "action", "action": "take_fhlb",
                      "payload": {"amount": draw, "term": 6}})
    return _card(
        "run_defense", 2, "EMERGENCY: fight the run",
        "Depositors are pulling money. Two moves slow a run: pay up so leaving "
        "costs something (max out your money market offset), and pile up cash "
        "BEFORE you need it (draw %s from the FHLB now, while you still can). "
        "Selling securities and raising capital are the next resorts."
        % (_fm(draw) if draw >= 100_000_00 else "what you can"),
        "A run feeds on the belief that the last one out loses. Visible cash and "
        "top-of-market rates break that belief. Your money market offset is "
        "currently %+dbp." % cur,
        "treasury",
        [_plan("Do both now", steps)])


def _r_capital_repair(state):
    reg = state["regulation"]
    if reg["pca"] == "well":
        return None
    r = REG.capital_ratios(state)
    shortfall = int(max(0, 0.09 * r["rwa"] - r["cet1"]) * 1.1)
    amount = max(1_000_000_00, (shortfall // 50_000_00) * 50_000_00)
    return _card(
        "capital_repair", 2, "Raise capital before regulators force you to",
        "You are %s-capitalized. Below 'well-capitalized', doors close: no "
        "brokered deposits, no buybacks, and the next stop is forced "
        "restrictions. Selling about %s of new stock would restore a "
        "comfortable cushion. It's dilutive and it stings — less than a "
        "seizure does." % (reg["pca"], _fm(amount)),
        "Capital is the layer of your own money that absorbs losses before "
        "depositors are at risk. Regulators grade you on it constantly "
        "(see the Risk & Reg tab).",
        "treasury",
        [_act("Raise %s of common stock" % _fm(amount), "raise_common",
              {"amount": amount})])


def _r_deposit_lag(state):
    econ = state["economy"]
    eff = DEP.effective_rate(state, "money_market")
    lag = econ["mmf_rate"] - eff
    # paying somewhat under money funds is normal banking; the problem is
    # lagging AND visibly losing deposits
    hist = state["metrics"]
    if lag <= 0.011 or len(hist) < 4:
        return None
    if hist[-1]["deposits"] >= hist[-4]["deposits"] * 0.997:
        return None
    deps = state["bank"]["deposits"]
    cur = deps["offsets_bp"]["money_market"]
    bump = min(300, cur + max(25, int(round(lag * 10000 / 25)) * 25))
    t = DEP.totals(deps)
    mm_bal = t["money_market"]
    cost = int(mm_bal * (bump - cur) / 10000)
    return _card(
        "deposit_lag", 1, "Your money market rate is falling behind",
        "Money funds are paying %.2f%%; you pay %.2f%%. That gap is why rate-"
        "sensitive balances leave. Raising your money market offset to %+dbp "
        "would cost roughly %s a year in extra interest on current balances — "
        "compare that with what shrinking deposits cost you in lending capacity."
        % (econ["mmf_rate"] * 100, eff * 100, bump, _fm(cost)),
        "Money market and short CDs are 'hot money' — they chase yield fastest. "
        "Checking barely moves. This is deposit beta: your funding cost lags a "
        "rising market only as long as customers let it.",
        "deposits",
        [_set("Raise offset to %+dbp" % bump, "deposits.offsets_bp.money_market", bump)])


def _r_excess_cash(state):
    bank = state["bank"]
    ledger = bank["ledger"]
    assets = max(1, bank["cached_assets"])
    liquid = ledger["balances"]["1000"] + ledger["balances"]["1010"] + \
        ledger["balances"]["1100"]
    excess = liquid - int(assets * 0.12)
    if excess < max(1_500_000_00, int(assets * 0.06)):
        return None
    buy = (int(excess * 0.6) // 100_000_00) * 100_000_00
    if buy < 500_000_00:
        return None
    y3 = SEC.type_yield(state["economy"], "treasury", 3.0)
    ff = state["economy"]["fed_funds"]
    pickup = int(buy * max(0.0, y3 - (ff - 0.001)))
    return _card(
        "excess_cash", 1, "Idle cash is leaving money on the table",
        "You're holding %s of cash and overnight money earning roughly the Fed "
        "rate. Moving %s into 3-year Treasuries at %.2f%% picks up about %s a "
        "year with zero credit risk. Keep them AFS (sellable) and the tenor "
        "modest so a rate spike doesn't trap you." % (_fm(liquid), _fm(buy),
                                                      y3 * 100, _fm(pickup)),
        "Banks earn the spread between what assets yield and what deposits "
        "cost. Cash is safe but yields the least; bonds yield more but lose "
        "market value when rates rise. Duration is the dial (Treasury tab).",
        "treasury",
        [_act("Buy %s of 3y Treasuries (AFS)" % _fm(buy), "buy_security",
              {"type": "treasury", "tenor": 3.0, "par": buy, "cls": "AFS"})])


def _r_hire_lender(state):
    bank = state["bank"]
    cap = LN.lender_capacity(state)
    if cap <= 0:
        util = 2.0
    else:
        util = bank["loans"]["stats"].get("originated_mtd", 0) / cap
    if util < 0.88:
        return None
    lenders = bank["ops"]["staff"]["lenders"]
    sal = int(lenders["salary"] * bank["ops"]["salary_multiplier"])
    return _card(
        "hire_lender", 1, "Your lenders are maxed out",
        "Loan production is running at %.0f%% of what your %d lender%s can "
        "handle — demand you can't write is walking to competitors, and "
        "overworked lenders quit. Another lender costs about %s a year and "
        "typically produces several times that in interest income."
        % (util * 100, lenders["count"], "s" if lenders["count"] != 1 else "",
           _fm(sal)),
        "Lender headcount is a hard cap on monthly loan originations "
        "(Operations tab). Skill and morale scale each lender's capacity.",
        "ops",
        [_act("Hire a lender", "hire", {"role": "lenders", "count": 1})])


def _r_rate_risk(state):
    bank = state["bank"]
    r = REG.capital_ratios(state)
    aoci = -bank["ledger"]["balances"]["3200"]
    unreal = min(0, aoci) + min(0, bank.get("cached_htm_unrealized", 0))
    ratio = -unreal / max(1, r["cet1"])
    if ratio < 0.20:
        return None
    par_total = sum(l["par"] for l in bank["securities"]["lots"])
    notional = (int(par_total * 0.5) // 100_000_00) * 100_000_00
    if notional < 1_000_000_00:
        return None
    return _card(
        "rate_risk", 2 if ratio > 0.35 else 1,
        "Paper losses on bonds are eating your capital",
        "Unrealized bond losses are %s — %.0f%% of your core capital. If "
        "depositors ever force you to sell, paper becomes real. A pay-fixed "
        "swap on %s of notional profits when rates rise, offsetting further "
        "damage. (It also gives back some income if rates fall — that's the "
        "price of sleeping at night.)" % (_fm(-unreal), ratio * 100, _fm(notional)),
        "This exact combination — long bonds bought at low rates, plus "
        "uninsured depositors who noticed — is how Silicon Valley Bank died "
        "in 2023. The gauge to watch is 'unrealized vs capital' on Risk & Reg.",
        "treasury",
        [_act("Hedge with a %s pay-fixed swap" % _fm(notional), "add_hedge",
              {"kind": "pay_fixed_swap", "notional": notional, "tenor": 3})])


def _r_late_cycle(state):
    econ = state["economy"]
    if econ["credit_boom"] < 0.85:
        return None
    cfg = state["bank"]["loans"]
    loose = [p for p in LN.PRODUCTS
             if cfg["standards"].get(p, 2) <= 1 and p in state["bank"]["products_enabled"]]
    if not loose:
        return None
    steps = [{"kind": "set", "path": "loans.standards.%s" % p, "value": 3}
             for p in loose]
    return _card(
        "late_cycle", 1, "The credit party is getting loud — tighten up",
        "Credit conditions look frothy (boom index %.2f — busts start above "
        "~0.6 territory and we're well past it). Your standards on %s are set "
        "loose. Loans written NOW with loose standards are the ones that "
        "default in the bust. Tightening costs volume today and saves your "
        "bank in two years." % (econ["credit_boom"], ", ".join(loose)),
        "Every loan pool remembers the underwriting standards in force when "
        "it was written ('vintage quality'). 2006 vintages ruined banks in "
        "2008. The boom index is on the Markets tab charts.",
        "lending",
        [_plan("Tighten %s to 'Tight'" % ", ".join(loose), steps)])


def _r_recession_cre(state):
    econ = state["economy"]
    if not (econ["recession"] or econ["credit_stress"] > 0.35):
        return None
    cfg = state["bank"]["loans"]
    risky = [p for p in ("construction", "cre")
             if p in state["bank"]["products_enabled"]
             and cfg["standards"].get(p, 2) < 3]
    if not risky:
        return None
    steps = [{"kind": "set", "path": "loans.standards.%s" % p, "value": 3}
             for p in risky]
    return _card(
        "recession_cre", 1, "Recession: protect the construction/CRE book",
        "The economy has turned (credit stress %.0f%%). Construction and "
        "commercial real estate are the first loans to go bad in a downturn — "
        "half-finished buildings don't make payments. Your standards on %s "
        "are still set for good times." % (econ["credit_stress"] * 100,
                                           " and ".join(risky)),
        "Construction loans carry a 150%% regulatory risk weight for a "
        "reason. In the simulation their default rates multiply during "
        "credit stress, exactly as in 2008-2010.",
        "lending",
        [_plan("Tighten %s" % " and ".join(risky), steps)])


def _r_bsa_weak(state):
    reg = state["regulation"]
    if reg["bsa"]["score"] >= 0.6:
        return None
    bank = state["bank"]
    assets = bank["cached_assets"]
    spend = max(reg["bsa"]["program_spend"], int(assets * 0.000005))
    spend = max(2_000_00, (spend // 1_000_00) * 1_000_00)
    return _card(
        "bsa_weak", 2 if reg["bsa"]["weak_months"] > 6 else 1,
        "Your anti-money-laundering program is failing",
        "BSA/AML program score is %.0f%% (%d weak months so far). This is the "
        "one every banker learns the hard way: underinvest for years and the "
        "fine has nine figures in it, plus a consent order that freezes "
        "acquisitions. Fix: a dedicated compliance officer and a budget of "
        "about %s/month at your size." % (reg["bsa"]["score"] * 100,
                                          reg["bsa"]["weak_months"], _fm(spend)),
        "Banks must know their customers, monitor transactions, and file "
        "suspicious-activity reports. Examiners grade the PROGRAM, not just "
        "outcomes — see the Risk & Reg tab.",
        "risk",
        [_plan("Hire compliance + fund the program",
               [{"kind": "action", "action": "hire",
                 "payload": {"role": "compliance", "count": 1}},
                {"kind": "set", "path": "regulation.bsa.program_spend",
                 "value": spend}])])


def _r_fraud_weak(state):
    bank = state["bank"]
    det = bank["fraud"].get("detection", 0.6)
    if det >= 0.45:
        return None
    assets = bank["cached_assets"]
    spend = max(3_000_00, (int(assets * 0.001 / 12 * 1.2) // 1_000_00) * 1_000_00)
    return _card(
        "fraud_weak", 1, "Fraudsters are winning",
        "Your fraud detection rate is %.0f%% — the criminals keep the rest. "
        "Losses scale with your size, and the big one (a spoofed wire) can be "
        "six figures in one afternoon. Raising prevention spend to about "
        "%s/month gets detection back toward 70%%." % (det * 100, _fm(spend)),
        "Detection depends on spend, ops/IT staffing, and thresholds. "
        "Tighter thresholds catch more but annoy good customers — that "
        "trade-off is yours to set on Risk & Reg.",
        "risk",
        [_set("Raise prevention to %s/mo" % _fm(spend),
              "fraud.prevention_spend", spend)])


def _r_core_old(state):
    ops = state["bank"]["ops"]
    if ops["core_system_age"] <= 8:
        return None
    return _card(
        "core_old", 1, "Your core system is a museum piece",
        "The core banking system is %.0f years old. Past 8 years the outage "
        "risk climbs every month — a two-day outage costs money, customers, "
        "and a headline that nervous depositors will read. Replace it on your "
        "schedule, not its schedule." % ops["core_system_age"],
        "The core system processes every account and transaction. Replacing "
        "it costs roughly 0.4%% of assets (Operations tab) and resets the "
        "clock.",
        "ops",
        [_act("Replace the core system", "upgrade_core", {})])


def _r_brand_decay(state):
    bank = state["bank"]
    ops = bank["ops"]
    home = ops["brand"].get("caprock")
    if home is None or home >= 14 or ops["marketing"].get("caprock", 0) > 500_00:
        return None
    return _card(
        "brand_decay", 0, "Nobody remembers your name",
        "Brand strength in your home market has decayed to %.0f/100 and "
        "you're spending almost nothing on marketing. Brand quietly drives "
        "both deposit gathering and loan demand. A modest $3,000/month "
        "rebuilds it in a small market." % home,
        "Brand decays about 1.2%% per month without spend, and marketing has "
        "diminishing returns — small towns are cheap, metros are not "
        "(Operations tab).",
        "ops",
        [_set("Spend $3,000/mo in the home market", "ops.marketing.caprock", 3_000_00)])


def _r_hoarding(state):
    bank = state["bank"]
    reg = state["regulation"]
    m = state["metrics"][-1] if state["metrics"] else None
    if m is None:
        return None
    ea = m["equity"] / max(1, m["assets"])
    payout = bank["policies"]["dividend_payout"]
    if ea < 0.16 or payout > 40 or reg["pca"] != "well" or \
            reg["camels"]["composite"] > 2 or m.get("roe", 0) > 0.10:
        return None
    return _card(
        "hoarding", 0, "You're sitting on a pile of idle capital",
        "Equity is %.0f%% of assets — roughly double what a safe bank needs — "
        "and your return on equity is only %.1f%%. Idle capital makes owners "
        "poor. Either put it to work (grow: branches, lenders, acquisitions) "
        "or give it back (raise the dividend payout toward 50%%, or buy back "
        "stock on the Treasury tab)." % (ea * 100, m.get("roe", 0) * 100),
        "ROA measures the bank; ROE measures the owner. A fortress balance "
        "sheet with no plan is a savings account with overhead.",
        "treasury",
        [_set("Raise dividend payout to 50%", "policies.dividend_payout", 50)])


def _r_funding_stretch(state):
    m = state["metrics"][-1] if state["metrics"] else None
    if m is None or m.get("loan_to_deposit", 0) < 1.15:
        return None
    deps = state["bank"]["deposits"]
    steps = []
    for p in ("money_market", "cd_1y"):
        cur = deps["offsets_bp"][p]
        if cur < 250:
            steps.append({"kind": "set", "path": "deposits.offsets_bp.%s" % p,
                          "value": min(300, cur + 50)})
    if not steps:
        return None
    return _card(
        "funding_stretch", 1, "Your loans have outrun your deposits",
        "Loans are %.0f%% of deposits. Past ~105%% you're funding growth with "
        "borrowed money, which is expensive, flighty, and what examiners "
        "flag first. Cheapest fix: win more deposits — pay up 50bp on money "
        "market and 1-year CDs." % (m["loan_to_deposit"] * 100),
        "Core deposits are the franchise: sticky, cheap, and they don't get "
        "margin-called. Wholesale funding disappears exactly when you need "
        "it (see Wholesale dependence on Risk & Reg).",
        "deposits",
        [_plan("Pay up +50bp for deposits", steps)])


def _r_uninsured_watch(state):
    unins = DEP.uninsured_share(state)
    lr, _ = REG.liquidity_ratio(state)
    if unins < 0.35 or lr > 0.12:
        return None
    return _card(
        "uninsured_watch", 1, "Big depositors + thin cash = run fuel",
        "%.0f%% of your deposits are over the $250k insurance limit, and "
        "liquid assets are only %.1f%% of assets. Insured depositors sleep "
        "through a crisis; uninsured ones run at the first headline. Build "
        "the cash buffer, spread large deposits, or accept that one bad "
        "quarter could start a stampede." % (unins * 100, lr * 100),
        "The 2023 runs (SVB, First Republic) were uninsured-deposit runs "
        "moving at phone speed. Your rumor gauge on Risk & Reg tracks the "
        "same dynamics.",
        "risk", [])


def _r_exam_prep(state):
    reg = state["regulation"]
    if reg["months_to_exam"] > 3:
        return None
    g = {x["key"]: x for x in gauges(state)}
    weak = [x["label"] for x in g.values() if x["status"] != "g"
            and x["key"] in ("capital", "liquidity", "credit", "raterisk")]
    if not weak:
        return None
    return _card(
        "exam_prep", 1, "Examiners arrive in ~%d months" % max(1, reg["months_to_exam"]),
        "Your weak spots right now: %s. Exam ratings are backward-looking — "
        "what they see on arrival day is what goes in the report, and a bad "
        "report brings restrictions that last years. Shore these up first."
        % ", ".join(weak),
        "CAMELS = Capital, Asset quality, Management, Earnings, Liquidity, "
        "Sensitivity to rates. Each is graded 1-5 from your actual numbers "
        "(Risk & Reg shows the components).",
        "risk", [])


_RULES = [
    _r_run_defense, _r_capital_repair, _r_rate_risk, _r_bsa_weak,
    _r_deposit_lag, _r_funding_stretch, _r_late_cycle, _r_recession_cre,
    _r_hire_lender, _r_excess_cash, _r_uninsured_watch, _r_exam_prep,
    _r_fraud_weak, _r_core_old, _r_brand_decay, _r_hoarding,
]


# ---------------------------------------------------------------- tutorial

def tutorial(state):
    adv = ensure(state)
    t = adv["tutorial"]
    econ = state["economy"]
    bank = state["bank"]
    acked = set(t["acked"])

    total_staff = sum(s["count"] for s in bank["ops"]["staff"].values())
    stats = bank["loans"]["stats"]
    steps = [
        {"id": "welcome", "title": "Get the lay of the land",
         "text": "Look at the six health lights above — click any of them to see "
                 "the full picture behind it. Green means sleep well. Then come "
                 "back and mark this done.",
         "done": "welcome" in acked, "tab": "desk"},
        {"id": "deposits", "title": "Take a stance on deposit pricing",
         "text": "Open the Deposits tab. Your rates track the market; your lever "
                 "is the OFFSET. Try +25bp on money market to grow, or leave a "
                 "product at 0 to match. Any change completes this step.",
         "done": any(v != 0 for v in bank["deposits"]["offsets_bp"].values())
                 or "deposits" in acked, "tab": "deposits"},
        {"id": "memo", "title": "Decide a loan yourself",
         "text": "Big loan requests come to your desk with a credit memo — "
                 "borrower, coverage ratio, collateral, an analyst's note. Read "
                 "one and approve or decline it. (They appear in the inbox below "
                 "and on the Lending tab; one shows up most months.)",
         "done": (stats["approved_apps"] + stats["declined_apps"]) > 0
                 or "memo" in acked, "tab": "lending"},
        {"id": "bonds", "title": "Put idle cash to work",
         "text": "Excess cash earns almost nothing. On the Treasury tab, buy at "
                 "least $500k of Treasuries (keep them AFS and 2-5 years — "
                 "long bonds are a bet on rates, not a parking spot).",
         "done": bank["securities"]["next_id"] > 5 or "bonds" in acked,
         "tab": "treasury"},
        {"id": "people", "title": "Meet your people",
         "text": "Three employees run this bank, and your single lender caps "
                 "how much you can lend each month. Hire one more person in any "
                 "role when you're ready to grow.",
         "done": total_staff > 3 or "people" in acked, "tab": "ops"},
        {"id": "exam", "title": "Survive your first examination",
         "text": "Examiners visit roughly every 14 months and grade you 1-5 on "
                 "capital, loans, management, earnings, liquidity, and rate "
                 "risk. Keep the health lights green and this takes care of "
                 "itself.",
         "done": len(state["regulation"]["exam_reports"]) > 0, "tab": "risk"},
    ]
    all_done = all(s["done"] for s in steps)
    active = t["active"] and not all_done and econ["months"] <= TUTORIAL_MAX_MONTHS
    return {"active": active, "steps": steps, "all_done": all_done}


def ack_step(state, step_id):
    adv = ensure(state)
    if step_id not in adv["tutorial"]["acked"]:
        adv["tutorial"]["acked"].append(step_id)


def tutorial_off(state):
    ensure(state)["tutorial"]["active"] = False


# ------------------------------------------------- constants for previews

def model_constants():
    """Sensitivities the UI uses for live 'what will this do' previews.
    Served from here so the client can never drift from the engine."""
    return {
        "dep_sens": DEP.SENS,
        "dep_speed": DEP.SPEED,
        "loan_price_k": 0.55,          # exp(-bp/100bp * k) volume multiplier
        "tight_mult": [1.30, 1.115, 0.93, 0.745, 0.56],
        "tier_mix": {str(k): v for k, v in LN.TIER_MIX.items()},
        "quality": [1.45, 1.25, 1.05, 0.85, 0.65],
        "fee_norm": 800,
        "od_annoyance_per_1000": 0.01,  # per $10 over $30
        "brand_gain_base": 9000.0,
    }


def peer_averages(state):
    peers = C.peer_group(state)
    if not peers:
        return None
    n = len(peers)
    return {
        "roa": sum(b["roa"] for b in peers) / n,
        "nim": sum(b["nim"] for b in peers) / n,
        "efficiency": sum(b["efficiency"] for b in peers) / n,
        "npa_ratio": sum(b["npa_ratio"] for b in peers) / n,
        "equity_ratio": sum(b["equity_ratio"] for b in peers) / n,
        "n": n,
    }
