# Playtest feedback — for Cursor

Post-PR-12 playtest. Every number below is reproducible from this commit; the
scripts that produced them are inline so you can re-run them after a fix.

**Bottom line:** the engine is *correct* and the macro model is *real*. The
problem is that its tails are clipped so tightly that the crisis systems you
already built can never actually fire. There are no accounting bugs left to
find. The work is calibration, not repair.

---

## 0. Already fixed and pushed — don't redo it

`web/app.js` had `function confirmRaiseCommon()` using `await`. That is a
SyntaxError, so the browser refused to parse the *entire file*: no globals, no
nav, no dashboard, blank white page. Fixed on
`claude/bank-management-sim-1il18e` (commit `66996aa`) by adding `async`.

Also added `tests/test_web_assets.py` — `node --check` on every file in `web/`,
plus a dependency-free scanner for the same bug so it still fires on a machine
with no node. Suite is 193 tests, green.

**Worth knowing:** 188 tests passed while 100% of the UI was down, because every
test was Python and nothing ever parsed the browser JS. If you add front-end
files, that guard is the thing keeping this from happening again.

---

## 1. The macro model is genuinely a model (keep it)

I checked whether the economy is noise dressed as economics. It isn't. 500
simulated years, `seed_stream(20260825, "economy")`:

| Property | Value | Verdict |
|---|---|---|
| Lag-1 autocorrelation, unemployment | 0.972 | persistent, not noise |
| Lag-1 autocorrelation, fed funds | 0.991 | rates move in campaigns |
| Okun's law (ΔU vs GDP growth) | −0.55 | correct sign and strength |
| Taylor rule (fed funds vs inflation) | +0.85 | the Fed genuinely reacts |
| Inverted curve → recession in 6–18m | 78% of 405 inverted months | real leading indicator |

Nothing here needs changing. This is better than most commercial sims.

---

## 2. **The headline problem: the tails are clipped**

Same 1,000-year run (12,000 months):

```
unemployment    max 6.53%   p99 5.92%   mean 4.68%
  months above 7%:  0     ← zero, in a thousand years
  months above 8%:  0
inflation       max 5.39%
  longest run above 5%:  2 months
  months above 5%:  8 of 12,000  (0.07%)
recession months: 2,155 (18.0%)
```

Real US, 1948–2024: unemployment peaked at 10.8% (1982) and 14.8% (2020) and sat
above 7% roughly 17% of all months. Inflation stayed above 5% for **110
consecutive months** through the 1970s.

So: **recessions are frequent but toothless.** 18% of months are technically
recessions — slightly *more* than reality's ~13% — yet not one of them ever
produces a labour market or an inflation print a real banker would recognise as
a crisis. The player never faces a 1982, a 1974, or a 2008. They face the same
mild wobble a hundred times.

Three specific throttles, in the order I'd fix them:

**a) Credit stress barely touches output.** `economy.py:122`
```python
stress_drag = -1.5 * e["credit_stress"] * 0.20    # = -0.30 * credit_stress
```
Even at maximum stress (1.0) this is a −0.30 drag on the output gap. The whole
credit-bust machinery above it — boom accumulation, bust severity, 8–20 month
duration — feeds into a coefficient too small to bite. Try `-0.9` to `-1.2`
and let severity scale it. This one number is most of the problem.

**b) Unemployment is symmetric; real unemployment isn't.** `economy.py:133`
```python
target_u = e["natural_unemployment"] - 0.45 * e["output_gap"]
e["unemployment"] += 0.30 * (target_u - e["unemployment"]) + noise
```
Unemployment rises like an elevator and falls like a feather — that asymmetry
*is* the business cycle's felt shape. Suggest a faster adjustment when the gap
is negative (≈0.45) than when positive (≈0.15), and a steeper Okun coefficient
(0.45 → ~0.6) so deep gaps translate into real joblessness.

**c) Inflation expectations can't unanchor.** `economy.py:141`
```python
anchor = 2.0 + 0.45 * (e["core_inflation"] - 2.0)
```
That 0.45 is fixed, which pins the long-run attractor at exactly 2.0% forever.
The 1970s happened *because* that coefficient drifted toward 1.0 — people stopped
believing the anchor. Make it a state variable that rises with sustained
above-target inflation and falls slowly once the Fed re-establishes credibility.
Related: the supply shock at `economy.py:143` is a single-month impulse fired
once per ~10 years. Real oil shocks persist for years. Give it a decaying state
(e.g. 6–30 months at declining magnitude) rather than one spike.

