"""Primary goal / scoring frame. Does not pause the sim."""

from . import ledger as L
from . import deposits as DEP
from .regulation import capital_ratios, pca_category

# G-SIB table in this model ($250B). You are not "in the world" until
# you sit there *and* you are larger than every living rival.
WORLD_CROWN = 250_000_000_000_00

GOAL_SPECS = {
    "world": {
        "label": "Biggest bank in the world",
        "blurb": "Pass every rival on the map, then pass $250 billion. Stay standing.",
    },
    "independent": {
        "label": "Stay independent 20 years",
        "blurb": "Decline buyouts. Do not get seized. Still standing in year 20.",
    },
    "square": {
        "label": "Best bank on the square",
        "blurb": "Home-market share, a calm report card, and ROA at or above peers after 10 years.",
    },
    "headline": {
        "label": "Don't be the next headline",
        "blurb": "Survive a credit bust and a rate shock with no run and no 4-rated exam.",
    },
    "regional": {
        "label": "Regional, not reckless",
        "blurb": "Grow to $500M–$2B, stay well-capitalized, keep a satisfactory CRA rating.",
    },
    "sell": {
        "label": "Sell well",
        "blurb": "Accept a buyout at 1.8× tangible book or better after year 8.",
    },
}

HOME_CHOICES = (
    ("caprock", "Caprock City, TX"),
    ("verhalen", "Verhalen, TX"),
    ("plainview", "Plainview, TX"),
    ("lubbock", "Lubbock, TX"),
)

DIFFICULTIES = ("easy", "standard", "hard")
ERAS = ("sandbox", "historical")

OWNER_EXAM = {
    1: "they are delighted",
    2: "they are calm",
    3: "they are watching",
    4: "they are not happy",
    5: "they are taking the keys",
}
COMP_OWNER = {
    "C": "Capital", "A": "Loan book", "M": "Management",
    "E": "Earnings", "L": "Cash", "S": "Rate risk",
}


def attach(state, goal_id="world"):
    if goal_id not in GOAL_SPECS:
        goal_id = "world"
    state.setdefault("meta", {})
    state["meta"]["goal"] = goal_id
    state["meta"]["goal_won"] = False
    state["meta"]["goal_failed"] = False
    if not isinstance(state.get("chronicle"), dict):
        state["chronicle"] = _empty_chronicle()
    return goal_id


def _empty_chronicle():
    return {
        "peak_ldr": 0.0,
        "peak_assets": 0,
        "first_4_exam": None,
        "saw_credit_bust": False,
        "saw_rate_shock": False,
        "had_run": False,
        "declined_buyouts": 0,
        "sale_multiple": None,
        "notable": [],
    }


def allow_svb_name(state):
    """SVB-style copy only after 2015 on the historical clock."""
    if (state.get("meta") or {}).get("era") != "historical":
        return False
    return int(state["time"]["date"][:4]) >= 2015


def display_date(state):
    raw = state["time"]["date"]
    if state.get("meta", {}).get("era") != "sandbox":
        return raw
    import datetime
    d = datetime.date.fromisoformat(raw)
    year = 1 + state["economy"]["months"] // 12
    return "%s, Year %d" % (d.strftime("%B"), year)


def summarize_save(state):
    """Card shown on the title-screen save list."""
    bank = state.get("bank") or {}
    led = bank.get("ledger")
    assets = L.total_assets(led) if led else 0
    reg = state.get("regulation") or {}
    camels = (reg.get("camels") or {}).get("composite", 2)
    months = (state.get("economy") or {}).get("months", 0)
    gid = (state.get("meta") or {}).get("goal", "world")
    spec = GOAL_SPECS.get(gid, GOAL_SPECS["world"])
    prog = progress(state) if bank else {"text": spec["blurb"]}
    return {
        "assets": assets,
        "pca": reg.get("pca", "well"),
        "camels": camels,
        "year": 1 + months // 12,
        "display_date": display_date(state) if state.get("time") else "",
        "goal": gid,
        "goal_label": spec["label"],
        "goal_text": prog.get("text", spec["blurb"]),
        "game_over": bool(state.get("game_over")),
    }


