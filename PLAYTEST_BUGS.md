# Playtest bug report — post-PR-3 build

Found during a scripted + browser bug-hunt playthrough of the merged branch
(PR 1 "Playtest fixes A–G" + PR 3 "overnight cash fix", head `1b7a976`).
Method: three headless playthroughs (an active sensible owner for 15y, an
abusive one for 8y, a 60-year endurance run) with per-day invariant checks
(trial balance, subledger-to-GL ties, negative accounts, NaN, int-cents),
plus garbage-input fuzzing of every action/policy, a v1-save migration test,
and a Chromium drive of the new UI. **No code has been changed** — this file
is the worklist.

Severity: 🔴 exploit/corruption · 🟠 wrong behavior · 🟡 rough edge.

---

## 🔴 1. Unlimited money: capital/funding actions have no size caps

`funding.py` — `issue_brokered` (L84), `raise_common` (L335),
`issue_preferred` (L362), `issue_subdebt` (L105).

Every one of these accepts **any** amount. Verified on a fresh $20M bank:

- `issue_brokered {amount: 10**14}` → **$1 trillion of cash appears** at 5.97%.
- `raise_common {amount: 10**14}` → $1T of equity sold "at 1.26× book"
  (68 billion new shares) — from a $20M bank in Caprock City.
- `issue_preferred` / `issue_subdebt` same. Sub debt of $1T also posts a
  $15B underwriting fee that drives equity to **−$15.0B** with no
  immediate consequence until quarter-end PCA.

This is how my abuse playthrough reached **$2.4 trillion of assets in 8
years with 0.00% NPAs**. The market must have capacity limits: brokered
tied to franchise/deposit size and rate escalation; equity raises capped by
a multiple of current book with price degradation as size grows; sub
debt/preferred capped vs capital. Also: refuse issues whose fees exceed
available equity (the −$15B case).

## 🔴 2. Selling any HTM lot double-transfers it and permanently corrupts account 1210

`securities.py` — `sell()` L187 posts the sale (credit 1210 by the lot's
book), **then** calls `_taint_htm()` (L229-230) while the sold lot is
**still in `book["lots"]`**. The taint routine transfers the same lot's
book out of 1210 a second time (L240+). Verified: selling the starter
bank's only HTM lot leaves GL 1210 at **−$1,000,000 forever** and the
subsequent `revalue()` burns a matching phantom **$1M loss into AOCI** —
the balance sheet shows "Held-to-maturity: −$1,000,000" and the player
loses $1M of equity out of thin air. Trial balance stays 0, so the daily
audit never catches it.

Fix direction: in `sell()`, remove/shrink the lot (or mark it excluded)
**before** calling `_taint_htm`, or have `_taint_htm` skip the lot being
sold. Add a regression test asserting 1210 == Σ HTM book after any sale
sequence (the existing taint test only checks the flag and trial balance).

## 🔴 3. `_prune_pools` deletes sub-$1 loan pools without a ledger entry

`loans.py` L929. Pools with balance 1–100 cents are silently dropped from
the list while GL 1300 keeps their balance. Every long game leaks a
growing pools-vs-GL discrepancy (observed: −91¢ at year 7 growing to
−$114 by year 40 as vintages amortize to crumbs, in steps of ~90-100¢ per
month). Verified with a direct repro: a 91-cent pool pruned → tie off by
exactly 91.

Fix direction: post the crumb as principal (credit 1300 / debit 1000) or
fold it into a sibling pool before dropping. Extend
`test_pools_tie_to_ledger` to run 10+ years so vintage crumbs actually
occur.

## 🔴 4. `_absorb_franchise` truncation leaks cents between GL and subledgers

`engine.py` L623. The GL entries (in `_resolve_fdic_bid` /
`_resolve_bank_purchase`) post the **full** deposit/loan amounts, but the
pool-side distribution truncates twice — `deposits_amt // len(markets)`
and `int(per_mkt * MIX[p])` / `int(per_mkt_l * frac)` — so pools receive
less than the GL. Verified: absorbing $10,000,000.07 across 3 markets put
$9,999,999.93 into pools (14¢ lost). Every acquisition permanently breaks
the deposits/loans-to-GL tie by a few cents (observed as the constant −5¢
deposit-tie offset in the 60-year run after one bank purchase).

Fix direction: hand the running remainder to the last market/product
(same pattern already used for the GL split in `_resolve_fdic_bid`).

## 🟠 5. Negative operating cash accrues no interest (free overdraft under "ask")

