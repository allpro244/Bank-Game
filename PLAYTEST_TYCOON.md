# Playtest: "get as big as possible" / biggest bank in the world

A play-to-win session on the merged branch. Goal set to **world** (beat every
living rival, then pass $250B). Played legitimately — no use of the uncapped
capital-raise exploit from `PLAYTEST_BUGS.md`.

## Result

| Attempt | Strategy | Outcome |
|---|---|---|
| 1 | Aggressive growth (branch + staff early) | **Seized in year 1.5** at $31M |
| 2 | Disciplined, rural-first | **Seized in year 5.5** — deposit run |
| 3 | Lean staff, marketing-heavy, survival-first | **Peak $81.2B**, seized year 144 |
| 4 | Same but looser capital gate | Seized year 73 at $8.5B |

**Best result: $20M → $81.2 billion peak over 143 years.**
Milestones (attempt 3): $100M year 26 · $1B year 59 · $10B year 82 ·
$50B year 143. **The $250B world crown was never reached** and, at the
observed 4–5%/yr terminal growth rate, would take roughly 185–200 game-years.

---

## Frustrations

### F1. The click burden is the game's biggest enemy (measured)
Simulating a player who only presses **+1 Qtr** and clears whatever appears:

- **1,560 clicks in the first game-decade** (~156 per game-year)
- **2,014 quarter-presses that advanced ZERO days**, blocked by the inbox

Every loan application (roughly one a month, 60–90 day life) hard-blocks
week/month/quarter advance. The player presses, nothing happens, clears the
memo, presses again, gets ~5 days, and a new application blocks it. Reaching
even $100M (year 26–40) costs on the order of 4,000–6,000 clicks; the world
crown would cost tens of thousands. `engine.advance()` already accepts
`skip_inbox` — nothing passes it, and there is no "advance anyway" control.

### F2. Every "good banking practice" makes you lose money
Same seed, 6 years, one change each:

| Decision | ROA | Δ |
|---|---|---|
| Do nothing | **1.08%** | — |
| + 1 teller | 1.01% | −0.07 |
| + 1 credit analyst | 0.76% | −0.32 |
| + 1 lender | 0.60% | **−0.48** |
| + 1 compliance officer | 0.57% | **−0.51** |
| + marketing $5k/mo | **1.15%** | +0.07 (and **+26% assets**) |
| + digital level 1 | 0.73% | −0.35 |
| **All of the above** | **−0.25%** | unprofitable |

Doing nothing beats running the bank properly. Hiring one lender — the thing
you must do to originate more loans — costs half a point of ROA. The advisor
card "Your lenders are maxed out → hire one" is, at small scale, advice to
lose money. There is a valley between "tiny and profitable" and "big enough
to afford staff" that the game never signposts.

### F3. Winning can kill you, and the game calls it a win
The FDIC auction has **no size limit** (`engine._resolve_fdic_bid`, L524):
the only gates are CAMELS ≤ 3, PCA, and no BSA order. My **$50M** bank was
allowed to win the franchise of **Lone Star Interstate Bank ($4.3B)** — 86×
its size — logged as "WON FDIC AUCTION", and was seized the following month.
Same for `bank_for_sale`: no relative-size ceiling.

### F4. The death spiral is invisible while it happens
Attempt 2, months 48–60: deposits fell **$27.6M → $8.1M (−70%)** while I was
paying **2.30% money market against a 1.42% market** (88bp over the field),
brand *rising* 30→32, and no rate error. Checking — the stickiest product —
fell 88%. It was a bank run triggered by eroding capital, but from the
numbers alone it reads as inexplicable. Nothing in the deposit screens says
"you are being run on"; the balances just evaporate.

### F5. The world empties out and the goal loses meaning
See U1. Because every rival dies, `beats_rivals` becomes trivially true
(me > $0) and the "biggest bank in the world" goal quietly degrades into
"reach $250B alone in an empty country."

---

## Unrealistic

### U1. Every rival bank goes extinct — always, in every seed
Player idle, world running, four seeds:

| Seed | y5 | y10 | y15 | y20 | y30 | y60 | new charters |
|---|---|---|---|---|---|---|---|
| 2024 | 12 | 12 | 1 | **0** | 0 | 0 | 0 |
| 7 | 12 | 10 | 7 | **0** | 0 | 0 | 0 |
| 99 | 12 | 11 | 5 | **0** | 0 | 0 | 0 |
| 555 | 12 | **0** | 0 | 0 | 0 | 0 | 0 |

All 12 fail within 10–20 years and **no new bank is ever chartered**. From
year ~20 the map is empty: no competitors, no peer comparison, no
acquisition targets, no more FDIC auctions. Real banking consolidates into
*bigger survivors* and issues new charters; it does not mass-extinct.

### U2. Rivals compound without bound while also being unable to survive
Empire Clearing Bank: **$26B → $63B in 10 years** (9.3%/yr, forever). Left
alone, the roster would reach implausible multiples of US banking assets —
except they all fail first. Two opposite unrealisms in one system.

### U3. Two spending levers are free
`regulation.bsa.program_spend` and `fraud.prevention_spend` are read for
their *effects* (compliance score, fraud detection) but **never posted to the
ledger**. Verified: setting BSA spend to $6k/mo produced financials identical
to the penny. Optimal play is to max both — there is no tradeoff to make.

### U4. Small-bank overhead is roughly double reality
A one-branch, ~5-employee bank runs **$135k/month of opex on $28M of assets
= 5.8% of assets**; my first attempt hit 9%. Real community banks run ~3%.
Combined with ~5% revenue, a small bank is structurally unprofitable the
moment it staffs up — which is what produced three of my four deaths.

### U5. A metro branch is strictly irrational
One branch, 8 years, same seed:

| Market | Deposits gathered | Δ assets | Δ net income |
|---|---|---|---|
| Plainview (rural) | $36.9M (15.2% of pool) | +$39.7M | **+$149k** |
| Lubbock (small metro) | $51.1M (1.2%) | +$53.8M | **+$427k** |
| Midland (small metro) | $30.7M (0.5%) | +$32.6M | +$131k |
| **Dallas (metro)** | **$4.4M (0.002%)** | +$3.3M | **−$510k** |

`natural_share` applies presence against the **entire metro pool**, so one
Dallas branch competes with all of Dallas and gathers nothing, while costing
1.6× a rural branch. In reality a de novo branch serves a trade area of a few
miles and would gather $50–100M. As built, you can never enter a big city,
which is precisely the path to megabank scale.

### U6. Permanently loaned-up
LDR sat above 1.00 for most of every run (peaking 1.20) without deliberate
leverage — loan demand outruns deposit generation structurally.

---

## Crash

### C1. Negative assets crash the whole engine
`fraud.py:146` — `(bank["cached_assets"] / 100 / 1e6 / 20) ** 0.5`. With
negative cached assets this returns a **complex number**, and
`max(1.0, complex)` raises `TypeError`, killing the day loop. Reachable via
the uncovered-overdraft path (bug #5 in `PLAYTEST_BUGS.md`: cash can stay
negative indefinitely and is never charged interest).

---

## Improvements, ranked by impact on this playthrough

1. **Autoplay + delegation + plumb `skip_inbox`.** A "play until something
   needs me" button, an "advance anyway" override, and officers who handle
   routine credit under a policy you set. Without this the stated goal is
   physically unreachable in a human session.
2. **Rebalance the growth economics.** Scale small-bank overhead down toward
   3% of assets; make a lender's marginal loan production clearly exceed
   their cost; give branches a trade-area share model so metro entry works.
   Growth should be *risky*, not *arithmetically losing*.
3. **Make the rival world alive.** New charters over time, mergers as the
   main consolidation channel, a cap on rival compounding, and failures at a
   rate that leaves survivors. The peer group and M&A pipeline both depend
   on it.
4. **Size-gate the FDIC auctions and M&A**, with the deal screen stating
   plainly "this franchise is 86× your size — assuming it will breach your
   capital on day one."
5. **Charge for BSA and fraud programs** so the risk/cost tradeoff exists.
6. **Surface the run.** When outflows are run-driven, say so loudly on the
   deposit screens, not only in an event that scrolls past.
7. **Fix C1** and add a guard against negative asset math.