def progress(state):
    gid = (state.get("meta") or {}).get("goal", "world")
    spec = GOAL_SPECS.get(gid, GOAL_SPECS["world"])
    months = state["economy"]["months"]
    years = months / 12.0
    won = bool(state["meta"].get("goal_won"))
    failed = bool(state["meta"].get("goal_failed")) or (
        state.get("game_over") and state["game_over"].get("kind") == "seized"
        and gid != "sell")
    text, pct = _progress_bits(state, gid, years)
    return {
        "id": gid, "label": spec["label"], "blurb": spec["blurb"],
        "text": text, "pct": round(min(1.0, max(0.0, pct)), 3),
        "won": won, "failed": failed and not won,
    }


def _progress_bits(state, gid, years):
    home = (state.get("meta") or {}).get("home", "caprock")
    r = capital_ratios(state)
    pca = pca_category(r)
    camels = state["regulation"]["camels"]["composite"]
    assets = r["assets"]
    m = state["metrics"][-1] if state["metrics"] else {}
    chron = state.get("chronicle") or _empty_chronicle()

    if gid == "world":
        race = world_race(state)
        if race.get("empty_field"):
            bits = ("The map is empty. Biggest-in-the-world needs a living "
                    "industry — this is a failed world, not a shortcut.")
            return bits, 0.60 * min(1.0, race["me"] / max(1, WORLD_CROWN))
        if race["beats_rivals"] and race["on_world_table"]:
            bits = "You are #1 of %d and over $250B. The largest on the map." % race["field"]
        elif race["beats_rivals"]:
            bits = ("#1 of %d on the map. World table is $250B — you are at %s."
                    % (race["field"], _fm_assets(race["me"])))
        else:
            nxt = race.get("next_name") or race["rival_name"]
            nxt_a = race.get("next_assets") or race["rival_assets"]
            bits = ("You are #%d of %d. Next to pass: %s at %s. %s still leads the map."
                    % (race["rank"], race["field"], nxt, _fm_assets(nxt_a),
                       race["rival_name"]))
        # The bar is the two gates the goal actually requires: pass the
        # living leader, then sit on the $250B table. Next-smallest rival
        # is a waypoint in the sentence, not 85% of the meter — a $20M
        # charter must not read as "28% of the way to the world."
        to_lead = 1.0 if race["beats_rivals"] else min(
            1.0, race["me"] / max(1, race["rival_assets"]))
        to_crown = min(1.0, race["me"] / max(1, WORLD_CROWN))
        return bits, 0.40 * to_lead + 0.60 * to_crown

    if gid == "independent":
        return ("Year %.1f of 20. Still independent."
                % years if not state.get("game_over")
                else "The charter ended."), years / 20.0

    if gid == "square":
        pool = state["regions"][home]["deposit_pool"]
        share = DEP.market_deposits(state, home) / max(1, pool)
        roa = m.get("roa")
        from . import advisor
        peers = advisor.peer_averages(state)
        roa_ok = roa is not None and roa >= (peers.get("roa") or 0)
        bits = "Home share %.1f%% · report card %d · %s peer ROA" % (
            share * 100, camels, "at or above" if roa_ok else "below")
        score = 0.0
        score += min(0.4, share / 0.15 * 0.4)
        score += 0.3 if camels <= 2 else 0.1 if camels == 3 else 0.0
        score += 0.15 if roa_ok else 0.0
        score += min(0.15, years / 10.0 * 0.15)
        return bits, score

    if gid == "headline":
        bits = ("Bust %s · rate shock %s · run %s · worst exam %s"
                % ("seen" if chron["saw_credit_bust"] else "waiting",
                   "seen" if chron["saw_rate_shock"] else "waiting",
                   "yes" if chron["had_run"] else "none",
                   chron["first_4_exam"] or "none over 3"))
        score = 0.0
        score += 0.35 if chron["saw_credit_bust"] else 0.0
        score += 0.35 if chron["saw_rate_shock"] else 0.0
        score += 0.15 if not chron["had_run"] else 0.0
        score += 0.15 if not chron["first_4_exam"] else 0.0
        return bits, score

    if gid == "regional":
        cra = state["regulation"]["cra"]
        bits = "Assets %s · %s-capitalized · CRA %s" % (
            "$%sM" % f"{assets // 100 // 1_000_000:,}", pca, cra)
        lo, hi = 500_000_000_00, 2_000_000_000_00
        size = 0.0 if assets < lo else 1.0 if assets <= hi else 0.4
        score = 0.55 * min(1.0, assets / lo) * (1.0 if assets <= hi else 0.5)
        score += 0.25 if pca == "well" else 0.0
        score += 0.20 if cra in ("Satisfactory", "Outstanding") else 0.0
        return bits, score

    # sell
    bits = "Year %.1f (need 8). Waiting for 1.8× book or better." % years
    if chron.get("sale_multiple"):
        bits = "Sold at %.2fx tangible book." % chron["sale_multiple"]
    return bits, min(0.5, years / 8.0 * 0.5) + (0.5 if chron.get("sale_multiple", 0) >= 1.8 else 0.0)


