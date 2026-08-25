# Design notes — how the simulation works

This is the reference for what is modeled, where it lives, and how the
pieces talk to each other. The audience is a future maintainer (human or
AI) tuning the game.

## Architecture

```
run.py                  entry point (starts server, opens browser)
bankgame/
  server.py             stdlib HTTP server: JSON API + static files
  store.py              SQLite persistence: saves, autosave snapshots, rollback
  sim/                  THE ENGINE — no UI knowledge, fully testable headless
    rng.py              xoroshiro128** with named per-subsystem streams,
                        integer state stored in the save (determinism)
    ledger.py           double-entry GL, chart of accounts, month closes, audit
    economy.py          macro: cycle, Fed, curve, commodities, housing, equities
    regions.py          12 markets with industry mixes and local shocks
    competitors.py      AI rival banks, market rates, failures
    deposits.py         deposit pools, flows, fees, CD repricing
    loans.py            origination, pools/vintages, delinquency, CECL, OREO,
                        large-loan queue with credit memos
    securities.py       AFS/HTM portfolio, pricing off the curve, hedges
    funding.py          FHLB/brokered/subdebt/overnight + capital actions
    operations.py       branches, staff, marketing/brand, technology
    regulation.py       capital/RWA, PCA, CAMELS exams, FDIC, thresholds, BSA, CRA
    fraud.py            channel losses, detection, cases
    crises.py           bank-run model, cyberattacks
    statements.py       financial statements & metrics from the ledger
    newgame.py          initial state
    engine.py           daily turn loop, month/quarter processing, actions,
                        policy whitelist, M&A
web/                    the browser UI (vanilla JS, canvas charts)
tests/                  unittest suite (ledger, interest, determinism, sim)
```

The entire game state is one JSON-serializable dict. Money is always
integer cents. RNG streams are named (`econ`, `credit`, `fraud`, ...) so
adding a random draw in one subsystem never perturbs another — this keeps
seeds stable across small code changes.

## The turn loop (engine.py)

One turn = one business day (weekends are skipped; interest accrues for
elapsed calendar days, so Monday accrues three days).

Daily: curve wiggle → deposit/loan/securities/borrowing accruals → AFS
mark-to-market through AOCI → bank-run model → overnight cash management
(sweep excess to fed funds sold; cover shortfalls via FFP then discount
window) → ledger audit (Σ balances must be exactly 0).

First business day of a month, before the daily phase: macro month step,
regions, competitors, deposit flows, interest collection, credit rolls
(delinquency/charge-offs/recoveries/OREO), originations, securities aging,
funding maturities, opex, fraud, business lines, exam countdown — then the
month's books close into an archive used by all reporting.

Quarter ends add: CECL re-measurement, estimated taxes (21%, with loss
carryforwards), FDIC assessment, capital ratios → PCA category, threshold
crossings, call report, dividends.

## Economic model

- **Output gap**: AR(2) with monetary-policy drag (lagged real rate vs
  r*), credit-stress drag, and N(0,0.33) monthly shocks.
- **Credit cycle**: a `credit_boom` stock builds when policy is easy and
  the gap is positive; above 0.6 the monthly bust probability rises
  quadratically. A bust runs 8–20 months of `credit_stress`, which feeds
  PDs, spreads, equity drawdowns, and rivals' health. Cycles are emergent,
  not scheduled.
- **Inflation**: partially-anchored expectations (anchor drifts 45% with
  realized core), Phillips term, oil passthrough, rare supply shocks
  (+0.5 to +2.8pp) — this is what produces occasional 1970s-style regimes.
- **Fed**: inertial Taylor rule (ρ=0.8, 25bp steps, ±75bp/month cap),
  crisis-cutting discretion, occasional discretionary surprises.
- **Yield curve**: short rate (fed funds) + long anchor (expected policy +
  mean-reverting term premium) blended by exp(-t/2.8), plus a curvature
  hump. Inversions emerge naturally late in hiking cycles.
