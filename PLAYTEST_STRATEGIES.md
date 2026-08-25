# Playtest: do the six promised strategy paths actually work?

The original brief promised "many genuinely different paths": a deposit-gathering
retail machine, a commercial real estate lender, a bank that lives off securities
and rate spread, an acquirer that rolls up failed banks, a digital-first
challenger, a trust and wealth shop, an investment bank.

I played each one as a distinct archetype — different pricing, credit appetite,
expansion, and capital policy — on identical seeds, with the same survival
hygiene underneath so the comparison is about strategy, not carelessness.
Run on head `5c16dda` (after Cursor's PR 4–6 fixes). Reports only; no engine
changes.

## Results — 6 archetypes × 2 seeds × 30 years

| Archetype | seed 2024 | seed 7 | Loans % of assets | Securities % | Fee % of revenue |
|---|---|---|---|---|---|
| Retail machine | $170M, ROA 0.90% | $1.3B, ROA 0.16% | 33–54 | 40–60 | 10–12 |
| CRE lender | $74M, **ROA −1.06%**, CAMELS 4 | $144M, ROA 1.56% | **96–99** | **0** | 2–7 |
| Securities / spread | $101M, ROA 1.26% | $189M, ROA 1.64% | 53–58 | 38–42 | 8 |
| Acquirer (roll-up) | **SEIZED year 20** | $194M, ROA 1.36% | 74–83 | 0–30 | 10–25 |
| Digital challenger | **SEIZED year 1.0** | **SEIZED year 1.8** | — | — | — |
| Fee / wealth shop | $143M, ROA 0.86% | $836M then **SEIZED year 26.5** | 71–74 | 3–5 | 11–14 |

**4 of 12 runs ended in seizure. The digital challenger died in both.**

---

## S1. The digital-first challenger is mathematically impossible

| Upgrade | Cost | Bank's entire equity |
|---|---|---|
| digital level 0 → 1 | **$1.50M** | $2.54M |

Level 1 costs **59% of all the equity you own** and buys a **+35% presence**
bump in one market. Reaching level 5 costs **$48.2M** — 2.4× the entire
starting bank's assets. Both seeds died inside two years buying it.

A digital-first bank is a real archetype (it is even one of the AI rivals'
strategies, "Meridian Digital Bank"), but the player cannot choose it. Either
the early levels need to be affordable at community-bank scale, or digital
needs a cheap "online-only, no branches" entry tier that trades branch capex
for platform spend.

## S2. Trust/wealth and investment banking are locked behind 35–80 years

Unlock thresholds vs. the growth curve measured in `PLAYTEST_TYCOON.md`:

| Line | Requires | Reached around |
|---|---|---|
| Treasury management | $50M | year ~15 |
| Trust & wealth | **$150M** | **year ~35** |
| Merchant acquiring | $250M | year ~40 |
| Correspondent | $1B | **year ~59** |
| Capital markets / IB | **$10B** | **year ~82** |

In a 26-year idle run the bank never crossed a single threshold — "enabled
lines: []". The promised "trust and wealth shop" and "investment bank" paths
are not strategies you can *choose*; they are rewards for having already won
by other means, decades in.

## S3. You cannot actually run a securities bank

I priced loans **150bp above market** with the **tightest** standards (4) —
the maximum deterrence the game allows — and loans still finished at **53–58%
of assets**, *more* than the "retail machine" run on the same seed (33–38%).
Origination volume bottoms out around 25% of baseline; there is no way to shut
the loan window and live off the curve. The archetype's balance sheet never
takes its intended shape.

## S4. Fee businesses barely register

Even with lines unlocked, fee income is **10–14% of revenue** — and most of
that is base interchange and deposit service charges that every bank gets for
free. Trust & wealth contributed **$0**. A real trust-and-wealth franchise runs
40–60% fee revenue; here the fee lines are rounding errors on the P&L, so the
"fee shop" is mechanically indistinguishable from a generic bank that happens
to have paid some setup costs.

## S5. Luck beats strategy

Same archetype (retail machine), same policies, 25 years, six seeds:

| Seed | Deals offered & taken | Branches | Final assets |
|---|---|---|---|
| 555 | **0** | 1 | **$81.5M** |
| 31337 | 1 | 2 | $103.4M |
| 2024 | 5 | 6 | $150.4M |
| 7 | 4 | 5 | $165.4M |
| 99 | 5 | 7 | $181.6M |
| 1234 | 4 | 6 | **$193.1M** |

Outcome tracks **deal flow**, which is a 5%/month dice roll, almost perfectly:
zero deals halves your bank. The spread from luck within one strategy (2.4×,
and 7.6× at 30 years) is **larger than the spread between strategies on one
seed** (~2.3×). A player switching strategies will feel less difference than a
player who reloads the same strategy on a new seed — which undercuts the whole
premise of meaningful strategic choice.

## S6. What did work

**The CRE lender is the one genuinely distinct archetype** — it produced a
genuinely different bank (96–99% loans, 0% securities, CRE concentration) with a
genuinely different risk profile: one seed compounded at 1.56% ROA, the other
went to CAMELS 4 and −1.06% ROA on the same policies. Concentration risk
behaving differently across cycles is exactly the intended design working.

The **retail machine** and **acquirer** are also viable and feel distinct in
play (deposit pricing and branch cadence vs. dry powder and bidding).

---

## Recommendations, ranked

1. **Make digital affordable at the bottom.** Scale early upgrade costs to bank
   size, or add a branchless digital charter option at game start.
2. **Lower the fee-line thresholds and raise their P&L weight** so trust,
   wealth, and capital markets are choices a mid-size bank makes, not trophies.
   Trust at $150M → ~$40M; give the lines enough revenue to reshape the P&L.
3. **Let a player genuinely stop lending** — a "no new originations" switch, or
   let extreme pricing actually drive volume to zero — so the securities/spread
   bank can exist.
4. **Damp the luck.** Make M&A opportunity frequency respond to the player's
   posture (a declared acquirer should see more deals) rather than a flat dice
   roll, so strategy — not the seed — drives the outcome spread.
5. **Warn on strategy-fatal spends.** "This upgrade costs 59% of your equity"
   belongs on the button, next to the consequence previews that already exist
   for pricing.
