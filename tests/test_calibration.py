"""G2: trailing metrics stay honest until a real window exists.

Full G1 profitability bands wait until Phase G. This file exists so the
first closed month cannot claim a printer-ROA from ×12 annualization
without a flag.
"""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine
from bankgame.sim import statements


def _run(state, days):
    for _ in range(days):
        engine.step_day(state)
        state["events"]["pending"].clear()


class TestCalibration(unittest.TestCase):
    def test_first_month_marks_partial_window(self):
        state = new_game("Cal", seed=12)
        state["bank"]["loans"]["queue"].clear()
        _run(state, 32)
        self.assertTrue(state["metrics"], "expected a month-end metric row")
        m = state["metrics"][-1]
        self.assertTrue(m.get("partial_window"))
        self.assertLess(m.get("window_months", 0), 6)

    def test_day1_has_no_metrics_row(self):
        state = new_game("Cal0", seed=12)
        self.assertEqual(state["metrics"], [])
        # compute_metrics on an empty history is still flagged noisy
        m = statements.compute_metrics(state)
        self.assertTrue(m.get("partial_window"))


if __name__ == "__main__":
    unittest.main()
