# Bank Game — project plan

This is the working plan for turning the simulation into a game people
finish and recommend. It comes from a full playtest of the live UI plus
multi-year engine campaigns (passive, advisor-follow, fortress, aggressive
expansion). Evidence numbers below are from those runs, not guesses.

`DESIGN.md` stays the model reference. This file is what we build, in
what order, and what “done” means. When a phase ships, check it off here
and note the PR.

---

## Thesis

The engine is already deeper than the UI can teach. We do **not** add
another product line, holding company, or Fed nuance until a new player
can:

1. Survive a honest first year without being lied to by the dashboard.
2. Grow into the next county without a hidden suicide button.
3. Get examined for decisions they actually made.
4. Sit down with a reason to play *tonight*, and get an autopsy when it ends.

Unfair deaths and silent systems first. Flavor, goals, and credit depth
second. Calibration third. Optional late-game systems last.

---

## Laws (do not violate)

1. **The books stay real.** Integer cents, double-entry, daily audit,
   named RNG streams, same seed → same world. No floating-point money.
   No third-party packages.
2. **The advisor is never an autopilot.** Cards recommend moves the
   player could make by hand. If a recommended move is illegal or
   unfunded, the card is wrong — fix the card, don’t silently no-op.
3. **No lethal click without a preview.** Branch, buy, sell HTM, accept
   a $2M credit, mash +1 Qtr past expiring memos: the player sees the
   consequence *before* commit.
4. **Owner view is a translation, not a second game.** Every label,
   top-bar pill, peer table, and exam sentence has an owner string.
   Simulation state does not change with the toggle.
5. **Depth over breadth.** One recurring borrower with a counteroffer
   beats three new unlockable P&L drips.
6. **News is signal.** If it does not change a decision in a market you
   serve (or a national headline that does), it does not make the inbox.
7. **Benign-era profit is allowed to be good, not a printer.** A
   passive, well-run community bank should feel like a real one: ROA
   around 1.0–1.3%, efficiency in the 50s–60s, capital piling up until
   you put it to work or give it back. Cycles and player mistakes kill.
8. **Date and world must agree.** Either the calendar is historical
   (2000–2024 path) or it is a sandbox clock. Do not write “January 2000”
   and then lecture about Silicon Valley Bank on day one.

---

## Definition of done (the whole project)

A stranger who has never run a bank can:

- Charter a bank, understand the six lights, take a deposit stance,
  decide one real credit, park cash, hire one person, and meet the
  first exam — without a fake ROA or a skipped memo.
- Open a second branch in a peer town and still be well-capitalized a
  year later. Opening Dallas is possible, expensive, and *labeled* as
  a capital event — never a $900M seizure in 90 days.
- Ignore the advisor for a year and not get a consent order solely
  because overnight code borrowed at the window in secret.
- Pick a goal on the title screen and know whether they are winning.
- Fail and get an autopsy that names the vintage, the market, the
  window days, and the decision that did it.

Plus: `python3 -m unittest discover -s tests` stays green, including
new invariants listed per phase.

---

## Phase A — Stop the unfair deaths

Priority: **ship first**. These are the bugs that make the game feel
random or cruel. No new features until A is in.

### A1. Market-entry share must start tiny

**Problem.** `deposits.natural_share` is `presence / (presence + 6 ×
competition)`. One new branch → presence ≈ 1 → **8.5% of Dallas**
(~$100B+ pool) or **6% of NYC** (~$1.8T). After a $5M capital raise
and one Dallas branch: $883M Dallas deposits in one quarter, leverage
1.0%, tangible equity 0.98%, seized.

**Desired.** A new branch in a market you do not already dominate
starts near-zero share and crawls with years-in-market, brand, and
staffing. Steady-state cap is a function of bank size vs market size
(a $25M bank cannot own 8% of Dallas). Rural peer towns (Verhalen,
Plainview) still work as the intended second-county move.

**Files.** `bankgame/sim/deposits.py` (`natural_share`, `presence_score`,
`step_month`); possibly a `years_in_market` / `entered` field on
`ops.brand` or a new `ops.markets` dict.