- **Commodities**: OU processes in logs with regime jumps (oil, gas,
  cattle, cotton). Regional economies weight them by industry mix — the
  Permian markets crack when crude craters.

## Emergent deposit beta

The player prices deposits as an offset (bp) to prevailing market rates.
Each market/product pool moves toward a target share driven by: rate edge
(exp-sensitivity per product), branch presence^0.72 + digital reach, brand,
fees, service quality, and money-fund competition. Product "heat" (money
market and short CDs fastest, checking slowest) makes funding costs lag on
the way up exactly like real deposit betas. CDs are booked at a weighted
average rate; a 1/term slice matures monthly and reprices or leaves.

## Credit

Pools keyed by (product, market, tier, vintage-year) with a stored vintage
quality from the underwriting standards in force at origination. Monthly
roll rates current→30→60→90→NPL→resolution, scaled by product base PD,
tier, quality, seasoning, and a macro multiplier (unemployment gap,
regional activity, oil/housing/cap-rate/drought channels). Charge-offs use
product LGDs; secured products route 60% of recoveries through OREO.
CECL: quarterly lifetime-loss re-measure (with a macro-forecast overlay)
plus specific reserves on delinquent buckets; provisions post the delta.

## The run model (crises.py)

A daily rumor level evolves from measured weakness (tangible equity,
unrealized bond losses vs equity, NPAs, losses, CAMELS/orders), ambient
stress and recent bank failures, amplified by a social-media factor that
grows with the calendar year and the bank's size. Above 0.45 the run is
on: daily outflows = f(rumor, uninsured share, social factor, rate
defense), pulled from hot products first, executed against the ledger. If
one day's demand exceeds every liquidity source (cash, AFS+HTM at market,
FHLB capacity, discount-window collateral), the bank fails mid-run.

## Calibration notes / known softness

- A passively-run bank in a benign expansion earns ROA ~1.5–2.5% and
  piles up capital; its ROE is poor and the equity sits idle. The
  intended pressure is cyclical: loose vintages + a bust, or rate risk,
  is what kills. If benign-era profitability feels too easy, the knobs
  are `operations.monthly_opex` (other-expense factor), `BASE_PD`, and
  competitor loan-stance tilts.
- Deposit pools grow with population/income/activity only; a player who
  never expands stays a ~$25–50M bank forever. Growth comes from
  branches, digital, marketing, rate, and M&A. This is intended.
- Competitor banks are strategic archetypes with health dynamics, not
  full balance-sheet simulations. They price, grow, sicken, fail, and
  appear in peer reports; they do not hold your paper.
- HTM transfer-at-taint uses fair value as the new basis (a mild
  simplification of ASC 320's amortization mechanics); AOCI self-corrects
  to zero at maturity.
- Taxes are cash-settled quarterly estimates at 21% with loss
  carryforwards; no deferred tax assets.

## Performance

State is aggregate (pools/cohorts), so a turn is ~1ms and 30 game-years
run in ~3 seconds. Save files are ~2MB JSON gzipped to a few hundred KB.
Entry log is capped (6,000 most recent journal entries) with monthly P&L
archives kept forever (capped at 100 years) for statements.

## Ideas for the next depth pass

These are queued as **Phase H** in `ROADMAP.md` and wait until the
unfair-death and first-session work (Phases A–E) is shipped. Do not
start them to avoid finishing A.

- Per-market deposit pricing (offsets by market, promo money). **Shipped.**
- Loan sales/participations and a securitization shelf. **Seasoned sale shipped** (performing strip or named credit → living rival, preview required). No purchase tape. Shelf still parked.
- Competitor M&A against the player's targets; hostile offers. **Shipped** (hold / pass / 3-month steal).
- Examiner remediation tracks (MRAs with deadlines). **Shipped.**
- Duration-matched EVE dashboard with +/-100/200/300bp shocks. **Shipped.**
- Named key employees (a CFO, a chief credit officer) with traits.
- Holding-company structure with double leverage.
