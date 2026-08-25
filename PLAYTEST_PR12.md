# Playtest: PR 12 — realism audit

Head `19126b7`. 188 tests green. This round answers six questions:
is the economy random or simulated, what's missing, is the UI friendly,
what needs balancing, are there bugs, and is the game realistic.

---

## 🔴 BLOCKER: the UI does not load at all

`web/app.js:1519` — `confirmRaiseCommon()` is declared **without `async`** but
uses `await` on line 1523. That is a hard `SyntaxError`, so **the entire
app.js fails to parse and the page renders blank**. No nav, no dashboard,
nothing. Verified in Chromium: `document.body.innerText` is empty, 0 nav
items, and the console shows

```
SyntaxError: await is only valid in async functions and the top level bodies of modules
```

One-word fix (`async function confirmRaiseCommon()`); I confirmed the file
then parses clean and that this is the **only** such error in the file.

**Why nothing caught it:** all 188 tests are Python. Nothing syntax-checks the
JavaScript. A `node --check web/*.js` line in CI (or a smoke test that loads the
page and asserts the nav renders) would have caught this before merge. Strongly
recommend adding it — this class of bug ships a completely dead game while every
test is green.

---

## 1. Is the economy random, or actually simulated?

**Actually simulated, and not close to random.** I ran the macro engine alone
for **1,000 simulated years** (5 seeds × 200 years, no bank attached):

| Test | Result | Pure noise would be |
|---|---|---|
| Output-gap autocorrelation (lag 1) | **0.955** | ~0.00 |
| Fed funds autocorrelation (lag 1) | **0.990** | ~0.00 |
| Inflation autocorrelation (lag 12) | **0.407** | ~0.00 |

And the structural relationships a real economy must have are all present —
none of these are hard-coded, they emerge from the interacting modules:

| Relationship | Model | Reality |
|---|---|---|
| Okun's law (output gap vs unemployment) | **−0.92** | strongly negative |
| Taylor rule (inflation vs fed funds) | **+0.85** | positive |
| Credit stress vs output gap | **−0.43** | negative |
| Curve inverted, % of months | **9.9%** | ~11% (US 1976–2024) |
| **Inversion → recession within 24 months** | **81%** | ~90% |

That last row is the impressive one: an emergent leading indicator, produced by
a two-factor curve and an inertial policy rule that were never told to predict
anything. This is a real macro model, not a random walk with a finance skin.

## 2. Is it realistic? Yes in structure, no in the tails

Same 1,000 years, distribution vs actual US history:

| Series | Model min / median / **max** | US actual |
|---|---|---|
| Inflation | −1.2 / 1.9 / **6.5%** | max **14.6%** (1980) |
| Fed funds | 0.0 / 2.5 / **10.0%** | max **19.1%** (1981) |
| Unemployment | 3.2 / 4.7 / **6.8%** | max **14.8%** (2020), 10.0% (2009) |
| Output gap | **−6.0** / −0.4 / +3.7 | −6% trough in 2008-09 ✔ |

- Months with inflation > 6%: **0.04%** of the sample. US 1965–2024: ~12%.
- Months with fed funds > 10%: **0**. US: ~8%.
- Longest stretch of inflation > 5%: **8 months**. The actual 1970s: ~110 months.
- **Unemployment never once reached 7% in a thousand years.**

`DESIGN.md` claims the inflation process produces "occasional 1970s-style
regimes." It does not — mean reversion is too strong and the shocks too small,
so the distribution is truncated. Meanwhile recessions are *too frequent and too
mild*: one per **2.1 years** covering **30% of all months** (US: one per 6.5
years, 13% of months), averaging 7.5 months (US: ~10).

**The shape is inverted.** Reality is long calm punctuated by catastrophe. This
model is permanent mild chop that never becomes catastrophe.

### The consequence: the crisis systems never fire

Four plainly-run banks × 30 years = 120 bank-years produced **zero days of
deposit run**. The bank-run model, the SVB duration trap, the contagion
mechanics — the most sophisticated and most marketed parts of this simulation —
are effectively dormant, because the macro engine cannot generate a shock big
enough to trigger them. You built a superb crisis engine and then built a world
that never has a crisis.

Bank-side ratios, by contrast, are good:

| Metric | Model median | FDIC actual |
|---|---|---|
| ROA | **1.08%** | 1.0–1.3% ✔ |
| NIM | 4.88% | 3.3–3.8% (high) |
| Efficiency ratio | 72% | 55–65% (high) |

## 3. Balance changes needed

1. **Fatten the macro tails.** Raise the supply-shock magnitude and weaken
   inflation's mean reversion so a multi-year high-inflation regime is possible;
   let unemployment reach 10%+ in a severe bust. Without this, nothing else in
   the crisis stack matters.
2. **Make recessions rarer and deeper.** Fewer, longer, meaner — target ~13% of
   months in recession instead of 30%, with a real tail.
3. **NIM and efficiency both run ~1pp and ~8pp rich.** Small, but they compound
   into the "too easy to be profitable" feel in calm decades.
4. **The crown keeps receding.** PR 7–9: year 86. PR 10: year 119. PR 12: past
   year 140 and still climbing at the 170-year mark. Each realism pass has
   slowed compounding. That is defensible individually, but the flagship goal is
   drifting out of reach of any human session. Pick a target length and tune to
   it deliberately.

## 4. What I wish it had

- **A crisis that actually arrives.** See above — this is the single biggest
  gap between what the game promises and what it delivers.
- **Faces.** Rivals are still stat blocks; borrowers now have memory (good) but
  no rival CEO ever taunts you, poaches your lender, or gets bought by you.
- **A newspaper.** The month digest is good; a rendered front page would turn
  numbers into story and give the late game a pulse.
- **Delegation.** Still no way to hand routine credit or pricing to officers,
  so a $100B bank is managed with the same clicks as a $20M one.

## 5. What I wish it didn't have

- **Exam spam.** Still the dominant line in any long log.
- **Fee lines that don't move the P&L** (10–14% of revenue with trust at ~$0).
- **396+ branch counts** as the winning strategy — "branch spam" is the optimum
  and it reads as a spreadsheet exercise rather than a strategic choice.

## 6. UI friendliness

I could not evaluate the live UI this round because of the blocker above. From
the code and prior rounds, the standing recommendations are unchanged:

1. **Fix the blocker, then add `node --check` to CI.**
2. **Autoplay / "play until something needs me"** remains the top usability
   item — measured at ~1,560 clicks per game-decade in an earlier round.
3. **Progressive disclosure on the dense tabs.** Lending shows every product ×
   4 controls at once; a new owner does not need construction limits in year 1.
4. **A "what changed since last quarter" strip** at the top of the Desk — three
   lines of delta beats six gauges the player must diff by eye.

---

## Bugs found this round

| # | Severity | Finding |
|---|---|---|
| 1 | 🔴 | `web/app.js:1519` non-async `await` → **entire UI blank** |
| 2 | 🟡 | No JS syntax check anywhere in the test suite (root cause of #1) |

Engine-side: **clean.** A 25-year invariant sweep (trial balance, pool↔GL ties
for loans and deposits, negative-balance checks, NaN/inf scan on all metrics)
plus fuzzing every action and policy path — including the new PR 12 surfaces
(`sell_loans`, `set_market_offset`, weight-class market unlocks) — produced
**zero findings**. The simulation core is in good shape.