**Tests.** `tests/test_markets.py`

- Open Dallas on day 1 (after raising enough cash). After 90 days:
  Dallas deposits < $15M, CET1 still “well”, not seized.
- Open Verhalen on day 1. After 1 year: home + Verhalen deposits
  grew, PCA still well, assets still community-bank scale
  (roughly $20–40M).
- A $2B bank’s Dallas share is allowed to be material; a $20M
  bank’s is not.

### A2. Branch button tells the truth

**Problem.** Operations says `Open (~$1.8M+)`. Dallas costs $2.88M
and, under current share math (and even after A1), is a capital event.
Starting cash is $2.2M — you often cannot afford the branch the
dropdown offers.

**Desired.** Dropdown grouped by kind (peer towns / small metros /
metros / money center). Each row: open cost, monthly cost, **year-1
deposit gather estimate**, **pro-forma CET1 / leverage**, and a
plain-English verdict (`safe` / `stretch` / `this will dilute you
below well-capitalized`). Confirm modal required for stretch/lethal.
Disable rows you cannot fund.

**Files.** `bankgame/sim/operations.py` (preview helper);
`bankgame/server.py` (ops section); `web/app.js` (`tabOps`).

**Tests.** Preview numbers match the same helpers the engine will use
after the branch opens (no “UI said $4M, sim gathered $400M”).

### A3. M&A is sized to the buyer

**Problem.** `_ma_opportunities` picks `rng.choice` over all 12
markets, so “Farmers National Bank” can be a NYC franchise. Buy
absorbs a branch into that market and A1’s old share math (or even
a milder version) can explode the book. Aggressive campaign: assets
jumped $98M → $3.2B, then PCA critical / seized. Deal modal is
Buy / Pass with no pro-forma.

**Desired.**

- Targets spawn in markets at or below your current weight class,
  or in a market you already serve, unless you are already a
  regional.
- Modal shows: price, estimated deposits/loans/goodwill, **pro-forma
  CET1, leverage, liquidity, LDR**, integration months, and
  “regulators will deny this if…” (CAMELS, orders, CRA, cash).
- Buy is disabled (with reason) when it would drop you below
  well-capitalized or when cash cannot close.
- Frequency: far less than ~5%/month once you have seen one. Maybe
  a quiet pipeline on Markets instead of a blocking modal every
  other quarter.

**Files.** `bankgame/sim/engine.py` (`_ma_opportunities`,
`_resolve_bank_purchase`, `_absorb_franchise`); `web/app.js`
(`renderEventModal`).

**Tests.** 5-year run, 20 seeds: no acquisition alone takes a
well-capitalized $25M bank to >$200M in 90 days. Denied deals
leave the ledger untouched.

### A4. Overnight funding is a decision

**Problem.** `funding.manage_overnight` covers cash holes with fed
funds purchased, then the **discount window**, in secret. News
fires only on uses 1, 5, 15. Fortress 5-year: 40 window uses,
liquidity 6.3%, CAMELS L=4, consent-order path — while C/A/E/S
were 1s. The player never chose to borrow from the Fed.

**Desired.**

- Daily sweep of surplus into fed funds sold can stay automatic
  (with a visible cash target).
- Covering a shortfall is a **policy**: `auto` (current, but
  FHLB first, window last and logged every time) vs `ask`
  (default for guided / owner view): clock stops,
  “We are short $X overnight. Draw FHLB / sell AFS / borrow FF /
  window / shrink next month’s originations.”
- Window use always creates a dated event and increments a
  top-bar / Desk warning (“Window used N times this exam cycle”).
- Examiners still hate habitual window use — but only after the
  player saw it happen.

**Files.** `bankgame/sim/funding.py`; `bankgame/sim/engine.py`
(blocking event); `bankgame/sim/advisor.py` (new card);
`web/app.js` (modal + Desk).

**Tests.** A cash hole without `auto` policy raises a blocking
event and does **not** increment `discount_window_uses` until
the player chooses. Auto policy still keeps the books balanced
every day.

### A5. Origination cannot outrun funding in silence