def _fm_assets(cents):
    dollars = max(0, int(cents)) // 100
    if dollars >= 1_000_000_000_000:
        return "$%.1fT" % (dollars / 1_000_000_000_000)
    if dollars >= 1_000_000_000:
        return "$%.1fB" % (dollars / 1_000_000_000)
    if dollars >= 1_000_000:
        return "$%.0fM" % (dollars / 1_000_000)
    return "$%s" % f"{dollars:,}"


def world_race(state):
    """Where you stand vs living rivals and the $250B world table."""
    me = L.total_assets(state["bank"]["ledger"])
    alive = [b for b in (state.get("competitors") or {}).get("banks", [])
             if b.get("alive")]
    if alive:
        top = max(alive, key=lambda b: b.get("assets") or 0)
        rival_assets = int(top.get("assets") or 0)
        rival_name = top.get("name") or "a rival"
    else:
        rival_assets = 0
        rival_name = "no living rival"
    ahead = sum(1 for b in alive if (b.get("assets") or 0) > me)
    larger = [b for b in alive if (b.get("assets") or 0) > me]
    if larger:
        nxt = min(larger, key=lambda b: b.get("assets") or 0)
        next_assets = int(nxt.get("assets") or 0)
        next_name = nxt.get("name") or "a rival"
    else:
        next_assets = rival_assets
        next_name = rival_name
    return {
        "me": me,
        "rival_assets": rival_assets,
        "rival_name": rival_name,
        "next_assets": next_assets,
        "next_name": next_name,
        "rank": 1 + ahead,
        "field": 1 + len(alive),
        "crown": WORLD_CROWN,
        "beats_rivals": me > rival_assets and len(alive) >= 3,
        "on_world_table": me >= WORLD_CROWN,
        "empty_field": len(alive) < 3,
        "living": len(alive),
    }


def update_chronicle(state):
    """Call at month close. Cheap, no RNG."""
    chron = state.get("chronicle")
    if not isinstance(chron, dict):
        chron = _empty_chronicle()
        state["chronicle"] = chron
    r = capital_ratios(state)
    loans = 0
    try:
        from .loans import total_loans
        loans = total_loans(state["bank"]["loans"])
    except Exception:
        pass
    deps = L.total_deposits(state["bank"]["ledger"])
    ldr = loans / max(1, deps)
    chron["peak_ldr"] = max(chron["peak_ldr"], ldr)
    chron["peak_assets"] = max(chron["peak_assets"], r["assets"])
    econ = state["economy"]
    if econ.get("credit_stress", 0) >= 0.40 or econ.get("recession"):
        chron["saw_credit_bust"] = True
    if econ.get("fed_funds", 0) >= 0.06 or econ.get("credit_stress", 0) >= 0.35:
        chron["saw_rate_shock"] = True
    if state["crisis"].get("run_active") or state["crisis"].get("run_days", 0) > 0:
        chron["had_run"] = True
    reports = state["regulation"].get("exam_reports") or []
    if reports:
        last = reports[-1]
        if last["composite"] >= 4 and not chron["first_4_exam"]:
            chron["first_4_exam"] = last["date"]
            _note(chron, "First 4-rated exam on %s." % last["date"])
    return chron


