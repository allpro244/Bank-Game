# Playtest improvement plan (Phase I)

This is the next working plan after Phases A–G. It comes from two
independent play-to-win sessions of the same prompt — become the biggest
bank in the world, see how much you can make, write down what is
frustrating or unrealistic.

- **Grok session** (this repo’s cloud agent): fortress and “grow now”
  owners, seed 11 and others. Best honest book **$1.2B in 26 years**,
  then seizure. Report lived in the PR #7 thread; the two player-facing
  lies from that session (goal bar, whale FDIC) already shipped.
- **Claude session** (`PLAYTEST_TYCOON.md`, commit `2f37e77`): four
  attempts, best honest book **$81.2B in 143 years**, seized year 144.
  Report only — no engine changes.

Neither session reached **$250B**. Both found the same spine. Phase H
(holding company, new business lines, named officers as flavor) stays
parked until this pass makes the stated game playable.

`DESIGN.md` is still the model reference. `ROADMAP.md` stays the index.
This file is what we build next, in what order, and what “done” means.

**Status:** I1–I7 shipped in PR #9. The crown is winnable (`PLAYTEST_WORLD_CROWN`
on Claude’s report: $253B / y86). I8 (PR #10) breaks the CAMELS 3→MOU→M
loop and the leftover playtest findings on that same build: metro offices
no longer stack full catchments, lenders scale with franchise size, raise
cards cool down, and Play until advances through a CAMELS 4 or an active
run. The $250B number still does not move.

---

## Thesis

A–G shipped the first-hour contract. The default goal still fails its
own promise:

1. A human cannot play the clock to megabank scale.
2. The industry dies, so “biggest on the map” becomes “last one standing
   in an empty country.”
3. The moves that look like running a bank (hire, branch, digital,
   compliance) lose money at the scale the charter starts.
4. Several lethal systems still fire without a preview, or fire in
   secret, or do not post to the books they claim to spend.

Fix those four. Do not add a product line to paper over them.

---

## Laws (do not violate)

Same eight as `ROADMAP.md`. Two clarifications for this pass:

9. **“Play until something needs me” is a clock, not an advisor.** The
   player writes a standing policy (credit box, overnight, interrupt
   list). The clock executes that policy and stops when something is
   outside it. The advisor still only recommends moves the player could
   make by hand. Auto-approving credits the player never configured is
   illegal.
10. **Trade-area is not a repeal of A1.** A $20M bank must not claim 8%
    of Dallas. A Dallas *branch* serves a catchment of a few miles, not
    the entire metro pool. Size caps stay. The gather number changes.

Integer cents, named RNG streams, no third-party packages. Rivals stay
reconstructed call-reports — no second live general ledger.

---

## Already shipped (do not redo)

| Item | Where |
| --- | --- |
| Phases A–G | `ROADMAP.md` status |
| Overnight uses Fed balances before asking | PR #3 |
| World goal as default | PR #2 |
| Fable 12 + owner-facing playtest bugs | PR #4 |
| Rival call-report books | PR #5 |
| Fraud case clears its inbox event | PR #6 |
| World-goal bar tracks living leader + $250B | PR #7 |
| FDIC bid refused if pro-forma is not well-capitalized | PR #7 |
| `skip_inbox` plumbed through `/api/advance` + “Advance anyway?” | PR #4 / B4 |

PR #7 is on `cursor/world-goal-honesty-e5c4`. Merge it before starting
I4 leftovers that assume the whale gate exists.

---

## Finding → work item

Every line from both sessions. Status is **open** unless marked shipped.

### Playability

| ID | Finding | Source | Item |
| --- | --- | --- | --- |
| P1 | ~1,560 clicks / first decade; 2,014 quarter-presses advanced 0 days | Claude F1 | I1 |
| P2 | `skip_inbox` exists but the player still babysits every memo | Claude F1, PR #4 | I1 |
| P3 | World crown is tens of thousands of clicks | Claude F1 | I1 |

### Living industry / goal meaning

| ID | Finding | Source | Item |
| --- | --- | --- | --- |
| W1 | All 12 rivals extinct by year 10–20, four seeds, **0 new charters** | Claude U1 | I2 |
| W2 | Empire $26B → $63B in 10 years (9.3%/yr) then dies | Claude U2 | I2 |
| W3 | After the field dies, “beat living rivals” is free | Claude F5, Grok | I2 |
| W4 | Private deals are 10–35% of *your* size — you never buy Empire | Grok | I2 |
| W5 | Organic 12 towns + metro caps cannot reach $250B | Grok | I2, I3 |
| W6 | Goal bar measured Comanche Peak, then 55% at $1.2B | Grok | **shipped PR #7** |

### Growth economics

| ID | Finding | Source | Item |
| --- | --- | --- | --- |
| G1 | Do-nothing 1.08% ROA; +1 lender −0.48pp; +1 compliance −0.51pp; all-in −0.25% | Claude F2 | I3 |
| G2 | Advisor “hire a lender” is advice to lose money at $20–40M | Claude F2 | I3, I7 |
| G3 | Marketing +$5k/mo is the one profitable lever (+0.07 ROA, +26% assets) | Claude F2 | I3 (keep; do not make it the only one) |
| G4 | Small-bank opex 5.8–9% of assets vs ~3% real | Claude U4 | I3 |
| G5 | One Dallas branch gathers 0.002% of the pool, −$510k NI; Lubbock +$427k | Claude U5 | I3 |
| G6 | LDR stuck above 1.00 (peak 1.20) without trying | Claude U6 | I3 |
| G7 | Sit-still year 1 is a loss; law says well-run ~1.0–1.3% | Grok | I3 |
| G8 | Digital L1 is a $1.5M expense on a $40M bank, not an asset | Grok, Claude F2 | I3 |
| G9 | Cannot open a second office in a town you already serve | Grok | I3 |
| G10 | “Grow now” died in 18 months at $72M (digital + fire-sale equity) | Grok | I3, I4 |

### Lethal / dishonest money

| ID | Finding | Source | Item |
| --- | --- | --- | --- |
| L1 | $50M bank won Lone Star ($4.3B), “WON FDIC AUCTION”, seized next month | Claude F3 | **shipped PR #7** (refuse if not well-cap); I4 adds the 86× copy |
| L2 | $48M → $1.1B overnight, equity −$19M | Grok | **shipped PR #7** |
| L3 | Common equity at 0.37× book when ROE is red; 5% fee; no preview | Grok | I4 |
| L4 | Overnight **auto** still racks 700–1,600 window draws → Liquidity 4 | Grok | I4 |
| L5 | CAMELS 4 is a tar pit; M&A needs 1–2; stuck for decades | Grok | I5 |

### Invisible systems / books

| ID | Finding | Source | Item |
| --- | --- | --- | --- |
| H1 | Deposits $27.6M → $8.1M (−70%) while paying 88bp over market, brand rising; screens never say “run” | Claude F4 | I5 |
| H2 | `regulation.bsa.program_spend` and `fraud.prevention_spend` never post | Claude U3 | I6 |
| H3 | Negative `cached_assets` → complex number in `fraud.py` → day loop dies | Claude C1 | I6 |

---

## Definition of done (this pass)

A stranger who picks **Biggest bank in the world** can:

- Press **Play until** and reach year 10 without four thousand empty
  clicks. Routine A/B credits follow a box they set. The clock stops on
  exams, runs, fraud, overnight holes, and anything outside the box.
- Hire the first lender and see that lender’s extra production cover
  fully-loaded cost. The hire-lender card does not appear until that is
  true.
- Open Dallas and gather a **trade-area** book that is expensive and
  slow — not −$510k/year forever, and not $883M in a quarter.
- Open a second office in Caprock (or any served town) with diminishing
  gather and an honest preview.
- Look at Markets in year 20, four seeds, and see **living banks**.
  Failures become bigger survivors and occasional new charters, not an
  empty map.
- See a run on **Deposits** and Desk the week it starts, not only in a
  modal that already scrolled by.
- Raise common through a preview (price, shares, fee, pro-forma CET1).
  A one-year red ROE does not clear at 0.37×.
- Leave overnight on **auto** for a quiet book and not collect a
  three-digit window count.
- Recover a CAMELS 4 in a visible number of exam cycles after they fix
  the component that caused it — or the Desk says exactly why they
  cannot.
- Pay for BSA and fraud programs on the ledger. Negative assets do not
  crash the day loop.

The $250B crown is **reachable in a long campaign** (play-until, living
field, metro catchments, size-gated M&A once you are in the weight
class) — not 185 years of +1 Qtr, and not “wait for the map to die.”
If after I2+I3 a headless campaign still cannot pass $50B in 60 years
without exploits, we revisit the crown number or the default goal. We
do not invent a printer.

Plus: `python3 -m unittest discover -s tests` stays green, including
the new campaign pack below.

---

## I1. Clock you can actually play

**Problem.** B4 and PR #4 made week/month/quarter *stop* on the inbox
and added “Advance anyway?”. That is the right safety rail. It is also
why Claude measured 2,014 zero-day quarter presses. Every large credit
lives 60–90 days and blocks the clock. There is no standing policy, so
every memo is a babysitting click. The world goal is physically
unreachable in a human session.

**Desired.**

- **Play until** (Desk + clock): advance day-by-day until an interrupt.
  Interrupts: exam, fraud case, run start/update, overnight ask, PCA
  drop, CAMELS 4/5, seizure, and any credit **outside** the policy box.
  Month digest still writes. This is a clock loop over existing
  `advance(..., "day")`, not a new sim.
- **Credit policy box** on Lending (player-written, saved on the bank):
  approve A/B at posted rate up to $X hold; counter C; decline D;
  participate if hold would exceed $X. Defaults conservative on guided
  / owner. Changing the box is a decision, previewed.
- Credits the box handles do **not** stop Play until. They still appear
  on the month digest (“3 A-tier CRE approved under your box”).
- `+1 Wk / Mo / Qtr` keep today’s stop-or-confirm. Play until is the
  new primary for long sessions.
- Advisor never writes the box and never clicks Approve for you.

**Files.** `bankgame/sim/loans.py` (policy + apply); `engine.py`
(`play_until` / interrupt list); `advisor.py` (do not auto-fill the
box); `server.py`; `web/app.js` (Desk button, Lending box, digest).

**Tests.** `tests/test_play_until.py`

- Seeded A-tier under a matching box: Play until crosses 90 days, memo
  is booked, inbox empty, trial balance 0.
- Seeded D-tier when the box says decline: declined, clock continues.
- Seeded hold-too-large: clock **stops**, memo still queued.
- Run start, overnight ask, exam, fraud: each stops Play until.
- Determinism: same seed + same box → same dates booked.

**Not in scope.** Named officers as characters (Phase H). A “CCO”
label on the box is fine; traits that nudge in secret are not.

---

## I2. Living industry

**Problem.** `competitors.step_month` grows every rival by a strategy
tilt (`rate_leader` 1.4×, `digital` 1.8×) then fails them on a hot
`months_weak` clock (`fail_p` 0.08 + stress after 4 weak months; 0.5
if equity < 2%). No new bank is ever chartered (`next_id` exists and
is unused). After year ~20 the map is empty, `beats_rivals` is free,
and the default goal is “sit alone until $250B.” Private deals spawn
at 10–35% of *your* assets, so a $40M bank is never offered Empire.

Rivals stay **scalars**. Do not build them a live GL.

**Desired.**

- **Size-dependent growth.** Community rivals may compound in the
  mid-single digits. Money-center names (Empire, Knickerbocker, Lone
  Star) slow toward GDP + 1–2%. Hard ceiling so the roster cannot
  outgrow US banking assets.
- **Failures leave survivors.** Weak banks are more often **bought by
  a living rival** than closed. FDIC auctions still happen — rarer,
  and still size-gated (PR #7). Floor: at least ~8 living banks
  through year 20 on a quiet seed; never 0 while the player is
  standing unless the player caused a systemic event we have actually
  modeled.
- **New charters.** A handful per decade into emptied towns, community
  scale, named from a list. Uses `next_id`.
- **Rival–rival M&A** is the main consolidation. The player can still
  bid when the target is in their weight class (A3 + PR #7). Once the
  player is regional, they may be offered a slice of a larger book —
  never 86× overnight.
- **Private deals can be larger than you** when you are well-capitalized
  and CAMELS 1–2, with the same pro-forma refuse as FDIC. The 10–35%
  cap becomes a *community-era* cap, not a lifetime cap.
- **World goal.** `beats_rivals` requires a living field (or a recorded
  crown you actually passed). An empty map is a failed world, not a
  shortcut. Desk copy says so. The bar already tracks leader + $250B
  (PR #7); keep that.

**Files.** `bankgame/sim/competitors.py` (`step_month`, `_franchise`,
new charter + rival-buy helpers); `engine.py` (`_ma_opportunities`);
`goals.py` (empty-field copy); Markets UI can stay.

**Tests.** `tests/test_industry.py`

- Idle player, seeds 7 / 99 / 2024 / 555: living count at y5 ≥ 10,
  y20 ≥ 8, y30 ≥ 6. At least one new charter by y20.
- Empire 10-year growth < 5%/yr (not 9.3%).
- A failed community rival is absorbed by a living peer more often
  than it becomes an FDIC card (assert on a 20-year pack).
- Empty field ⇒ world goal `beats_rivals` is false.
- $40M bank is not offered a $4B private deal; $2B regional may see
  a larger-than-self deal that still refuses if pro-forma fails.

---

## I3. Growth economics

**Problem.** G1 tuned a *passive, no-hire* book into the 1% ROA band.
The moment the player does what the advisor and the tycoon goal ask —
hire, branch, digital — the book goes red. Claude’s A/B: one lender
−0.48pp ROA. One-branch opex prints 5.8% of assets ($135k/mo on $28M)
against a real community-bank ~3%. `natural_share` applies presence to
the **entire** metro pool, so A1’s size cap (correct, do not lift)
makes one Dallas office gather nothing. One office per market × 12
towns is the entire franchise. Loan demand outruns deposits, so LDR
sits above 1.00. Year-one sit-still is still a loss. Digital L1 is
`$1.5M × (1+level)^1.6` expensed on day one.

**Desired.** Growth is *risky*, not *arithmetically losing*.

### I3a. Overhead scales like a community bank

Target: sit-still, no-expansion, opening staff: **opex / assets ~2.8–3.5%**,
**ROA 0.9–1.3%** in the first *full* trailing year (not a red year-1
then a lucky year-3). Staffed-up still costs — a compliance officer
is not free — but one lender must earn more NIM than they cost.

Knobs: `operations.monthly_opex` (`other` is `1.10% of assets + $12k`
today, plus tech `0.26%`, plus salaries × 1.38). Decline the asset
rate as the book grows so a $1B bank is not paying community % on
money-center assets.

**Files.** `operations.py`, `tests/test_calibration.py` (extend).

### I3b. A lender’s production covers their cost

`loans.lender_capacity` vs fully-loaded salary. At opening scale, the
marginal lender’s extra originations (and the deposits that follow a
relationship book) must cover salary + benefits + a slice of occupancy.
If the math is still negative, **raise production**, do not hide the
card.

Hire-lender advisor card only when the preview is NI-positive over 12
months (I7).

**Files.** `loans.py`, `operations.py`, `advisor.py`.
**Tests.** Same-seed 6-year A/B: +1 lender ⇒ ROA ≥ do-nothing − 0.10pp
and assets up. Compliance still costs; it must not cost half a point
of ROA on a $25M book.

### I3c. Trade-area share (metros)

Each market gets a **catchment** per office, not a claim on the whole
pool:

| Kind | Catchment per office (order of) |
| --- | --- |
| Rural / peer | Most of the town pool |
| Small metro (Lubbock, Midland) | A real slice; already almost works |
| Metro (Dallas, Houston, Austin) | ~$0.8–1.5B pool per office, ramps with years-in-market |
| Money center (NYC) | Smaller still; labeled as a capital event |

`size_share_cap` still applies. A1 tests stay: Dallas in 90 days is
not seizure; Verhalen is the safe second county.

**Files.** `deposits.py` (`natural_share`, `year1_gather_estimate`,
new `trade_pool`); `tests/test_markets.py`.

**Tests.** One Dallas office, 8 years, $20M start: year-1 gather in a
community-bank band (tens of millions, not $4M and not $800M);
trailing NI not a structural −$510k. Lubbock still beats Dallas on
year-1 NI. A1 Dallas-90-day cap still holds.

### I3d. Second office in a served town

`open_branch` currently returns `"already have a branch in this
market"`. Allow another office. Presence scales with count;
catchments overlap (diminishing gather — `office_effective`, not
`cap_one * n`). Preview already has cost / year-1 gather / pro-forma
capital — use it. Cannot close the last office (already true).

**Files.** `operations.py`, `deposits.py`, `web/app.js` (Ops rows).
**Tests.** Second Caprock office opens; year-1 incremental gather <
first office; books tie; last-branch close still refused.

### I3e. LDR can sit still under 1.00

A5 claimed a throttle. Claude still saw LDR > 1.00 most of every
tycoon run. Tighten the idle throttle and/or let deposit gather fund
a well-run book (I3a–c). Aggressive pay-up / FHLB still lets you run
hot **on purpose**.

**Tests.** Passive 3y × 4 seeds: LDR ≤ 1.05, window rare (already in
`test_calibration.py` — make it fail if we regress).

### I3f. Digital and core are investments with a preview

Keep them as real cash outs (books stay real). Change the lie:

- Cost **scales with assets** so L1 is not $1.5M on a $20M charter
  (or the button is disabled with “raise or wait — this is 7% of
  tangible book”).
- Preview: cash out, monthly run-rate (`digital_level * $25k` today),
  expected gather, pro-forma NI / CET1.
- Optional later: capitalize and amortize so the P&L is not a one-day
  crater. Only if preview + scale is not enough. Depth over a new
  asset class.

**Files.** `operations.py` (`digital_upgrade_cost`, preview helper),
`web/app.js`, advisor card.

### I3g. Year-one sit-still

G2 hides a numeric ROA until six months. The *books* can still be a
loss. Opening earning assets vs opex should print a small profit (or
a rounding-error loss) in the first full trailing year if the player
does nothing dumb. Law 7 is the spec.

**Tests.** Sit-still seeds: first `earnings_ready` year in 0.7–1.4%;
median in 0.9–1.3%.

---

## I4. Honest lethal money

**Problem.** PR #7 stops a whale FDIC close when pro-forma capital
breaks. The card still needs to say “this franchise is 86× your
size.” Common equity uses `roe_ttm` with no through-the-cycle floor,
so one red year clears at 0.37× plus a 5% fee and no modal.
Overnight **ask** is honest after PR #3/#4; **auto** still walks
FHLB → FF → window and can rack hundreds of window uses on a quiet
book that is structurally loaned-up (G6).

**Desired.**

- FDIC / private cards print **size multiple**, pro-forma CET1,
  leverage, and the refuse reason. Whale refuse stays.
- `raise_common` / preferred / subdebt / brokered: **preview
  modal** (price-to-book, shares, fee, pro-forma CET1, tangible
  book). Floor price when `earnings_ready` is false or ROE is one
  bad year (~0.7× at CAMELS 4, ~1.0× at 2). 5% fee can stay if
  shown.
- Overnight **auto**: same stack as `ensure_cash`, then FHLB 3-month,
  then FF to the counterparty limit, **window last**. A quiet
  sit-still book over 3 years uses the window **0 times** unless
  the player ran LDR hot. Every window use still logs.

**Files.** `engine.py` (card copy); `funding.py` (`raise_common`,
`manage_overnight`); `web/app.js`; `tests/test_funding_decisions.py`,
`tests/test_ma.py`.

**Tests.** Preview numbers match the post. Auto + passive 3y × 4
seeds: `discount_window_uses == 0`. CAMELS 4 raise is not below 0.55×
without the modal stating it.

---

## I5. Surface the hidden killers

**Problem.** `crises.py` already models rumor → `run_active` →
outflows, and fires a blocking `run_start`. Claude’s attempt 2 still
read as “balances evaporate”: deposits −70% while paying up, brand
*rising*, nothing sticky on the deposit screens. CAMELS 4 exams every
6 months; composite is `max(avg, worst−1)`; M&A needs 1–2; there is
no Desk card that says what would move the 4.

**Desired.**

- While `run_active` or rumor > 0.25: **banner on Deposits, Desk,
  and the franchise strip** — not only a modal. Copy names the
  cause (capital, uninsured, contagion) from `condition_weakness`.
  Paying up is already a defense; show the edge vs outflow.
- Checking as the “sticky” product must actually be sticky in a
  capital-run (it already has a lower `RUN_SPEED` than MM — if
  Claude saw −88% checking, the weights or the rumor duration are
  wrong). Re-read before changing; do not invent a second run model.
- **CAMELS 4 path out.** Desk card: which component is the floor,
  what number would move it, which actions (raise, cut window, sell
  AFS, shrink LDR) examiners will credit **next exam**. If the 4 is
  earned, it stays. If the player fixed the books and the next exam
  does not move, the exam math is the bug.

**Files.** `crises.py`, `deposits` UI, `advisor.py`, `regulation.py`
(`run_exam` / Desk helper), `web/app.js`.

**Tests.** Force `run_active`: Deposits section payload includes
`run: true` and a cause string. After a manufactured L-only 4, fix
liquidity in-sim, next `run_exam` composite ≤ 3.

---

## I6. Charge what you spend; do not crash

**Problem.** BSA and fraud sliders change detection / compliance and
never hit the GL. Optimal play is max both. `fraud._spawn_case`
does `(cached_assets / 100 / 1e6 / 20) ** 0.5`; negative assets →
complex → `TypeError` in the day loop. Reachable via a hole that
stays negative.

**Desired.**

- Monthly: post `fraud.prevention_spend` and
  `regulation.bsa.program_spend` to expense (5120 / 5170 or a
  dedicated 51xx). `ensure_cash` first. Advisor cards that raise
  these now have a real cost (law 2).
- Guard: `assets = max(1, cached_assets)` before any `** 0.5`.
  Same pattern anywhere else we take sqrt of size.

**Files.** `operations.py` or `regulation.py` / `fraud.py` month
step; `engine.py` month close; `tests/test_playtest_bugs.py`.

**Tests.** $6k/mo BSA spend reduces NI vs control by ~$72k/year.
Negative cached assets: `_spawn_case` does not raise; day loop
continues; trial balance 0.

---

## I7. Advisor tells the truth at this scale

**Problem.** Law 2: if a recommended move loses money or is illegal,
the card is wrong. Hire-lender, digital, Dallas, and “raise common
to grow” all failed that test in the play-to-win sessions. C1/C2
gated some cards; they did not preview NI.

**Desired.**

- Hire-lender, digital, open-branch, raise-common cards carry the
  **same preview** as the button (I3/I4). If 12-month NI is red,
  the card says so and is not `severity: high`.
- Coordinated advice (C2) already prefers deposits / FHLB over hire
  when LDR is hot. Keep it. Add: do not recommend Dallas as the
  second county; Verhalen / Plainview remain the intended move.
- Do not have the advisor write the I1 credit box.

**Files.** `advisor.py`, `tests/test_advisor.py`.

---

## Out of scope (still)

- Phase H: holding company, trust/insurance/IB lines, EVE tab,
  examiner MRA machinery as a new system, named-officer *traits*.
- Live rival ledgers.
- Changing the default goal **until** I2+I3 are measured. If a
  60-year headless pack still cannot pass $50B honestly, then we
  change the crown or the default — in that order, in a later PR.
- Multiplayer, React, pip.

---

## Test plan (this pass)

Keep the existing suite. Add:

| File | Guards |
| --- | --- |
| `tests/test_play_until.py` | I1 interrupts and policy booking |
| `tests/test_industry.py` | I2 census, growth cap, empty-field goal, deal size |
| `tests/test_markets.py` (extend) | I3c trade-area; I3d second office; A1 still holds |
| `tests/test_calibration.py` (extend) | I3a/e/g opex, LDR, year-one, lender A/B |
| `tests/test_funding_decisions.py` (extend) | I4 auto window = 0; raise preview |
| `tests/test_advisor.py` (extend) | I7 cards carry previews; hire gated on NI |
| `tests/test_playtest_bugs.py` (extend) | I6 spend posts; fraud sqrt guard |
| ledger / determinism / interest | still green |

Campaign pack (paste in the PR, do not gold-flake):

```
passive 3y × 4 seeds
fortress 5y
tycoon play-until 20y × 2 seeds   (living count, assets, window, ROA)
Dallas one-office 8y
+1 lender A/B 6y
idle-world 30y × 4 seeds          (rival census)
```

Determinism: new draws go on named streams (`ops`, `credit`, `event`,
a new `industry` stream for charters/M&A). Re-golden
`tests/test_determinism.py` only when that stream is added.

---

## Ship order

One PR per lettered item when possible. Do not batch I2 with I1.

Wave 0 is small and restores the books. Wave 1 makes the map a place.
Wave 2 makes growth legal. Wave 3 makes the default goal playable by
a human. Wave 4 is copy and advisor, after the numbers are true.

```
I6  charge BSA/fraud; guard fraud.py          } Wave 0 — correctness
I4  capital preview; auto overnight           } Wave 0 — leftover honesty
I5  run banner; CAMELS-4 path                 } Wave 0 — visible failure
        ↓
I2  living rivals, charters, deal weight      } Wave 1 — the map
        ↓
I3a opex band
I3b lender production
I3c trade-area metros
I3d second office
I3e LDR sit-still
I3f digital preview / scale
I3g year-one sit-still                        } Wave 2 — economics
        ↓
I1  Play until + credit policy box            } Wave 3 — clock
        ↓
I7  advisor previews                          } Wave 4
        ↓
Measure the 60-year pack. Only then touch
the $250B number or the default goal.
        ↓
H only if the game is already recommendable
```

I3c before I3d (second office uses catchment overlap). I2 before I1
is allowed to overlap once I2’s census tests are green — the clock
does not depend on charters.

---

## File map (this pass)

| Area | Own |
| --- | --- |
| Play until / interrupts | `engine.py`, `web/app.js` |
| Credit policy box | `loans.py`, Lending UI |
| Rival life / charters / rival-M&A | `competitors.py` |
| Deal size / FDIC copy | `engine.py` |
| World-goal empty field | `goals.py` |
| Opex / digital / second office | `operations.py` |
| Trade-area share | `deposits.py` |
| Lender capacity | `loans.py` |
| Capital preview / overnight auto | `funding.py` |
| Run payload | `crises.py`, Deposits UI |
| CAMELS path | `regulation.py`, `advisor.py` |
| BSA / fraud expense + sqrt | `fraud.py`, `regulation.py`, month close |
| Advisor previews | `advisor.py` |

---

## Open questions (decide in the first PR of that wave, not now)

- **Play until stop list.** Start strict (stop on every large credit
  without a box). Loosen only if the 20-year pack is still unplayable.
- **Capitalize digital?** Preview + scale first. Amortize only if the
  P&L crater remains the lie.
- **Crown number.** Do not change $250B until I2+I3 are measured.
- **CAMELS 3 M&A.** Do not loosen A3’s 1–2 gate to paper over I5.
  Recover the 4, or say why you cannot.

If a new idea is not in the finding table, it goes under H or it
loses to an open I item.