**Problem.** Monthly loan origination keeps booking even when LDR
is 1.3+ and deposits are capped by the home-market pool. Passive
3-year: loans $25M vs deposits $18M, cash floor, window,
CAMELS 3. Advisor then says “hire a lender.”

**Desired.** A player-facing **growth stance** (or an automatic
throttle the advisor explains):

- When LDR > ~1.05 or cash < target, new pool originations
  shrink before wholesale fills the hole.
- Large credits still arrive, but the memo says “funding this
  requires $X we do not have — raise deposits, FHLB, or
  participate.”
- Approve of an unfunded loan fails *before* the click if we
  can know; otherwise the current error stays, and the advisor
  never says “approve it.”

**Files.** `bankgame/sim/loans.py` (`originate_month`,
`approve_application`); `bankgame/sim/advisor.py`
(`_r_hire_lender`, `_r_funding_stretch`).

**Tests.** Passive 3-year, several seeds: LDR stays under ~1.15
without player action, window uses are rare, CAMELS L is not
a 4 solely from idle play. Aggressive growth still possible
if the player pays up for deposits or draws FHLB on purpose.

---

## Phase B — Honest first session

The first hour is how the game is judged. Make it tell the truth.

### B1. Day-1 gauges tell the truth

**Problem.** Earnings light is green with “ROA 1.10%” from
`bank["roa_ttm"]` fallback. NI is $0. Reserve need is $0. Rate-risk
copy names SVB on 2000-01-03. All six lights green, empty inbox.

**Desired.** Before the first month close: status `y` or a fourth
state `new` — “Books just opened. First real scorecard when
January closes.” No invented ROA/efficiency. SVB copy only after
the world has a reason to know that story (or never, in 2000
sandbox — see F3).

**Files.** `bankgame/sim/advisor.py` (`gauges`); `web/app.js`
(`tabDesk`, `tabDashboard` empty-chart already OK).

**Tests.** Day-1 gauges do not contain a numeric ROA unless
`metrics` is non-empty.

### B2. Title screen is a real front door

**Problem.** `Game.__init__` auto-loads the most recent save.
Relaunch skips the charter screen. Save rows show name / date /
seed only.

**Desired.** Always land on the title screen. “Continue” is a
big button for the most recent save. Save rows show year,
assets, CAMELS/report-card, PCA, goal progress. Delete still
confirms. Rollback stays on a sub-panel after load, not as the
first thing a new player sees.

**Files.** `bankgame/server.py` (`Game.__init__`, `/api/saves`);
`bankgame/store.py` (store extra summary columns or derive from
latest snapshot meta); `web/app.js` (`showSaves`, `refresh`).

### B3. Owner view is consistent

**Problem.** Toggle changes Desk/glossary labels. Top bar still
says `CAMELS 2`. Markets peers are NIM / ROA / NPA. Exam modal
is examiner English.

**Desired.** One dictionary, used everywhere: top-bar pills,
peer table headers, exam title (“Report card: 2 — they are
calm”), call-report chips, advisor “Show me why.” Banker view
keeps the jargon.

**Files.** `web/app.js` (`DICT`, `renderTopbar`, `tabMarkets`,
`renderEventModal`, `tabReports`); exam text can stay official
in the `<pre>` (it is a real report) with an owner-language
summary above it.

### B4. The clock respects the inbox

**Problem.** Loan apps are non-blocking, `days_left` 60,
decremented 30 per month. `+1 Qtr` expires memos the player
never opened. Tutorial says “one shows up most months”; some
year-1 seeds produced three.

**Desired.**

- Advance stops (or asks) when a loan memo, fraud case, or
  exam is waiting — same as today’s blocking events.
- Optional: “advance anyway” expires with an explicit confirm
  (“2 credits will walk”).
- Tutorial copy matches real frequency, or we raise generation
  slightly in year 1 so the tour is not a lie.

**Files.** `bankgame/sim/engine.py` (`advance`);
`bankgame/sim/loans.py` (`_generate_applications`);
`web/app.js` (`advance`).

**Tests.** `advance(..., "quarter")` with a queued app returns
before the app expires, unless the caller passed
`skip_inbox=True`.

### B5. Tutorial is a set piece, not homework