def _note(chron, text):
    if text not in chron["notable"]:
        chron["notable"].append(text)
        chron["notable"] = chron["notable"][-8:]


def check_win(state):
    """If the primary goal just completed, mark it and return an event dict."""
    if state["meta"].get("goal_won") or state.get("game_over"):
        return None
    gid = state["meta"].get("goal", "world")
    years = state["economy"]["months"] / 12.0
    chron = state.get("chronicle") or _empty_chronicle()
    r = capital_ratios(state)
    pca = pca_category(r)
    camels = state["regulation"]["camels"]["composite"]
    won = False

    if gid == "world":
        race = world_race(state)
        won = (race["beats_rivals"] and race["on_world_table"]
               and not state["regulation"].get("seized"))
    elif gid == "independent":
        won = years >= 20 and not state["regulation"].get("seized")
    elif gid == "square":
        if years >= 10 and camels <= 2:
            home = state["meta"].get("home", "caprock")
            pool = state["regions"][home]["deposit_pool"]
            share = DEP.market_deposits(state, home) / max(1, pool)
            from . import advisor
            peers = advisor.peer_averages(state)
            roa = (state["metrics"][-1] or {}).get("roa") if state["metrics"] else None
            won = share >= 0.08 and roa is not None and roa >= (peers.get("roa") or 0)
    elif gid == "headline":
        won = (chron["saw_credit_bust"] and chron["saw_rate_shock"]
               and not chron["had_run"] and not chron["first_4_exam"]
               and years >= 3)
    elif gid == "regional":
        cra = state["regulation"]["cra"]
        won = (500_000_000_00 <= r["assets"] <= 2_000_000_000_00
               and pca == "well"
               and cra in ("Satisfactory", "Outstanding"))
    elif gid == "sell":
        won = bool(chron.get("sale_multiple") and chron["sale_multiple"] >= 1.8
                   and years >= 8)

    if not won:
        return None
    state["meta"]["goal_won"] = True
    spec = GOAL_SPECS[gid]
    return {
        "type": "goal_won", "blocking": True,
        "title": "Goal complete: %s" % spec["label"],
        "text": ("You did it. %s\n\nThis is a win, not a stop. Keep playing "
                 "the sandbox, or retire to the title screen."
                 % spec["blurb"]),
        "choices": ["keep", "retire"],
    }


def record_sale(state, offer, tbv):
    chron = state.setdefault("chronicle", _empty_chronicle())
    if tbv > 0:
        chron["sale_multiple"] = round(offer / tbv, 3)


def autopsy(state, kind):
    """Structured end-of-game summary."""
    r = capital_ratios(state)
    chron = state.get("chronicle") or _empty_chronicle()
    prog = progress(state)
    reports = state["regulation"].get("exam_reports") or []
    last = reports[-1] if reports else None
    exam_line = "Never examined."
    if last:
        comps = last.get("components") or state["regulation"]["camels"]
        parts = ", ".join("%s %s" % (COMP_OWNER.get(k, k), comps.get(k, "?"))
                          for k in ("C", "A", "M", "E", "L", "S") if k in comps)
        exam_line = "Last report card %d — %s. %s." % (
            last["composite"], OWNER_EXAM.get(last["composite"], ""), parts)
    aoci = -state["bank"]["ledger"]["balances"]["3200"]
    htm = state["bank"].get("cached_htm_unrealized", 0)
    unreal = min(0, aoci) + min(0, htm)
    notes = list(chron.get("notable") or [])
    for b in state["bank"]["ops"]["branches"]:
        if b.get("market") and b["market"] != state["meta"].get("home", "caprock"):
            notes.append("Opened in %s." % b["market"])
            break
    if chron.get("first_4_exam"):
        notes.append("The 4-rated exam on %s started the trouble."
                     % chron["first_4_exam"])
    if state["bank"]["funding"].get("discount_window_uses", 0) >= 5:
        notes.append("The window became a habit (%d uses)."
                     % state["bank"]["funding"]["discount_window_uses"])
    notes = notes[:3] or ["No single headline did this. The book just ran out."]
    earlier = "A year earlier: watch liquidity and do not let loans outrun deposits."
    if chron["peak_ldr"] > 1.1:
        earlier = "A year earlier: you were already loaned-up. Pay up for deposits or slow originations."
    if chron["first_4_exam"]:
        earlier = "A year earlier: the exam was coming and liquidity was the grade they would write down."
    years = state["economy"]["months"] / 12.0
    return {
        "kind": kind,
        "date": state["time"]["date"],
        "display_date": display_date(state),
        "assets": r["assets"],
        "years": round(years, 1),
        "goal": prog,
        "exam": exam_line,
        "peak_ldr": round(chron["peak_ldr"], 3),
        "window_uses": state["bank"]["funding"].get("discount_window_uses", 0),
        "unreal_vs_cet1": round(-unreal / max(1, r["cet1"]), 3),
        "cet1": round(r["cet1_ratio"], 4),
        "notes": notes,
        "earlier": earlier,
        "summary": _closing_line(state, kind, years, r),
    }


