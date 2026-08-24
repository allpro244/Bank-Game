"""A4: overnight shortfall is a decision; auto still balances the books."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import funding as FUND


def _drain_cash(state, hole):
    """Force operating cash negative by `hole` cents. Leaves TB = 0."""
    led = state["bank"]["ledger"]
    date = state["time"]["date"]
    liquid = (led["balances"]["1000"] + led["balances"]["1010"]
              + led["balances"]["1100"])
    # consolidate into 1000, then spend past zero
    for acct in ("1010", "1100"):
        bal = led["balances"][acct]
        if bal > 0:
            L.post(led, date, "test: consolidate liquid",
                   [["1000", bal, 0], [acct, 0, bal]], tag="test")
    spend = led["balances"]["1000"] + hole
    L.post(led, date, "test: cash hole",
           [["5170", spend, 0], ["1000", 0, spend]], tag="test")
    self_tb = L.trial_balance(led)
    assert self_tb == 0, self_tb


class TestFundingDecisions(unittest.TestCase):
    def test_ask_does_not_use_window_until_player_chooses(self):
        state = new_game("Ask", seed=5)
        self.assertEqual(state["bank"]["funding"]["overnight_policy"], "ask")
        uses = state["bank"]["funding"]["discount_window_uses"]
        _drain_cash(state, 800_000_00)
        evs = FUND.manage_overnight(state)
        self.assertEqual(state["bank"]["funding"]["discount_window_uses"], uses)
        short = [e for e in evs if e.get("type") == "overnight_shortfall"]
        self.assertTrue(short, "ask policy should raise a shortfall event")
        self.assertTrue(short[0]["blocking"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

        ev = engine.push_event(state, short[0])
        engine.perform_action(state, "event_choice",
                              {"event_id": ev["id"], "choice": "window"})
        self.assertEqual(state["bank"]["funding"]["discount_window_uses"], uses + 1)
        self.assertGreaterEqual(state["bank"]["ledger"]["balances"]["1000"], 0)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_auto_covers_and_keeps_books_balanced(self):
        state = new_game("Auto", seed=6)
        engine.set_policy(state, "funding.overnight_policy", "auto")
        _drain_cash(state, 800_000_00)
        evs = FUND.manage_overnight(state)
        self.assertGreaterEqual(state["bank"]["ledger"]["balances"]["1000"], 0)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        self.assertFalse(any(e.get("type") == "overnight_shortfall" for e in evs))

    def test_wait_leaves_uses_unchanged(self):
        state = new_game("Wait", seed=7)
        uses = state["bank"]["funding"]["discount_window_uses"]
        _drain_cash(state, 400_000_00)
        evs = FUND.manage_overnight(state)
        ev = engine.push_event(state, evs[0])
        engine.perform_action(state, "event_choice",
                              {"event_id": ev["id"], "choice": "wait"})
        self.assertEqual(state["bank"]["funding"]["discount_window_uses"], uses)


if __name__ == "__main__":
    unittest.main()
