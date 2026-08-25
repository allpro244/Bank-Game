# Playtest after PR #10 (I8 + leftover findings)

Headless world-crown owner, same harness as the pre-#10 session.
Credit box $2M hold, overnight auto, follow advisor, bid FDIC when
pro-forma allows, buy private deals under 55% of equity on a CAMELS
1–2. Seeds 11, 7, 3, 19. Ninety years or seizure. Head `08a9ff6`
(PR #10 merged into the playable branch).

The $250B crown does not move in this note.

## Versus the pre-#10 run (same harness)

| Seed | Before #10 | After #10 |
| --- | --- | --- |
| 11 | Seized y34 at $17.2B, #2 of 10, TE 1.25%. Last weeks jumped $6.6B → $17.2B. | Standing y90 at **$96.2B**, #1 of 9. Knickerbocker $33.9B. LDR 0.85. CAMELS 2 (M=3). Window 0. Books tied. |
| 7 | Standing y80 at $11.6B, #2 of 9, LDR ~0.29. | Standing y90 at **$32.0B**, #2 of 9. Knickerbocker $45.9B. LDR 0.93. CAMELS 2. Window 0. |

Seeds 3 and 19 (not run last time): both standing y90, both #1 of 9, $22.2B and $37.4B. Eight living rivals on every seed. No trial-balance breaks. No engine exceptions. Whale FDIC still refused (3 wins on seed 11, all ≤0.5× us).

Nobody hit $250B in 90 years. Best book is $96B / rank 1. Claude’s earlier $253B / y86 used a different owner.

## What #10 actually fixed

- **No catchment seizure.** Seed 11’s old last-month jump is gone. Dallas/Houston opens stay trade-area (year-1 gather $23–80M).
- **LDR can keep up.** Seed 7 went from 0.29 to 0.93. Seed 11 holds 0.85–1.02 for decades.
- **CAMELS loop is broken.** End states are composite 2, M=3, no orders. A 4 still appears (seed 11 y10, seed 7 y5) and recovers in a few exams. No 65-year flatline at 3.
- **Play until advances through a 4 and through a run.** First 25 years of seed 11: 141 presses, zero zero-day, stops are quarter-close / exam / the occasional deal. No day-by-day walk on the leftover rating or run flag.
- **Raise cards did not spam.** 7–12 raises over 90 years, not 20 in one sitting.
- **Window stays at 0** on auto.

## Findings from this session

1. **M&A plants a window farm.** Private deals and FDIC absorbs used to drop `sqrt(assets_m)/3` offices into *one* market. Seed 11 ended with **409 open offices** (201 Austin). Extra windows overlap the same catchment, so they do not buy the crown — they buy rent. Engine fix on this branch: cap inherited offices at 3 per market per deal. The books still transfer.
2. **Play until gets noisy late if the credit box stays at $2M.** Seed 11 used 11,535 presses over 90 years; seed 7 used 526. First 25 years of seed 11 look like seed 7. After the book is several billion, leftover memos the $2M box cannot participate stop the clock. That is the player-written box working as designed — raise the hold as you grow. Not an engine interrupt regression.
3. **Year-one sit-still is still thin** (ROA 0.00–0.32% in y1, then 1.0–1.6% in y2). Left alone so the 3-year 0.6–1.6% band does not move.
4. **The crown is not a 90-year sit.** $96B / y90 on the best seed, field still alive. Organic + sized M&A grows; it does not print $250B. That is the I2+I3 measurement the plan asked for — not a reason to move the number from one harness.

## Not bugs

Books tied. No crashes. Industry does not go extinct. First exam is not a 4. Advisor hire-lender stays off when the preview is red.
