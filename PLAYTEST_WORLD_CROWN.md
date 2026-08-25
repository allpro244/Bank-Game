# Playtest: the world crown on the PR 7–9 build

Head `43a1dd2`. 141 tests green. Two 170-year runs for the **world** goal
(pass every living rival, then pass $250B), played legitimately.

## Headline: the crown is now winnable

**Run 2 reached $253.14B in year 86 (Jan 2083), rank 1 of 9 — goal won,
bank still standing.** On the previous build my best was $81B peak with a
seizure at year 144 and an estimated ~200 years to the crown. That is the
single biggest improvement in the project so far.

| Milestone | Run 2 |
|---|---|
| $100M | year 18 |
| $1B | year 41 |
| $10B | year 44 |
| $50B | year 55 |
| $100B | year 70 |
| **$250B — crown** | **year 86** |

### My findings that PRs 7–9 fixed (verified)

| Finding | Status |
|---|---|
| Metro branches gather ~nothing (whole-pool share) | **Fixed** — `CATCHMENT` trade-area model; metro expansion now scales with offices |
| Rivals all extinct by year 20, no new charters | **Fixed** — 8 rivals alive at year 170; `_spawn_charter` fills emptied towns |
| Digital level 1 costs 59% of a new bank's equity | **Fixed** — cost scales with assets (a $20M charter pays 22% of sticker) |
| FDIC auction has no size limit (a $50M bank won a $4.3B franchise) | **Fixed** — whale gate; I was correctly told to pass six times |
| `skip_inbox` built but wired to nothing | **Fixed** — plumbed to API and UI |
| Negative assets crash the engine (`(neg) ** 0.5`) | **Fixed** |
| BSA / fraud spend never charged to the ledger | **Fixed** — $500k/mo now costs real money |

---

## The story of Caprock Financial (run 2)

- **2000** — Chartered. $19.7M, three employees, one branch on the courthouse square.
- **2001** — First examination: **composite 4**. Six months later, a 2. (See W3.)
- **2003** — First deal: Security Bancorp, $825K. Construction lending launched.
- **2007** — Composite 4 again as the credit cycle turns. Back to 2 by mid-2008.
- **2009–2034** — The golden years: ratings of 1 and 2, small tuck-in acquisitions
  (Pioneer, Frontier Savings, Frontier Bank & Trust), and **three buyout offers
  turned down** — $69M, $92M, $99M. Passed on six FDIC auctions as too big to
  swallow, which is the new whale gate doing exactly its job.
- **2017 (year 18)** — Crossed $100M.
- **2030** — Launched trust & wealth management.
- **2035 (year 36)** — *Finally leaves the home town*: first branch in Plainview,
  then Verhalen, Lubbock, Midland.
- **2039–2042** — $1B, then $10B three years later as the metro catchments compound.
- **2043** — Cyberattack: **$32.6M** of damage.
- **2044** — Capital slips **WELL → ADEQUATE**, clawed back nine months later.
- **2053 (year 55)** — $50B. And from here the examiners never leave: composite
  **4, every exam, for thirty years** (see W1).
- **2067 (year 70)** — $100B.
- **2083 (year 86)** — **$253B. Bigger than every rival. Crown won.**

---

## W1. 🔴 The CAMELS rating is a self-sustaining trap

A fortress bank sat at composite 3 for 65 consecutive years. Diagnosed at
year 45:

```
composite: 3   components: {C:1, A:1, M:4, E:3, L:1, S:1}
CET1 30.6%   NPA 0.21%   liquidity 12.9%   wholesale funding 0.0%
orders: ['Memorandum of understanding']
```

Capital, asset quality, liquidity and rate risk are all **1s**. The composite
is pinned entirely by **Management = 4**, and here is why it can never fall:

1. `regulation.py:361` — `composite = max(composite, max(components) - 1)`, so
   M=4 forces composite ≥ 3.
2. `regulation.py:376` — a composite of 3 **appends a Memorandum of
   Understanding** to `orders`.
3. `regulation.py:351` — `if len(reg["orders"]) > 0: M += 1`.

The rating creates the order; the order sustains the rating. The only exit is
the −1 bonus at line 355, which requires **two executives at skill ≥ 3** — not
signposted anywhere. In run 2 the same loop locked at composite **4** from
2053 onward (a consent order feeding M), so a $250B bank spent its last thirty
years permanently under enforcement while being, by every measurable
component, excellent.

Fix direction: don't let an order that a rating produced feed back into that
same rating; decay M when the underlying causes are cured; or exclude the
self-generated MOU from the `orders` count.

## W2. 🔴 The story flatlines after year 40

Every narrative event in run 1 from year 40 to year 170 — 130 game-years:

| Event | Count |
|---|---|
| "EXAMINATION COMPLETE — Composite rating: 3" | **124** |
| Cyberattack | 9 |
| Threshold crossing | 2 |
| Product launch | 1 |

No runs, no failures, no auctions, no acquisitions, no local shocks reaching
the log. The bank grew from $900M to $59B and *nothing happened*. Combined
with W1, the late game is a spreadsheet compounding quietly while the same
sentence prints once a year. This is the enjoyment problem, not a balance one.

## W3. 🟠 The first examination is a 4 — in year one

Both runs drew **composite 4 at the first exam (March 2001)** on a bank that
had done nothing wrong, then a **2** six months later. A brand-new charter with
clean books being rated "deficient" and then fine is a whipsaw that teaches the
player nothing except that the rating is noise. (Cause is almost certainly the
same M loop: no compliance officer, no credit analyst, no execs on a
three-person bank.)

## W4. 🟠 Run 1 ended as an 86%-equity "bank"

Run 1 finished with **$58.96B of assets against $50.65B of equity** — 86%
equity to assets, ROE ~2%. Retained earnings compounded with nowhere to go
because the deposit franchise stopped scaling once expansion halted. The game
never flags this; a real board would have been buying back stock for decades.
A "your capital is idle" gauge, or pressure to deploy or return it, would make
the endgame a decision instead of an accumulation.

## W5. 🟠 Winning hinged on one unsignposted gate

The **only** difference between run 1 ($59B, no crown) and run 2 ($253B, crown
in year 86) was whether the player keeps opening branches while carrying an
MOU. Run 1's policy — "don't expand while under an order" — is the cautious,
sensible reading, and it costs you the game. The engine only hard-blocks
growth at `growth_cap_active` (composite ≥ 4); the MOU at 3 is advisory. A
player has no way to know that distinction matters this much.

## W6. 🟠 Thirty-six years to leave town

Run 2 didn't open its second market until **2035, year 36**, gated behind
profitability + capital + a clean rating. Everything interesting (metro
catchments, the $1B→$100B compounding) happens after that. The first third of
the game is one branch in one town.

---

## Recommendations

1. **Break the CAMELS feedback loop (W1).** Highest value: it fixes the
   flatline, the year-one whipsaw, and the late-game enforcement absurdity at
   once.
2. **Give the late game events (W2).** Rival moves, market entries against you,
   regulatory regime changes, a newspaper — anything so that year 40–170 has a
   pulse.
3. **Signpost the MOU-vs-consent-order distinction (W5)**, so cautious play
   isn't silently fatal to the goal.
4. **Pressure idle capital (W4)** — a gauge, board pressure, or an activist
   investor when equity/assets runs absurd.
5. **Shorten the opening act (W6)** — let a well-run bank contemplate market #2
   inside the first decade.
