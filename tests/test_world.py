"""F1–F4: news filter, rarer fraud, era copy, market share ceiling."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, economy, advisor, goals
from bankgame.sim import deposits as DEP
from bankgame.sim import fraud as FR
from bankgame.sim import rng as R


class TestWorld(unittest.TestCase):
    def test_unserved_region_shock_stays_out_of_inbox(self):
        state = new_game("News", seed=3)
        ev = {"type": "region_shock", "region": "nyc",
              "title": "New York, NY: Hurricane landfall", "text": "x"}
        self.assertFalse(engine._inbox_worthy(state, ev))
        ev_home = {"type": "region_shock", "region": "caprock",
                   "title": "home", "text": "x"}
        self.assertTrue(engine._inbox_worthy(state, ev_home))
        self.assertIn("caprock", engine.served_markets(state))
        self.assertNotIn("nyc", engine.served_markets(state))

    def test_fraud_cases_are_rare_over_three_years(self):
        counts = []
        for seed in (11, 33):
            state = new_game("Fr%d" % seed, seed=seed)
            state["bank"]["loans"]["queue"].clear()
            state["bank"]["funding"]["overnight_policy"] = "auto"
            n = 0
            for _ in range(756):
                evs = engine.step_day(state)
                state["events"]["pending"].clear()
                n += sum(1 for e in evs if e.get("type") == "fraud_case")
            counts.append(n)
        # Wallpaper was 5–8 in 3 years. Meaner cadence should stay under that.
        self.assertLessEqual(max(counts), 4)
        self.assertLessEqual(sum(counts) / len(counts), 2.5)

    def test_sandbox_gauges_never_name_svb(self):
        state = new_game("Era", seed=1, era="sandbox")
        self.assertFalse(goals.allow_svb_name(state))
        blob = str(advisor.gauges(state))
        self.assertNotIn("SVB", blob)
        self.assertNotIn("Silicon Valley", blob)

    def test_historical_allows_svb_after_2015(self):
        state = new_game("Hist", seed=1, era="historical")
        self.assertFalse(goals.allow_svb_name(state))  # starts 2000
        state["time"]["date"] = "2016-03-15"
        self.assertTrue(goals.allow_svb_name(state))
        # Nudge pulls 2008 toward a bust, not a boom
        e = economy.new_economy(R.Rng(R.make_streams(1, ["econ"])["econ"]))
        before = e["credit_stress"]
        for _ in range(8):
            economy._nudge_historical(e, "2008-10-01")
        self.assertGreater(e["credit_stress"], before)
        self.assertGreater(e["credit_stress"], 0.25)

    def test_25m_ceiling_is_tiny_in_dallas(self):
        state = new_game("Ceil", seed=3)
        cap = DEP.size_share_cap(state, "dallas", 25_000_000_00)
        self.assertLess(cap, 0.003)
        home = DEP.size_share_cap(state, "caprock", 25_000_000_00)
        self.assertGreater(home, cap)


class TestFraudSpawn(unittest.TestCase):
    def test_case_amounts_can_be_six_figures(self):
        state = new_game("Big", seed=8)
        state["bank"]["cached_assets"] = 80_000_000_00
        rng = R.Rng(R.make_streams(8, ["fraud"])["fraud"])
        ev = FR._spawn_case(state, rng)
        self.assertIn("case_id", ev)
        case = state["bank"]["fraud"]["cases"][-1]
        self.assertGreaterEqual(case["amount"], 15_000_00)


if __name__ == "__main__":
    unittest.main()