With `overnight_policy: "ask"` (the new default), choosing **wait** — or
just leaving the shortfall modal — leaves account 1000 negative.
`funding.accrue_day` charges interest only on 2100/2110/2120/brokered/
sub-debt balances; a negative 1000 costs **nothing**. A player can run
weeks deep in the red for free. Realistically an uncovered overnight
position is a daylight-overdraft/fed-funds position at a penalty rate.

Fix direction: accrue interest on negative 1000 at fed funds + penalty in
`accrue_day`, or have day-end sweep any negative into 2110 regardless of
policy (the "ask" then being about *which term facility* to use, not
whether to be funded).

## 🟠 6. Ask-path "fed_funds" choice bypasses the counterparty limit

`engine.py` L1056-1061 (`_resolve_overnight_choice`): posts unlimited fed
funds purchased directly, while the auto path correctly respects
`_ff_purchase_limit` (which shrinks for troubled banks). A CAMELS-5 bank
mid-run can borrow any amount overnight through the modal. Route the
choice through the same limit and fail over to the window with a message.

## 🟠 7. Week/month/quarter advance is hard-blocked by the inbox with no override

`engine.advance()` L699 has a `skip_inbox` parameter — but nothing passes
it: not `server.py`'s `/api/advance` handler, not the UI. Any open loan
application (they live 60–90 days) or open fraud case makes every
week/month/quarter click return `days: 0`. A player who wants to
deliberately sit on an application must press **+1 Day ~60 times**.
Verified in the browser: eight `advance('quarter')` calls moved the clock
zero days past a pending memo. Decision-first is good; the missing part
is plumbing `skip_inbox` through the API plus an "advance anyway" button
on the toast/modal.

## 🟠 8. Choosing "wait" on the overnight shortfall re-raises the modal every single day

`funding.manage_overnight` dedups only against **pending** events
(L270-272). After the player resolves the modal with "wait", the next
day's shortfall raises a fresh blocking modal — every business day until
covered. Combined with bug 7, "wait" is a trap: the stated option ("wait
and shrink next month's originations") is unplayable in practice. A
cooldown (e.g., don't re-ask for N days after an explicit "wait", or make
"wait" auto-cover via FFP at a penalty) would make it honest.

## 🟠 9. `set_policy` crashes on NaN (HTTP 500)

`engine.py` L1124: `value = int(value)` raises `ValueError: cannot
convert float NaN to integer` — uncaught, so `/api/set` returns a 500
with a stack trace instead of a clean refusal. JSON `NaN` is accepted by
Python's parser, so this is reachable from the client. Guard with
`math.isfinite` before conversion.

## 🟠 10. `repay_funding` with an unknown kind crashes (KeyError)

`funding.py` L127: `acct = {...}[kind]` indexes before validating.
`{"kind": "nope"}` → `KeyError: 'nope'` → HTTP 500. Validate `kind`
first and raise a clean error string.

## 🟡 11. `store.list_saves()` fully loads and decompresses every save

`store.py` L59: the saves list now calls `self.load(name)` (gunzip +
json-parse of a ~2MB state) **per save** just to decorate the card via
`goals.summarize_save`. With a handful of long games this makes the save
screen and `/api/saves` conspicuously slow, and it runs at server startup
too. Cache the summary columns in the `saves` table at snapshot time
instead.

## 🟡 12. Risk tab shows "False-positive drag 1.00x"

Browser pass: the fraud panel renders the false-positive drag as `1.00x`
on a fresh bank — the value is a small fraction (≈0.006-scale drag) or a
multiplier depending on which field the new UI reads; either the field or
the format is wrong. Worth a look at the risk-tab fraud block in
`web/app.js` to make the unit honest (it previously displayed `0.60%`).

## Verified-clean notes (things I hunted and did NOT find)

- 85/85 tests pass; trial balance held to the cent through every
  playthrough, including the trillion-dollar abuse run.
- Calibration is fair: five minimally-managed 20-year banks all survived
  (ROA 0.17–1.15%, CAMELS 1–3). My scripted deaths traced to deliberately
  reckless M&A, not the model.
- The `counter_loan` / `participate_loan` booking paths tie to the GL
  exactly; garbage params are clamped safely.
- v1 saves (pre-goals schema) step, render every section, and summarize
  without errors.
- The new-game screen (home/era/difficulty/goal), Your Desk, digest, memo
  Approve/Counter/Participate/Decline buttons, and all tabs render with
  zero JS errors in Chromium.

## Suggested fix order

1. #1 (exploit), #2 (corruption) — these break the game's promise.
2. #3, #4 — restore the subledger ties, then tighten the daily audit to
   assert pools==GL so any future leak screams on day one.
3. #5, #6, #8 — make the overnight system honest.
4. #7, #9, #10 — plumbing and input hygiene.
5. #11, #12 — polish.
