"""Closing a fraud case must clear the inbox event and the badge."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine
from bankgame.sim import fraud as FR
from bankgame.server import Game


def _spawn_pending_case(state):
    state["bank"]["loans"]["queue"].clear()
    ev = FR._spawn_case(state, engine._rng(state, "fraud"))
    pushed = engine.push_event(state, ev)
    return pushed


class TestFraudCaseClears(unittest.TestCase):
    def test_desk_resolve_drops_pending_event(self):
        state = new_game("Fraud", seed=4)
        ev = _spawn_pending_case(state)
        cid = ev["case_id"]
        self.assertTrue(any(e.get("type") == "fraud_case" and e.get("case_id") == cid
                            for e in state["events"]["pending"]))
        self.assertTrue(engine.inbox_waiting(state))
        res = engine.perform_action(state, "resolve_fraud_case",
                                    {"case_id": cid, "choice": "act"})
        self.assertIn("message", res)
        self.assertFalse(any(e.get("type") == "fraud_case"
                             for e in state["events"]["pending"]))
        self.assertEqual(state["bank"]["fraud"]["cases"][-1]["status"], "closed")
        self.assertFalse(engine.inbox_waiting(state))

    def test_event_choice_still_closes_and_files(self):
        state = new_game("FraudEv", seed=5)
        ev = _spawn_pending_case(state)
        res = engine.perform_action(state, "event_choice",
                                    {"event_id": ev["id"], "choice": "monitor"})
        self.assertIn("message", res)
        self.assertFalse(any(e.get("type") == "fraud_case"
                             for e in state["events"]["pending"]))
        self.assertEqual(state["bank"]["fraud"]["cases"][-1]["status"], "closed")

    def test_stuck_event_heals_on_summary(self):
        state = new_game("Stuck", seed=6)
        ev = _spawn_pending_case(state)
        state["bank"]["fraud"]["cases"][-1]["status"] = "closed"
        # leftover inbox event, the live-save bug
        self.assertTrue(any(e.get("id") == ev["id"]
                            for e in state["events"]["pending"]))
        g = Game()
        g.state = state
        s = g.summary()
        self.assertFalse(any(e.get("type") == "fraud_case"
                             for e in state["events"]["pending"]))
        self.assertEqual(s["counts"]["fraud_cases"], 0)
        self.assertFalse(any(e.get("type") == "fraud_case"
                             for e in s["pending"]))
        self.assertFalse(engine.inbox_waiting(state))

    def test_second_click_does_not_error(self):
        state = new_game("Twice", seed=7)
        ev = _spawn_pending_case(state)
        engine.perform_action(state, "resolve_fraud_case",
                              {"case_id": ev["case_id"], "choice": "act"})
        # Event already pruned; a leftover event + second choice must file, not raise
        state["events"]["pending"].append(dict(ev))
        res = engine.perform_action(state, "event_choice",
                                    {"event_id": ev["id"], "choice": "act"})
        self.assertIn("already closed", res["message"].lower())
        self.assertFalse(any(e.get("id") == ev["id"]
                             for e in state["events"]["pending"]))


if __name__ == "__main__":
    unittest.main()
