"""Fraud: a live loss environment you manage with spend, staffing and
thresholds.

Channels: check fraud (kiting, counterfeits), card fraud, wire/BEC,
account takeover, synthetic identity, elder exploitation, loan fraud,
insider theft. Monthly expected losses scale with your volumes and the
ambient fraud environment, reduced by your detection stack. Tight
thresholds catch more fraud but decline good customers (a deposit drag).
Cases occasionally surface for you to handle individually.
"""

from . import ledger as L

CHANNELS = {
    # per $1M of driver volume per month, base loss in cents at detection=0.5
    "check":     {"driver": "deposits", "base": 900,  "detectable": 0.85},
    "card":      {"driver": "deposits", "base": 2100, "detectable": 0.75},
    "wire_bec":  {"driver": "deposits", "base": 700,  "detectable": 0.80},
    "ato":       {"driver": "deposits", "base": 600,  "detectable": 0.80},
    "synthetic": {"driver": "loans",    "base": 800,  "detectable": 0.70},
    "elder":     {"driver": "deposits", "base": 350,  "detectable": 0.60},
    "loan_fraud": {"driver": "loans",   "base": 1100, "detectable": 0.65},
    "insider":   {"driver": "assets",   "base": 150,  "detectable": 0.55},
}


def new_fraud():
    return {
        "prevention_spend": 3_000_00,   # monthly, player lever
        "threshold": 2,                 # 0 loose .. 4 tight, player lever
        "env": 1.0,                     # ambient fraud intensity, drifts
        "false_positive_drag": 0.006,   # (threshold-1)*0.006 at default 2
        "cases": [],                    # open cases for the player
        "next_case_id": 1,
        "losses_ytd": 0,
        "losses_by_channel": {k: 0 for k in CHANNELS},
        "cases_resolved": 0,
    }


def detection_rate(state):
    bank = state["bank"]
    fr = bank["fraud"]
    assets = max(bank["cached_assets"], 20_000_000_00)
    # spend adequacy: ~0.10% of assets/yr keeps pace with the fraud arms race
    adequacy = min(1.5, fr["prevention_spend"] * 12 / (assets * 0.001))
    staff = bank["ops"]["staff"]["ops"]["count"] + bank["ops"]["staff"]["it"]["count"] * 0.5
    staff_need = max(1.0, assets / 100 / 1_000_000_000 * 6)
    staffing = min(1.5, staff / staff_need)
    thr = fr["threshold"]
    d = 0.22 + 0.20 * adequacy + 0.12 * staffing + 0.06 * thr \
        + 0.03 * bank["ops"]["digital_level"]
    return max(0.15, min(0.90, d))


def step_month(state, rng):
    bank = state["bank"]
    fr = bank["fraud"]
    econ = state["economy"]
    date = state["time"]["date"]
    events = []

    # fraud environment drifts; spikes in booms (more activity) and with time
    year_factor = 1.0 + econ["months"] / 12 * 0.012   # fraud gets worse every year
    fr["env"] = round(max(0.5, min(3.5,
        fr["env"] * 0.97 + 0.03 * year_factor + rng.normal(0, 0.03))), 3)

    det = detection_rate(state)
    fr["detection"] = round(det, 3)
    thr = fr["threshold"]
    fr["false_positive_drag"] = round(max(0.0, (thr - 1) * 0.006), 4)

    deposits = L.total_deposits(bank["ledger"]) / 100 / 1_000_000
    from .loans import total_loans
    loans = total_loans(bank["loans"]) / 100 / 1_000_000
    assets = bank["cached_assets"] / 100 / 1_000_000
    drivers = {"deposits": deposits, "loans": loans, "assets": assets}

    total_loss = 0
    for name, ch in CHANNELS.items():
        vol = drivers[ch["driver"]]
        mitigation = 1.0 - ch["detectable"] * (det - 0.15) / 0.85
        expected = vol * ch["base"] * fr["env"] * max(0.05, mitigation)
        loss = int(max(0.0, rng.normal(expected, expected * 0.35)))
        fr["losses_by_channel"][name] += loss
        total_loss += loss

    # Reg E / chargebacks / ACH returns: ongoing ops cost, scaled by volume
    rege = int(deposits * 320 * (1.15 - det * 0.3))
    total_loss_entry = total_loss
    if total_loss_entry > 0:
        L.post(bank["ledger"], date, "Fraud losses (month)",
               [["5160", total_loss_entry, 0], ["1000", 0, total_loss_entry]], tag="fraud")
    if rege > 0:
        L.post(bank["ledger"], date, "Chargebacks, ACH returns, Reg E resolution",
               [["5170", rege, 0], ["1000", 0, rege]], tag="fraud")
    fr["losses_ytd"] += total_loss

    # ---- individual cases (rarer, meaner) ----
    # Old cadence produced wallpaper (5–8 kiting cases in 3 years).
    lam = 0.06 + assets / 12000 + fr["env"] * 0.05
    if rng.chance(min(0.18, lam * 0.12)):
        events.append(_spawn_case(state, rng))

    # occasional six-figure wire when detection is weak
    if det < 0.55 and rng.chance(0.012):
        hit = int(min(max(assets, 20), 8000) * rng.uniform(2500, 9000))
        L.post(bank["ledger"], date, "BUSINESS EMAIL COMPROMISE wire loss",
               [["5160", hit, 0], ["1000", 0, hit]], tag="fraud")
        events.append({"type": "fraud_major", "blocking": True,
                       "title": "Wire fraud: $%s out the door" % f"{hit // 100:,}",
                       "text": ("A customer's controller was spoofed into authorizing wires to "
                                "a 'new vendor account'. Your wire desk had no callback "
                                "verification threshold that would have caught it. Recovery "
                                "prospects are poor. Raise fraud prevention spend and "
                                "thresholds, or eat more of these.")})
    return events


