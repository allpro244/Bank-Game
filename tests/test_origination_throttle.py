"""A5: idle origination cannot silently outrun deposits."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import loans as LN


def _run(state, days):
    for _ in range(days):
        engine.step_day(state)
        state["events"]["pending"].clear()


class TestOriginationThrottle(unittest.TestCase):
    def test_passive_three_years_ldr_stays_sane(self):
        for seed in (3, 11, 29):
            state = new_game("P%d" % seed, seed=seed)
            state["bank"]["loans"]["queue"].clear()
            _run(state, 756)   # ~3 years
            loans = LN.total_loans(state["bank"]["loans"])
            deps = L.total_deposits(state["bank"]["ledger"])
            ldr = loans / max(1, deps)
            self.assertLess(ldr, 1.15, "seed %s LDR %.3f" % (seed, ldr))
            self.assertIsNone(state["game_over"])
            self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
            # ask policy + no player: window is not a silent habit
            self.assertLessEqual(
                state["bank"]["funding"]["discount_window_uses"], 3,
                "seed %s window uses" % seed)

    def test_large_app_flags_unfunded_hold(self):
        state = new_game("Fund", seed=8)
        # drain liquid so a typical large memo cannot fund
        led = state["bank"]["ledger"]
        leave = 50_000_00
        for acct in ("1010", "1100"):
            bal = led["balances"][acct]
            if bal:
                L.post(led, state["time"]["date"], "test consolidate",
                       [["1000", bal, 0], [acct, 0, bal]], tag="test")
        extra = led["balances"]["1000"] - leave
        if extra > 0:
            L.post(led, state["time"]["date"], "test drain",
                   [["5170", extra, 0], ["1000", 0, extra]], tag="test")
        app = LN._make_application(state, engine._rng(state, "credit"),
                                   "caprock", 500_000_00)
        self.assertIsNotNone(app)
        self.assertIn("If we decline", app["memo"])
        self.assertIn("Why them", app["memo"])
        if app["amount"] > 50_000_00:
            self.assertFalse(app["can_fund"])
            self.assertIn("FUNDING", app["memo"])


if __name__ == "__main__":
    unittest.main()