---

## 3. **The deposit-run system is mathematically unreachable**

This is the finding I'd act on first, because you've already built the whole
thing — outflow waterfalls, social-media speed scaling by decade, contagion from
nearby failures, the liquidity-exhaustion failure path — and none of it can run.

**Evidence 1.** 20 years of ordinary play, per-day instrumentation:
```
deposit-run days : 0
peak rumor level : 0.100   (a run needs 0.45)
```
Rumor never even doubled off its first spark in two decades.

**Evidence 2** — the decisive one. I pinned `condition_weakness()` to fixed
values and measured time-to-ignition:

| weakness pinned at | run ignites after |
|---|---|
| 0.4 (troubled bank) | **never**, in 10 years |
| 0.6 (very sick) | 203 business days (9.7 months) |
| 0.8 (dying) | 143 business days (6.8 months) |
| 1.0 (maximum possible) | 91 business days (4.3 months) |

A bank at weakness 1.0 must *simultaneously* have tangible equity under ~3%,
large unrealized securities losses, 4%+ NPAs, negative earnings, CAMELS 4+, and
a consent order. That bank hits `pca_category() == "critical"` and gets seized by
`regulation.py:141` in **weeks**. It is never alive for the four months the run
mechanic needs. The run can't fire because the regulator always wins the race.

For scale: Silicon Valley Bank went from "fine" to failed in about 36 hours.

**Root cause.** `crises.py:122`
```python
drift = (weak * 0.6 + ambient - 0.30) * 0.08
cr["rumor"] += drift * cr["rumor"]
```
Growth is multiplicative on `rumor`, and `rumor` starts near 0.05, so the early
days grow by ~0.0002/day. It's exponential growth from a seed too small, through
a coefficient too small, toward a threshold too far away. Compounding it,
`crises.py:118` fires a spark only every 60–200 days.

**Suggested shape** (not literal code — your call on the numbers):
- Add a linear term so rumor can build from near-zero:
  `rumor += drift * (0.15 + rumor)`.
- Raise the `0.08` scale to ~0.35 so a genuinely weak bank ignites in days.
- Lower the `0.45` trigger to ~0.30, or let `social_media_factor` lower it by
  era — a 2030s run should trip on less rumor than a 1990s one, which is
  presumably what that function was for.
- Make `ambient` matter: at `crises.py:120` it's multiplied by 0.02, which
  reduces contagion from nearby failures to nothing. Rival failures should be
  frightening.

Target: a bank at weakness 0.6 should face a run in **3–10 days**, not 10
months. That single change turns liquidity management from decoration into the
tensest part of the game.

---

## 4. Engine correctness: clean

20 years / 5,040 business days with per-day invariant checks:

```
ledger problems  : NONE — trial balance held every single day
integer cents    : held
turn time        : ~1ms  (1,890 days/sec)
```

No accounting bugs. Trial balance, pool↔GL ties, no negative balances, no
NaN/inf. Performance is ~2,000× the 2-second budget. Nothing to do here.

---

## 5. Smaller UI item

An open `#eventmodal` covers the nav bar and swallows clicks, so a player who
wants to check Treasury or Loans *before* answering an event can't. Blocking the
**advance-day** button is right; blocking read-only navigation isn't. Suggest
letting the modal sit behind nav clicks, or adding a "look around first" affordance
that re-opens it.

---

## Priority

1. **Deposit-run ignition** (`crises.py:118–129`) — unlocks a system that already exists.
2. **Credit-stress drag** (`economy.py:122`) — one coefficient, most of the missing severity.
3. **Unemployment asymmetry** (`economy.py:133`) — makes downturns feel like downturns.
4. **Inflation unanchoring + persistent supply shocks** (`economy.py:141–144`) — makes a 1970s possible.
5. **Event modal vs nav** — small, but every player hits it.

Items 1–4 are all calibration inside functions you've already written. There is
no new subsystem to build.