CASE_TEMPLATES = [
    ("check_kiting", "Suspected check kiting",
     "Branch staff flagged {name}, who has been cycling ${amt:,} in checks between us and "
     "two other banks with matching deposits and withdrawals timed to float. Freeze the "
     "accounts and file a SAR, or keep watching to build the case?"),
    ("elder", "Possible elder exploitation",
     "A teller reports that {name}, 84, has been withdrawing ${amt:,} in cashier's checks "
     "accompanied by a 'nephew' nobody has met. Intervene (freeze and call the family) or "
     "process the transactions?"),
    ("loan_fraud", "Falsified financials suspected",
     "A credit analyst found inconsistencies in {name}'s borrowing-base certificate — "
     "receivables pledged to us may not exist. Exposure ${amt:,}. Call the loan and demand "
     "a field audit, or work with the borrower quietly?"),
    ("skimmer", "Card skimmer found",
     "Maintenance found a skimming device on the drive-up ATM. An estimated ${amt:,} of "
     "card data is compromised. Reissue all affected cards now (cost, annoyance) or "
     "monitor accounts for fraud (risk)?"),
]


def _spawn_case(state, rng):
    bank = state["bank"]
    fr = bank["fraud"]
    from .loans import FIRST, LAST
    kind, title, tmpl = rng.choice(CASE_TEMPLATES)
    name = "%s %s" % (rng.choice(FIRST), rng.choice(LAST))
    scale = max(1.0, (bank["cached_assets"] / 100 / 1_000_000 / 20) ** 0.5)
    amt = int(rng.uniform(40_000, 480_000) * scale) * 100
    case = {"id": fr["next_case_id"], "kind": kind, "name": name, "amount": amt,
            "opened": state["time"]["date"], "status": "open"}
    fr["next_case_id"] += 1
    fr["cases"].append(case)
    if len(fr["cases"]) > 30:
        del fr["cases"][0]
    return {"type": "fraud_case", "blocking": False,
            "title": "FRAUD CASE #%d: %s" % (case["id"], title),
            "text": tmpl.format(name=name, amt=amt // 100),
            "case_id": case["id"], "choices": ["act", "monitor"]}


def prune_resolved_events(state):
    """Drop pending fraud_case events whose case is no longer open.

    Desk Act/Watch closes the case without going through event_choice, so
    the inbox event used to linger — badge stuck, clock still stopping,
    and a second click raised 'already closed'.
    """
    cases = ((state.get("bank") or {}).get("fraud") or {}).get("cases") or []
    open_ids = {c.get("id") for c in cases if c.get("status") == "open"}
    pend = (state.get("events") or {}).get("pending")
    if not pend:
        return 0
    keep = [e for e in pend
            if not (e.get("type") == "fraud_case"
                    and e.get("case_id") not in open_ids)]
    dropped = len(pend) - len(keep)
    if dropped:
        pend[:] = keep
    return dropped


def resolve_case(state, case_id, action, rng):
    """action: 'act' (freeze/intervene) or 'monitor'."""
    bank = state["bank"]
    fr = bank["fraud"]
    case = None
    for c in fr["cases"]:
        if c["id"] == case_id and c["status"] == "open":
            case = c
            break
    if case is None:
        prune_resolved_events(state)
        return {"message": "This case is already closed.", "loss": 0,
                "already": True}
    det = detection_rate(state)
    date = state["time"]["date"]
    if action == "act":
        # acting early usually caps the loss; small cost + goodwill hit possible
        loss = int(case["amount"] * rng.uniform(0.0, 0.25))
        cost = int(case["amount"] * 0.05)
        msg = "Acted immediately. Loss contained to $%s (plus $%s in costs). SAR filed." \
            % (f"{loss // 100:,}", f"{cost // 100:,}")
        total = loss + cost
    else:
        if rng.chance(det):
            loss = int(case["amount"] * rng.uniform(0.1, 0.5))
            msg = "Monitoring paid off — the scheme was interrupted at $%s of loss." \
                % f"{loss // 100:,}"
        else:
            loss = int(case["amount"] * rng.uniform(0.8, 1.6))
            msg = "The scheme ran longer than expected. Total loss: $%s." % f"{loss // 100:,}"
        total = loss
    if total > 0:
        L.post(bank["ledger"], date, "Fraud case #%d resolution (%s)" % (case_id, case["kind"]),
               [["5160", total, 0], ["1000", 0, total]], tag="fraud")
    case["status"] = "closed"
    case["outcome"] = msg
    fr["cases_resolved"] += 1
    state["regulation"]["bsa"]["sars_filed"] += 1
    prune_resolved_events(state)
    return {"message": msg, "loss": total}