Keep the six steps. Change the contract:

- Welcome cannot be “mark done” without clicking a gauge.
- First large credit is **blocking** and is guaranteed in
  month 1 of a guided game (seed a named borrower).
- Bonds / hire stay as now (real actions complete them).
- Exam step stays automatic on first report.
- Skip still exists.

**Files.** `bankgame/sim/advisor.py` (`tutorial`, `ack_step`);
`bankgame/sim/newgame.py` or `loans.py` (guided first memo).

### B6. Keyboard and +1 Qtr are documented

Shortcuts (space / w / m / q) appear in the top bar or a `?`
popover. `+1 Qtr` tooltip: “Stops if something needs you.
Can skip day-to-day noise.” After B4, this is true.

### B7. Exam date is always visible

Top bar and Desk: “Examiners in 11 months.” At 3 months the
existing `exam_prep` card fires **with actions** (see C1).
First exam is a set piece (modal, owner summary, then the
full report) — not just another news line.

**Files.** `web/app.js` (`renderTopbar`, `tabDesk`);
`bankgame/sim/regulation.py` (`run_exam` event payload).

---

## Phase C — An advisor you can trust

### C1. Every card has a doable action

**Problem.** `uninsured_watch` and `exam_prep` are Ignore-only.
Several cards recommend moves that then throw
`ActionError` (unfunded loan, can’t afford the acquisition).

**Desired.** Extend `tests/test_advisor.py` (`test_cards_actions_are_all_legal`)
so that:

- Every card has ≥1 action **or** a navigation-only action
  (`{kind: "goto", tab: "..."}`).
- Executing the action on the state that produced the card
  does not raise, and does not drop PCA to critical in one
  click.
- Hire-lender card does not appear when you cannot fund
  another month of capacity.

**Files.** `bankgame/sim/advisor.py` (all `_r_*` rules).

### C2. Coordinated advice

If LDR is stretched, the first card is deposits / FHLB, not
hire. If cash is excess **and** LDR is high, prefer funding
loans over buying 3-year notes. Run-defense stays highest
severity.

### C3. “Do it” reports what actually happened

`doSteps` in `web/app.js` should toast the engine messages
and stop on first failure without claiming “Done.” Partial
applies are OK if the toast lists them.

---

## Phase D — A game you sit down to play

### D1. New-game options

Title screen fields, all optional with good defaults:

| Field | Default | Notes |
| --- | --- | --- |
| Bank name | First National Bank of Caprock | as now |
| Seed | random | as now |
| Guided first year | on | as now |
| Home market | Caprock | Caprock / Verhalen / Plainview / Lubbock. Metros locked until we have A1. |
| Era | Sandbox clock, date labeled “Year 1” | See F3. Alternate: Historical 2000 (real-ish path). |
| Difficulty | Standard | Easy: extra $1M capital, slower examiners. Hard: thinner capital, hotter competition. |
| Goal | Stay independent 20 years | See D2. |

**Files.** `bankgame/sim/newgame.py` (`new_game` grows a
`meta` block); `web/app.js` (`showSaves`, `newGame`);
`bankgame/server.py` `/api/new`.

Charter (state vs national) either becomes a real small
modifier (exam cadence, assessment) or is removed from the
UI so it stops looking like a choice. Do not leave a dead
dropdown.

### D2. Goals / scenarios

Sandbox remains. On charter, pick one primary goal. Desk
shows a progress chip. None of these pause the sim; they
are scoring frames.

- **Stay independent N years** — decline buyouts, avoid
  seizure.
- **Best bank on the square** — home-market share + CAMELS
  ≤ 2 + ROA vs peers, 10 years.
- **Don’t be the next headline** — survive a credit bust
  and a rate shock with no run and no 4-rated exam.
- **Regional, not reckless** — $500M–$2B, still well-
  capitalized, CRA satisfactory.
- **Sell well** — accept a buyout ≥ 1.8× TBV after year 8.

Goal completion is a *win modal* (not a hard stop): keep
playing or retire to the title screen.

**Files.** `bankgame/sim/advisor.py` or new
`bankgame/sim/goals.py`; Desk + title UI.

