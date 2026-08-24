"""The advisor layer: gauges, cards, tutorial, and their action plumbing.
The advisor must never crash, and every action it recommends must be a
legal move the player could make by hand."""

import json
import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, advisor, ledger as L


class TestAdvisor(unittest.TestCase):
    def _run(self, state, days):
        for _ in range(days):
            engine.step_day(state)
            state["events"]["pending"].clear()

    def test_day1_gauges_have_no_invented_roa(self):
        state = new_game("Day1", seed=1)
        g = advisor.gauges(state)
        earn = next(x for x in g if x["key"] == "earnings")
        self.assertEqual(earn["status"], "y")
        blob = (earn["head"] + " " + earn["detail"]).lower()
        self.assertTrue("opened" in blob or "scorecard" in blob)
        self.assertNotRegex(earn["detail"], r"\d+\.\d+\s*%")
        self.assertNotIn("SVB", json.dumps(g))
        self.assertNotIn("Silicon Valley", json.dumps(advisor.cards(state)))

    def test_gauges_shape_and_stability(self):
        state = new_game("G", seed=42)
        for chunk in range(6):
            self._run(state, 120)
            g = advisor.gauges(state)
            self.assertEqual(len(g), 6)
            for x in g:
                self.assertIn(x["status"], ("g", "y", "r"))
                self.assertTrue(x["detail"])
                self.assertTrue(x["tab"])
                self.assertTrue(x.get("moved"), "gauge %s missing moved" % x["key"])
        json.dumps(g)   # must serialize

    def test_cards_actions_are_all_legal(self):
        """Every step on every card must pass validation when executed."""
        seen = set()
        for seed in (7, 42, 99, 1234):
            state = new_game("C%d" % seed, seed=seed)
            for chunk in range(8):
                self._run(state, 90)
                for c in advisor.cards(state):
                    seen.add(c["id"])
                    self.assertTrue(c["actions"], "card %s has no action" % c["id"])
                    for a in c["actions"]:
                        for s in a["steps"]:
                            if s["kind"] == "goto":
                                self.assertTrue(s.get("tab"))
                                continue
                            if s["kind"] == "set":
                                engine.set_policy(state, s["path"], s["value"])
                            else:
                                try:
                                    engine.perform_action(state, s["action"],
                                                          s["payload"])
                                except engine.ActionError as e:
                                    # only resource refusals are acceptable
                                    self.assertIn("cash", str(e).lower(),
                                                  "illegal advisor action %s: %s"
                                                  % (s, e))
                    advisor.dismiss(state, c["id"])
                self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        self.assertTrue(seen, "no advisor cards ever fired across 4 seeds")

    def test_dismiss_suppresses_card(self):
        state = new_game("D", seed=42)
        self._run(state, 300)
        cards = advisor.cards(state)
        if not cards:
            return
        cid = cards[0]["id"]
        engine.perform_action(state, "advisor_dismiss", {"card_id": cid})
        self.assertNotIn(cid, [c["id"] for c in advisor.cards(state)
                               if c["sev"] < 2])

    def test_tutorial_progresses(self):
        state = new_game("T", seed=42)
        t = advisor.tutorial(state)
        self.assertTrue(t["active"])
        self.assertFalse(any(s["done"] for s in t["steps"]))
        # acting in the game completes steps
        engine.set_policy(state, "deposits.offsets_bp.money_market", 25)
        engine.perform_action(state, "hire", {"role": "tellers", "count": 1})
        engine.perform_action(state, "tutorial_ack", {"step_id": "welcome"})
        t = advisor.tutorial(state)
        done = {s["id"]: s["done"] for s in t["steps"]}
        self.assertTrue(done["deposits"])
        self.assertTrue(done["people"])
        self.assertTrue(done["welcome"])
        # skip the whole tour
        engine.perform_action(state, "tutorial_off", {})
        self.assertFalse(advisor.tutorial(state)["active"])
        # first exam auto-completes the exam step
        self._run(state, 320)
        t = advisor.tutorial(state)
        self.assertTrue({s["id"]: s["done"] for s in t["steps"]}["exam"])

    def test_old_saves_get_advisor_lazily(self):
        state = new_game("Old", seed=1)
        del state["advisor"]     # simulate a save from before this feature
        advisor.ensure(state)
        self.assertIn("tutorial", state["advisor"])
        advisor.cards(state)     # must not raise
        advisor.gauges(state)

    def test_peer_averages_and_constants(self):
        state = new_game("P", seed=42)
        self._run(state, 60)
        p = advisor.peer_averages(state)
        self.assertTrue(0 < p["nim"] < 0.08)
        c = advisor.model_constants()
        self.assertIn("dep_sens", c)
        json.dumps(c)


if __name__ == "__main__":
    unittest.main()
