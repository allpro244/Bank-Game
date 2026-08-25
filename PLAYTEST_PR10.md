# Playtest: PR 10 build — the CAMELS fix verified

Head `08a9ff6`. 152 tests green. Re-ran the **identical** two runs from the
PR 7–9 playtest (same seed 2024, same two strategies) so the numbers compare
directly.

## Result: crown won by both strategies

| | PR 7–9 | **PR 10** |
|---|---|---|
| Cautious strategy (won't expand under an MOU) | $59B, **no crown** | **$300.59B, crown year 119** |
| Aggressive strategy (expands under an MOU) | $253B, crown year 86 | **$300.63B, crown year 119** |
| Difference between the two | **4.3× — the game** | **0.01% — noise** |

Milestones (both runs, identical): $100M y14 · $1B y40 · $10B y47 · $50B y66 ·
$100B y86 · **$250B y119**. Final: $300.6B, rank 1 of 9, 396 branches, CAMELS 2,
never seized, books balanced to the cent.

## My findings from last round — status

**W1 — CAMELS self-sustaining trap: FIXED.** `SELF_ORDERS` now excludes orders
an exam wrote itself from grading Management next time. Same 45-year diagnostic
that previously printed `M=4, composite 3` for 65 straight years now traces
`2222233333334234334343...` — it moves. In the actual runs the bank held
**composite 2 at years 20, 40, 60, 80 and 100**, where before it was pinned at 3
then 4 forever.

**W5 — knife-edge MOU gate: FIXED, twice over.** The two strategies now land
within 0.01% of each other, so the choice no longer decides the game. And the
exam line itself is signposted exactly as recommended:

```
2007-12  EXAMINATION COMPLETE — Composite 3 (MOU: you can still grow)
2001-03  EXAMINATION COMPLETE — Composite 4 (CONSENT ORDER: growth capped)
```

**W4 — idle capital: SIGNPOSTED.** `_idle_capital_letter` fires when equity/assets
> 22% and ROE < 8%, with a working 18-month cooldown (verified directly). See
R2 below for the part that remains.

**W2 — story flatline: MOSTLY FIXED.** A 35-year sample now yields **16 distinct
event types** — `national`, `new_charter`, `rival_merger`, `region_shock`,
`idle_capital`, `fdic_auction`, `bank_for_sale`, `outage` — where the old late
game had essentially three. (My saga script only logs a subset, so its story
looks thinner than the game actually is; that was my logging, not the engine.)

**Also fixed:** compliance FTE need is now sublinear — 20 FTE at $250B instead of
the old 625. And my older bug #8 is properly dead: choosing "wait" on an
overnight shortfall now re-raises after **22–70 days**, not daily (~4/year).

*(I briefly flagged 1,738 overnight shortfalls in 35 years — that was an
artifact of my test clearing pending events without answering them, which
bypasses the cooldown bookkeeping. Not a real bug.)*

---

## What remains

### R1. 🟠 The year-one examination is still a composite 4 — with a consent order

```
2001-03  EXAMINATION COMPLETE — Composite 4 (CONSENT ORDER: growth capped)
2001-09  EXAMINATION COMPLETE — Composite rating: 2
```

Fourteen months into a clean charter, the bank is rated deficient and has its
growth capped — then rated 2 six months later. Nothing happened in between.
This is the last surviving piece of my W3: a brand-new three-person bank has no
compliance officer, no credit analyst and no executives, so Management grades
badly by construction. A first exam should either be a grace visit or grade a
startup on a startup's terms.

### R2. 🟠 The winning bank is still 2.3× levered

Final state: **$300.6B of assets on $130.2B of equity — 43% equity/assets.**
Real money-center banks run 8–12% equity (8–12× leverage). The board letter now
*warns* about this, but the underlying dynamic is unchanged: deposits cannot
scale fast enough to match retained earnings, so capital piles up with nowhere
to go. The warning is honest; the mechanism it warns about still has no cure.
Until deposits can grow into the capital, the endgame bank is a very large,
very safe, very inefficient thing.

### R3. 🟡 The crown moved from year 86 to year 119

The new `office_effective` diminishing-returns curve (extra branches in one
town overlap the same streets) is more realistic and clearly correct, but it
pushed the goal out by 33 years. 119 game-years is a long campaign for a stated
objective — worth a deliberate decision about whether that is the intended
length, especially since pacing/click-burden was already the top complaint.

### R4. 🟡 Strategy may now be *too* convergent

Two deliberately different policies produced $300.63B and $300.59B. Last round
that gap was the whole game; now it is rounding error. Robustness is good, but
if every reasonable strategy converges on the same number, the world-goal
campaign stops rewarding judgment. Worth watching alongside the archetype
findings in `PLAYTEST_STRATEGIES.md`.

---

## Recommendation

R1 is a small, contained fix with outsized first-impression value — it is the
first thing a new player sees, and it currently reads as noise. R2 is the real
remaining depth problem: the endgame balance sheet is not a bank's. R3/R4 are
judgement calls for the designer, not defects.