def _closing_line(state, kind, years, r):
    name = state["bank"]["name"]
    if kind == "seized":
        return ("After %.1f years the FDIC took %s. Assets were $%s; "
                "tangible equity %.2f%% of assets."
                % (years, name, f"{r['assets'] // 100:,}",
                   r["tang_equity_ratio"] * 100))
    if kind == "sold":
        return ("You sold %s after %.1f years. The courthouse square "
                "got a new name on the window."
                % (name, years))
    if kind == "retired":
        return ("You stepped away from %s after %.1f years, still standing."
                % (name, years))
    return "After %.1f years, the story of %s ends here." % (years, name)


def compose_digest(state):
    """One month, one page. Dashboard reads the latest."""
    m = state["metrics"][-1] if state["metrics"] else {}
    prev = state["metrics"][-2] if len(state["metrics"]) > 1 else {}
    econ = state["economy"]
    if econ.get("recession"):
        econ_line = "Recession. GDP %+.1f%%, unemployment %.1f%%." % (
            econ.get("gdp_growth", 0), econ.get("unemployment", 0))
    else:
        econ_line = "Expansion. Fed funds %.2f%%, unemployment %.1f%%." % (
            econ.get("fed_funds", 0) * 100, econ.get("unemployment", 0))
    home = (state.get("meta") or {}).get("home", "caprock")
    region = state["regions"].get(home) or {}
    local = None
    if region.get("shock"):
        local = region["shock"].get("name")
    else:
        # one local headline only if we serve that market
        served = set(state["bank"]["deposits"]["pools"])
        for mid, regn in state["regions"].items():
            if mid in served and regn.get("shock"):
                local = "%s — %s" % (regn["name"], regn["shock"].get("name"))
                break
    ni = 0
    if state["bank"]["ledger"]["months"]:
        ni = state["bank"]["ledger"]["months"][-1]["net_income"]
    month_events = [e for e in state["events"]["log"][-30:]
                    if (e.get("date") or "")[:7] == state["time"]["date"][:7]]
    exam = next((e["title"] for e in month_events if e.get("type") == "exam"), None)
    fraud_n = sum(1 for c in state["bank"]["fraud"]["cases"]
                  if c.get("status") == "open")
    return {
        "month": state["time"]["date"][:7],
        "display": display_date(state),
        "econ": econ_line,
        "ni": ni,
        "dep_flow": int(m.get("deposits", 0) - prev.get("deposits", m.get("deposits", 0))),
        "loan_flow": int(m.get("loans", 0) - prev.get("loans", m.get("loans", 0))),
        "cet1": m.get("cet1_ratio"),
        "ldr": m.get("loan_to_deposit"),
        "local": local,
        "exam": exam,
        "window": state["bank"]["funding"].get("discount_window_uses", 0),
        "fraud": fraud_n,
    }
