"""A1/A2: new-market share stays tiny; branch preview matches the engine."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import deposits as DEP
from bankgame.sim import operations as OPS
from bankgame.sim.regulation import capital_ratios, pca_category


def _run(state, days):
    for _ in range(days):
        engine.step_day(state)
        state["events"]["pending"].clear()


class TestMarkets(unittest.TestCase):
    def test_dallas_90_days_is_not_a_seizure(self):
        state = new_game("Dallas", seed=11)
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        engine.perform_action(state, "open_branch", {"market": "dallas"})
        _run(state, 90)
        dallas = DEP.market_deposits(state, "dallas")
        self.assertLess(dallas, 15_000_000_00,
                        "Dallas gathered $%s in 90 days" % f"{dallas // 100:,}")
        self.assertIsNone(state["game_over"])
        self.assertEqual(pca_category(capital_ratios(state)), "well")
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_verhalen_one_year_stays_community_scale(self):
        state = new_game("Verhalen", seed=22)
        engine.perform_action(state, "open_branch", {"market": "verhalen"})
        home0 = DEP.market_deposits(state, "caprock")
        _run(state, 252)
        home = DEP.market_deposits(state, "caprock")
        verd = DEP.market_deposits(state, "verhalen")
        self.assertGreater(home + verd, home0)
        self.assertGreater(verd, 0)
        assets = L.total_assets(state["bank"]["ledger"])
        self.assertLess(assets, 50_000_000_00)
        self.assertGreater(assets, 18_000_000_00)
        self.assertEqual(pca_category(capital_ratios(state)), "well")
        self.assertIsNone(state["game_over"])

    def test_size_cap_distinguishes_20m_from_2b(self):
        small = new_game("S", seed=3)
        small["bank"]["cached_assets"] = 20_000_000_00
        big = new_game("B", seed=3)
        big["bank"]["cached_assets"] = 2_000_000_000_00
        cap_s = DEP.size_share_cap(small, "dallas")
        cap_b = DEP.size_share_cap(big, "dallas")
        # Caps are now vs the Dallas catchment, not the $100B+ pool.
        self.assertLess(cap_s, 0.02)
        self.assertGreater(cap_b, 0.20)
        self.assertGreater(cap_b, cap_s * 10)
        full_s = DEP.share_of_full_pool(small, "dallas", extra_offices=1, maturity=1.0)
        self.assertLess(full_s, 0.001)

    def test_preview_uses_same_helpers_as_engine(self):
        state = new_game("Prev", seed=4)
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        for mid in ("verhalen", "dallas", "nyc"):
            prev = OPS.preview_branch(state, mid)
            self.assertEqual(prev["cost"], OPS.branch_open_cost(state["regions"][mid]))
            self.assertEqual(prev["year1_gather"],
                             DEP.year1_gather_estimate(state, mid))
            self.assertIn(prev["verdict"],
                          ("cannot_fund", "lethal", "stretch", "safe"))
        nyc = OPS.preview_branch(state, "nyc")
        verd = OPS.preview_branch(state, "verhalen")
        self.assertGreater(nyc["cost"], verd["cost"])
        # After A1 the gather is size-capped, so NYC is expensive — not a
        # $900M seizure. Year-1 deposits stay a rounding error vs the pool.
        self.assertLess(nyc["year1_gather"], nyc["pool"] * 0.001)

    def test_metro_offices_do_not_stack_full_catchments(self):
        state = new_game("Stack", seed=11)
        one = DEP.trade_pool(state, "houston", extra_offices=1)
        five = DEP.trade_pool(state, "houston", extra_offices=5)
        self.assertGreater(five, one)
        self.assertLess(five, one * 3,
                        "five Houston windows must overlap, not 5× catchment")
        self.assertAlmostEqual(DEP.office_effective(1), 1.0)
        self.assertAlmostEqual(DEP.office_size_boost(1), 1.0)
        self.assertLess(DEP.office_size_boost(5), 1.30)

    def test_second_office_preview_is_not_blocked(self):
        state = new_game("Home2", seed=4)
        prev = OPS.preview_branch(state, "caprock")
        self.assertTrue(prev["already"])
        self.assertGreater(prev["offices"], 0)
        self.assertNotEqual(prev["verdict"], "cannot_fund")
        broke = new_game("Broke", seed=4)
        self.assertEqual(OPS.preview_branch(broke, "nyc")["verdict"], "cannot_fund")


if __name__ == "__main__":
    unittest.main()
