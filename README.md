# Bank Game

A deep, turn-based bank management simulation. You start with a $20 million
community bank on a courthouse square in West Texas — one branch, three
employees — and an open sandbox: grow into a money-center giant, stay small
and run the best bank in the state, or blow yourself up trying.

Under the hood there is a real double-entry general ledger (debits equal
credits on every transaction, audited every single day), a simulated macro
economy with an inertial-Taylor-rule Fed and a full moving yield curve,
twelve regional economies, a dozen AI rival banks, credit cycles that build
and burst on their own, CAMELS examinations with written reports, CECL
reserving, FDIC-assisted failed-bank auctions, and bank runs that emerge
from your actual condition — not from an event card.

## How to run it (2 steps, no installs beyond Python)

1. **Install Python 3.10 or newer** (if you don't have it):
   - Windows: get it from https://www.python.org/downloads/ — during install,
     tick the box that says **"Add Python to PATH"**.
   - Mac: `brew install python` or use https://www.python.org/downloads/
   - Linux: you almost certainly already have it (`python3 --version`).

2. **Start the game.** Open a terminal in this folder and type:

   ```
   python3 run.py
   ```

   (On Windows, type `py run.py` instead.)

   Your browser opens to `http://localhost:8321` automatically. That's the
   game. Leave the terminal window open while you play; press Ctrl+C there
   to quit. The game autosaves after every action and every turn.

There is nothing else to install — no pip, no npm, no database server.
The game deliberately uses only Python's standard library, so the setup
cannot break because of a dependency.

## Why this stack (in plain English)

- **Python** runs everywhere, and its built-in SQLite database means your
  saves are a single ordinary file (`saves.db`) with zero setup.
- **Zero third-party packages** was a deliberate choice: every dependency
  is a way for setup to fail on your machine. This project has none.
- **The browser is the screen.** A small local web server shows you a
  dense dashboard UI. Nothing leaves your computer — the server only
  listens on localhost.
- **The engine is a separate module from the UI** (`bankgame/sim/` vs
  `web/`), so the economics can be tested and tuned independently. There
  is an automated test suite for the accounting and interest math.

## Playing the game

- **Advance time** with the +1 Day / Week / Month / Quarter buttons (or
  keyboard: space = day, w = week, m = month, q = quarter). Events that
  need a decision stop the clock and pop a modal.
- **Every number is real.** The Ledger tab shows the chart of accounts and
  the journal; click any account to see the entries behind it. If the
  books ever fail to balance, the game raises an audit alarm (that's a bug
  — the test suite exists to make sure you never see it).
- **Saves tab** (top right): multiple named banks, and rollback to any
  autosave if a decision goes badly. Each save stores its random seed —
  the same seed always produces the same world.

### Your first hour, roughly

1. Look at the **Deposits** tab. Your rates track the market by default;
   the lever is your *offset* in basis points. Pay up to grow, lag to
   fatten margin and slowly bleed.
2. Look at **Lending**. Set spreads and underwriting standards per
   product. Loans above your threshold come to your desk with a credit
   memo. Loose standards book volume today and losses in the next
   recession — vintages remember how they were underwritten.
3. **Treasury**: park excess liquidity in securities. Watch duration —
   long bonds at cycle lows plus a deposit run is exactly how Silicon
   Valley Bank died, and the same mechanics are simulated here (AFS marks
   hit equity daily; selling any HTM taints the whole book).
4. **Operations**: your lone lender caps loan production. Hire before you
   grow. Compliance staff and BSA budget keep the examiners friendly.
5. Watch the **Risk & Reg** tab before every exam. CAMELS 4 means a
   consent order: dividends banned, growth capped.

### The many ways to die

Insolvency (tangible equity ≤ 2% of assets → the FDIC takes the keys), or
illiquidity (a deposit run that exhausts cash, securities, FHLB capacity
and the discount window mid-run). Runs are driven by your real condition:
thin capital, unrealized bond losses vs. equity, uninsured deposit share,
public enforcement actions, nearby bank failures, and a social-media speed
multiplier that grows over the decades.

## Tests

```
python3 -m unittest discover -s tests
```

29 tests cover the ledger invariants (balanced postings, month closes,
integer-cents-only money), interest and bond math, CD repricing,
determinism (same seed → byte-identical world), save/load round-trips,
rollback, and multi-year full-simulation runs asserting the books balance
every single day.

## What was deliberately simplified (and why)

You asked for a flag on anything that would be tedious rather than deep:

- **Customers are cohorts, not individuals.** Deposits and small loans are
  pools per market/product/credit-tier/vintage; only large credits are
  individual named borrowers with memos. Simulating millions of household
  agents would burn the performance budget without changing your decisions
  — the pool model produces the same emergent behavior (deposit beta, hot
  money, vintage losses) and a turn resolves in ~1 millisecond even at
  scale.
- **Fees are grouped into the majors** (maintenance, OD/NSF, ATM, wire,
  interchange, treasury management). Thirty separate fee sliders would be
  busywork; the ones here each have a real tradeoff.
- **Reg CC / chargebacks / Reg E** are modeled as an ongoing operational
  cost line scaled by your volumes and fraud posture rather than as
  per-item decisions — item-level dispute handling is tedium, not depth.
- **Later-stage business lines** (trust & wealth, insurance, merchant
  acquiring, correspondent, capital markets) are P&L engines with
  realistic revenue/cost/volatility profiles you unlock as you grow, not
  full sub-simulations. Each can be deepened later without touching the core.
- **Charter choice** exists as flavor but has minimal mechanical effect —
  in reality the state/national distinction matters far less than capital
  and CAMELS, which are fully modeled.
- **M&A due diligence** is summarized (price to book, credit mark,
  attrition estimate) rather than a document room. Integration risk,
  goodwill, day-1 reserves, and deposit attrition are all real.

Everything else — the yield curve, the Fed reaction function, emergent
credit booms and busts, regional oil/ag/tech exposure, competitor failure
and FDIC auctions, CECL, PCA, exam reports, the $10B/$50B/$100B/$250B
regulatory thresholds, BSA fines, fraud channels, deposit runs — is
mechanically simulated. See `DESIGN.md` for the full model documentation.
