"""B4: week/month/quarter stop on loan memos; skip_inbox can override."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine


class TestAdvanceInbox(unittest.TestCase):
    def test_quarter_stops_on_seeded_credit(self):
        state = new_game("Inbox", seed=2)
        self.assertTrue(state["bank"]["loans"]["queue"])
        left = state["bank"]["loans"]["queue"][0]["days_left"]
        res = engine.advance(state, "quarter")
        self.assertEqual(res["days"], 0)
        self.assertTrue(res["inbox"])
        self.assertEqual(state["bank"]["loans"]["queue"][0]["days_left"], left)
        self.assertEqual(state["time"]["date"], "2000-01-03")

    def test_week_stops_on_queue(self):
        state = new_game("Wk", seed=2)
        res = engine.advance(state, "week")
        self.assertEqual(res["days"], 0)
        self.assertTrue(res["inbox"])

    def test_day_still_runs_with_inbox(self):
        state = new_game("Day", seed=2)
        res = engine.advance(state, "day")
        self.assertEqual(res["days"], 1)
        self.assertFalse(res.get("inbox"))

    def test_skip_inbox_can_expire_memos(self):
        state = new_game("Skip", seed=2)
        self.assertTrue(state["bank"]["loans"]["queue"])
        res = engine.advance(state, "quarter", skip_inbox=True)
        self.assertGreater(res["days"], 0)


if __name__ == "__main__":
    unittest.main()
