"""D1–D4: charter options, goals, digest, autopsy."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import goals as GOALS
from bankgame.sim import deposits as DEP


class TestGoals(unittest.TestCase):
    def test_defaults_and_display_date(self):
        state = new_game("G", seed=1)
        self.assertEqual(state["meta"]["goal"], "world")
        self.assertEqual(state["meta"]["era"], "sandbox")
        self.assertEqual(state["meta"]["home"], "caprock")
        self.assertIn("Year 1", GOALS.display_date(state))
        hist = new_game("H", seed=1, era="historical")
        self.assertEqual(GOALS.display_date(hist), hist["time"]["date"])

    def test_home_market_verhalen(self):
        state = new_game("V", seed=2, home="verhalen")
        self.assertEqual(state["meta"]["home"], "verhalen")
        self.assertIn("verhalen", state["bank"]["deposits"]["pools"])
        self.assertNotIn("caprock", state["bank"]["deposits"]["pools"])
        self.assertEqual(state["bank"]["ops"]["branches"][0]["market"], "verhalen")
        self.assertEqual(state["bank"]["loans"]["queue"][0]["market"], "verhalen")
        self.assertGreater(DEP.market_deposits(state, "verhalen"), 10_000_000_00)

    def test_easy_adds_capital(self):
        std = new_game("S", seed=3)
        easy = new_game("E", seed=3, difficulty="easy")
        self.assertGreater(L.total_equity(easy["bank"]["ledger"]),
                           L.total_equity(std["bank"]["ledger"]))
        self.assertEqual(easy["regulation"]["months_to_exam"], 20)
        self.assertEqual(L.trial_balance(easy["bank"]["ledger"]), 0)

    def test_hard_thins_cash(self):
        std = new_game("S", seed=3)
        hard = new_game("H", seed=3, difficulty="hard")
        self.assertLess(hard["bank"]["ledger"]["balances"]["1000"],
                        std["bank"]["ledger"]["balances"]["1000"])
        self.assertEqual(hard["regulation"]["months_to_exam"], 10)
        self.assertEqual(L.trial_balance(hard["bank"]["ledger"]), 0)

    def test_progress_and_digest_after_a_month(self):
        state = new_game("D", seed=4, goal="independent")
        state["bank"]["loans"]["queue"].clear()
        for _ in range(32):
            engine.step_day(state)
            state["events"]["pending"].clear()
        self.assertTrue(state["digests"])
        d = state["digests"][-1]
        self.assertIn("econ", d)
        self.assertIn("ni", d)
        p = GOALS.progress(state)
        self.assertEqual(p["id"], "independent")
        self.assertGreater(p["pct"], 0)
        self.assertFalse(p["won"])

    def test_autopsy_on_forced_seizure(self):
        state = new_game("A", seed=5)
        state["regulation"]["seized"] = True
        engine._game_over(state, "seized")
        g = state["game_over"]
        self.assertEqual(g["kind"], "seized")
        self.assertTrue(g["summary"])
        self.assertIn("peak_ldr", g)
        self.assertIn("notes", g)
        self.assertTrue(g["earlier"])

    def test_independent_wins_at_year_20(self):
        state = new_game("W", seed=6, goal="independent")
        state["economy"]["months"] = 240
        ev = GOALS.check_win(state)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["type"], "goal_won")
        self.assertTrue(state["meta"]["goal_won"])

    def test_world_goal_bar_is_not_halfway_on_charter_day(self):
        state = new_game("WorldBar", seed=8, goal="world")
        p = GOALS.progress(state)
        race = GOALS.world_race(state)
        self.assertLess(race["me"], race["rival_assets"] / 100)
        # $20M vs Empire (~$26B) and $250B is a rounding error, not 28%.
        self.assertLess(p["pct"], 0.03)
        self.assertIn("Empire", p["text"])

    def test_world_goal_tracks_rank_and_can_win(self):
        state = new_game("World", seed=8, goal="world")
        p = GOALS.progress(state)
        self.assertEqual(p["id"], "world")
        self.assertIn("#", p["text"])
        self.assertFalse(p["won"])
        self.assertIsNone(GOALS.check_win(state))
        old = GOALS.WORLD_CROWN
        try:
            GOALS.WORLD_CROWN = 1
            for b in state["competitors"]["banks"]:
                b["assets"] = 1
            ev = GOALS.check_win(state)
            self.assertIsNotNone(ev)
            self.assertEqual(ev["type"], "goal_won")
            self.assertIn("Biggest", ev["title"])
            self.assertTrue(state["meta"]["goal_won"])
        finally:
            GOALS.WORLD_CROWN = old

    def test_summarize_save(self):
        state = new_game("Sum", seed=7, goal="square")
        card = GOALS.summarize_save(state)
        self.assertEqual(card["goal"], "square")
        self.assertGreater(card["assets"], 0)
        self.assertEqual(card["pca"], "well")


if __name__ == "__main__":
    unittest.main()