### D3. Month digest

Replace the raw news firehose on Dashboard with a monthly
digest: economy one-liner, your P&L, deposit/loan flow,
one local headline if it is *your* market, exams/window/
frauds. Full log stays on Events.

**Files.** `bankgame/sim/engine.py` (compose digest at
month close); `web/app.js` (`tabDashboard`).

### D4. Autopsy

Seizure / sale / retire writes a structured summary:

- Years, final assets, goal outcome.
- Last exam components in owner language.
- Peak LDR, window uses, unrealized / CET1.
- The three events that mattered (first 4-rated exam,
  the Dallas branch, the vintage that charged off).
- One sentence the advisor would have said a year earlier.

**Files.** `bankgame/sim/engine.py` (`_game_over`);
`web/app.js` (`renderGameOver`).

### D5. Juice, lightly

No soundtrack required. Do give: a distinct exam modal,
a quarter-close card with three numbers (NI, CET1, LDR),
a CAMELS 1 that feels like a win, a run banner that is
impossible to miss (already partly there). Keyboard focus
trap in modals. Confirm on HTM sell stays.

---

## Phase E — Credit is the heart

Do this before any new business line.

### E1. Memos that are a decision

Keep the one-page memo. Add:

- Why this borrower (industry, years in market, deposit
  relationship if any).
- What happens if we decline (they go to a named rival).
- A one-line exception to policy if standards are tight
  and the tier is C.
- Owner-language gloss on DSCR / LTV next to the numbers
  (already in `DICT`).

**Files.** `bankgame/sim/loans.py` (`_make_application`).

### E2. Counteroffer and participate

Approve / Decline is not enough for a $1.8M CRE.

- **Counter:** +50–150 bp, lower hold, shorter term, extra
  collateral. Borrower accepts/rejects with a simple roll.
- **Participate:** book 25–50%, rest sold (counterparties
  are rivals / FHLB). This is also the escape hatch for
  A5’s “we cannot fund the whole thing.”

**Files.** `bankgame/sim/loans.py`; `bankgame/sim/engine.py`
(new actions); `web/app.js` (`showMemo`).

This also covers the DESIGN.md “loan sales/participations”
item at the only place it matters: the desk.

### E3. Recurring borrowers

Large credits persist as names. A performing relationship
comes back. A declined A-tier remembers. A charged-off
name can become a caution in a later memo. Cheap to store
(list on `bank["loans"]["relationships"]`).

### E4. Mortgage sale is already a lever — teach it

The secondary-sale % on Lending is easy to miss. Advisor
card when LDR is high and the mortgage book is growing:
“Sell more of the new production.” Preview already-style.

---

## Phase F — World signal vs noise

### F1. News filter

Region shocks (`regions.step_month`) only enter the inbox
if you have deposits, loans, or a branch there — plus at
most one national wire per month. Full world still ticks
for rivals and for Markets-tab color.

**Files.** `bankgame/sim/regions.py`; `bankgame/sim/engine.py`
(`push_event`).

### F2. Fraud is rarer and meaner

Current cadence (5–8 cases in 3 years, lots of check
kiting) becomes wallpaper. Cut frequency, raise the
occasional six-figure wire, keep the Act / Monitor
choice. Cases stay on Desk.

**Files.** `bankgame/sim/fraud.py`.

### F3. Era: sandbox clock vs historical path

Two charter options (D1):

- **Sandbox.** Calendar is “March, Year 3.” Copy never
  names 2023 SVB unless we invent a peer failure in-world.
  Social-media speed still rises with *years played*.
- **Historical 2000.** Economy is nudged toward a
  recognizable path (dot-com, 2001 cut, 2004–06 boom,
  2008 bust, ZIRP, 2022 hike) without hard-scripting
  every month. SVB-style copy is allowed after 2015.

Default for guided newcomers: sandbox, so the date and
the model do not fight.

**Files.** `bankgame/sim/economy.py`; `bankgame/sim/newgame.py`;
copy in `advisor.py` / `crises.py`.

### F4. Markets tab teaches geography

