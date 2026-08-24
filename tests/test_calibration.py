"""G1–G3: profitability bands, honest early ROA, liquidity exam."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine
from bankgame.sim import statements
from bankgame.sim import ledger as L
from bankgame.sim import loans as LN
from bankgame.sim.regulation import run_exam, pca_category, capital_ratios


def _passive(state, days):
    state["bank"]["loans"]["queue"].clear()
    state["bank"]["funding"]["overnight_policy"] = "auto"
    for _ in range(days):
        engine.step_day(state)
        state["events"]["pending"].clear()
        state["bank"]["loans"]["queue"].clear()


class TestCalibration(unittest.TestCase):
    def test_first_month_marks_partial_window(self):
        state = new_game("Cal", seed=12)
        state["bank"]["loans"]["queue"].clear()
        _passive(state, 32)
        self.assertTrue(state["metrics"], "expected a month-end metric row")
        m = state["metrics"][-1]
        self.assertTrue(m.get("partial_window"))
        self.assertLess(m.get("window_months", 0), 6)
        self.assertFalse(m.get("earnings_ready"))
        self.assertIsNone(m.get("roa"))

    def test_day1_has_no_metrics_row(self):
        state = new_game("Cal0", seed=12)
        self.assertEqual(state["metrics"], [])
        m = statements.compute_metrics(state)
        self.assertTrue(m.get("partial_window"))
        self.assertFalse(m.get("earnings_ready"))
        self.assertIsNone(m.get("roa"))

    def test_opening_ldr_is_not_already_tight(self):
        state = new_game("Book", seed=1)
        loans = LN.total_loans(state["bank"]["loans"])
        deps = L.total_deposits(state["bank"]["ledger"])
        ldr = loans / max(1, deps)
        self.assertLess(ldr, 0.80)
        self.assertGreater(ldr, 0.65)
        cash = (state["bank"]["ledger"]["balances"]["1000"]
                + state["bank"]["ledger"]["balances"]["1010"]
                + state["bank"]["ledger"]["balances"]["1100"])
        # One rural branch is $1.8M; cash+fed should cover it.
        self.assertGreaterEqual(cash, 1_800_000_00)

    def test_passive_three_years_roa_in_community_band(self):
        roas, effs, ls = [], [], []
        for seed in (7, 19, 41, 88):
            state = new_game("P%d" % seed, seed=seed)
            _passive(state, 756)
            self.assertIsNone(state["game_over"])
            self.assertEqual(pca_category(capital_ratios(state)), "well")
            m = state["metrics"][-1]
            self.assertTrue(m.get("earnings_ready"))
            roas.append(m["roa"])
            effs.append(m["efficiency"])
            evs = run_exam(state, engine._rng(state, "misc"))
            cam = state["regulation"]["camels"]
            ls.append(cam["L"])
            window = state["bank"]["funding"].get("discount_window_uses", 0)
            ldr = m.get("loan_to_deposit", 0)
            if window == 0 and ldr <= 1.05:
                self.assertLessEqual(cam["L"], 2,
                                     "L=%s with window=0 ldr=%.2f seed=%s"
                                     % (cam["L"], ldr, seed))
            self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
            _ = evs
        mid = sorted(roas)[len(roas) // 2]
        self.assertGreaterEqual(mid, 0.006, "median ROA %.2f%% too thin" % (mid * 100))
        self.assertLessEqual(mid, 0.016, "median ROA %.2f%% still a printer" % (mid * 100))
        for e in effs:
            self.assertGreater(e, 0.45)
            self.assertLess(e, 0.85)


if __name__ == "__main__":
    unittest.main()