After A1/A2, Markets is where you plan the next county:
kind, pool, **your current share vs a $25M bank’s natural
ceiling**, activity, shock. Rival table can stay. Owner
labels from B3.

---

## Phase G — Calibration

Only after A and B. Otherwise we are tightening a printer
that also secretly uses the window.

### G1. Benign-era profitability

Target for a passive, well-run, no-expansion bank in a
normal expansion: **ROA 0.9–1.3%**, **efficiency 55–70%**,
**ROE** poor if you hoard capital (the hoarding card is
correct). Knobs already named in `DESIGN.md`:
`operations.monthly_opex`, `BASE_PD`, competitor
`loan_stance`.

**Files.** `bankgame/sim/operations.py`, `loans.py`,
`competitors.py`. New `tests/test_calibration.py` that
runs 3 years × N seeds and asserts bands (not point
values).

### G2. Trailing metrics need a real trailing window

First closed month currently annualizes ×12 → ~2.7% ROA
on the opening book. Either show “month annualized
(noisy)” until 6–12 months exist, or do not annualize
until quarter 2. Same for efficiency.

**Files.** `bankgame/sim/statements.py` (`compute_metrics`);
Desk / Dashboard copy.

### G3. Exams after liquidity is a choice

Once A4/A5 ship, a fortress book with C1 A1 E1 S1 should
not draw L4 from silent wholesale. If L is still 3–4,
it is because the player ran LDR hot or used the window.
The “max(avg, worst−1)” rule can stay — it is realistic —
but the worst component must be one they saw coming
(B7 + Desk).

Management score: starting 3-person bank should not need
a compliance FTE on day 1; the current “ops counts as
0.35 BSA” is fine. Do not add a BSA trap before year 3
at this size.

### G4. Opening book

Keep the West Texas $20M start. Consider:

- Slightly more sticky deposits or a slightly smaller
  loan book so month-1 LDR is ~0.75, not already tight.
- Opening cash high enough to open **one rural** branch
  without selling the bond portfolio, *or* the Verhalen
  button is honest that you must sell/raise first (A2).

---

## Phase H — Later depth (only after A–E)

These are the DESIGN.md “next depth pass” items, rewritten
as project work. Do not start H to avoid finishing A.

| Item | Why it waits | Sketch |
| --- | --- | --- |
| Per-market deposit pricing | Useless until A1 share is sane | Offsets by market; promo money; Desk card when one town is leaking |
| Competitor M&A vs your targets | Needs A3 pipeline | Rivals can buy the bank you were sizing |
| Examiner MRAs with deadlines | Needs B7 exam as set piece | “Raise liquidity ratio above 10% by September” |
| EVE / ±100–300 bp dashboard | Needs B3 owner labels | Treasury panel, not a new tab |
| Named officers (CFO, CCO) | After E3 relationships | Traits that nudge capacity, exam M, defects |
| Holding-company double leverage | Late-game only | Unlock with a D2 regional goal |
| Business lines (trust, insurance, merchant, correspondent, IB) | Currently a click + P&L drip | Each line gets **one** recurring decision or it stays hidden from the first-hour UI |
| Charter | Real small modifier or gone | See D1 |
| Digital / core already exist | Teach them | Advisor cards are enough; no new systems |

---

## Test plan (whole project)

Keep the existing suite. Add:

| File | Guards |
| --- | --- |
| `tests/test_markets.py` | A1 share caps; Verhalen safe; Dallas not fatal in 90 days |
| `tests/test_funding_decisions.py` | A4 blocking vs auto; books still balance |
| `tests/test_origination_throttle.py` | A5 LDR bound on passive play |
| `tests/test_advisor.py` (extend) | C1 every card legal and funded |
| `tests/test_advance_inbox.py` | B4 quarter does not expire memos |
| `tests/test_calibration.py` | G1 bands, G2 no 2.7% day-30 ROA claim |
| `tests/test_ma.py` | A3 size and deny-does-not-mutate |
| existing ledger / determinism / interest | still green, always |

Determinism test must be re-golden if we add RNG draws;
use the named streams (`event`, `credit`, `ops`) so econ
does not twitch.

---

## Ship order (how this actually gets built)

One PR per lettered item when possible. Do not batch A1
with E2.

```
A1 share math
A2 branch preview          } can overlap once A1 lands
A5 origination throttle
A4 overnight decisions
A3 M&A sizing
        ↓
B1 day-1 gauges
B4 inbox-aware clock
B5 / B7 first credit + exam
B2 / B3 / B6 title, owner view, shortcuts
        ↓
C1–C3 advisor
        ↓
D1–D4 goals, digest, autopsy, new-game
        ↓
E1–E4 credit
        ↓
F then G
        ↓
H only if the game is already recommendable
```

After each phase: run the unittest suite, then a headless
campaign pack (the playtest script: passive 3y × 4 seeds,
fortress 5y, Dallas-branch 90-day, advisor-follow 5y) and
paste the summary in the PR.

---

## File map (quick)

| Area | Own |
| --- | --- |
| Share / deposits | `bankgame/sim/deposits.py` |
| Branches / staff | `bankgame/sim/operations.py` |
| Overnight / FHLB / window | `bankgame/sim/funding.py` |
| Origination / memos / large | `bankgame/sim/loans.py` |
| Exams / BSA / PCA | `bankgame/sim/regulation.py` |
| M&A / turn loop / actions | `bankgame/sim/engine.py` |
| Gauges / cards / tutorial | `bankgame/sim/advisor.py` |
| Opening book / meta | `bankgame/sim/newgame.py` |
| Metrics | `bankgame/sim/statements.py` |
| Economy / era | `bankgame/sim/economy.py` |
| Shocks | `bankgame/sim/regions.py` |
| Fraud | `bankgame/sim/fraud.py` |
| HTTP | `bankgame/server.py` |
| Saves | `bankgame/store.py` |
| UI | `web/app.js`, `web/style.css`, `web/index.html` |

---

## Out of scope (on purpose)

- Multiplayer, accounts, cloud saves.
- Pixel art, soundtrack, mobile-first layout (desktop dense
  dashboard stays the skin; just don’t overflow at 1100px —
  already partly handled).
- Individual household agents.
- Rewriting the stack (no React, no Postgres, no pip).
- Making charter, Durbin, or G-SIB the tutorial.

If a new idea is not on this list, it goes under H or it
loses to an open A/B item.

---

## Playtest evidence (why A is not optional)

| Run | What happened |
| --- | --- |
| Day 1 | $19.7M assets, $2.5M equity, $2.2M cash, CET1 20.8%. Gauges green on fake 1.10% ROA. No advisor cards. |
| Passive 3y × 4 seeds | Assets ~$27M, ROA 1.6–2.3%, efficiency ~43%, loans outrun deposits, cash ~$800k, CAMELS often 3, window used. |
| Advisor-follow 5y | $37M, then CAMELS 4 + consent order. Log flooded with “not enough liquidity to fund this loan.” |
| Fortress 6y | CET1 28%, NPA 0.2%, ROA 2.3%, still L=4 path, 40 window uses, LDR 1.37. |
| Dallas branch | $5M raise + 1 branch → $883M Dallas deposits in one quarter → seized. Open cost was $2.88M vs $1.8M button copy. |
| Verhalen branch | +~$5M deposits in a year, still well-capitalized. This is the intended growth. |
| Year-1 events (one seed) | 3 loan apps (tutorial said “most months”), 0 exams yet, 2 window news items. |

---

## Status

- [x] Playtest and this plan
- [x] Phase A (A1 share, A2 preview, A3 M&A size, A4 overnight ask, A5 throttle)
- [x] Phase B (B1 gauges, B2 title Continue + no auto-load, B3 owner labels on bar/peers/exam, B4 inbox clock, B5 seeded first credit, B6 shortcuts, B7 exam pill). Save-row year/CAMELS and welcome-must-click-a-gauge still open.
- [x] Phase C (C1 goto actions, C2 hire-lender gate, C3 toast what happened)
- [ ] Phase D
- [ ] Phase E
- [ ] Phase F
- [ ] Phase G (G2 partial-window flag only; G1 bands still open — benign ROA is still ~2.5%)
- [ ] Phase H (optional)
