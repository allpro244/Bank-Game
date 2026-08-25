"""A3: targets are sized to the buyer; denied deals do not mutate the ledger."""

import copy
import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim.regulation import capital_ratios, pca_category


def _run(state, days):
    for _ in range(days):
        engine.step_day(state)
        state["events"]["pending"].clear()


class TestMA(unittest.TestCase):
    def test_starter_bank_cannot_be_offered_nyc(self):
        state = new_game("NYC", seed=1)
        mkts = engine._eligible_ma_markets(state)
        self.assertNotIn("nyc", mkts)
        self.assertNotIn("dallas", mkts)
        self.assertTrue(any(state["regions"][m]["kind"] in ("rural", "small_metro")
                            for m in mkts))

    def test_fdic_whale_is_refused(self):
        state = new_game("Whale", seed=4)
        snap = copy.deepcopy(state["bank"]["ledger"])
        ev = {
            "franchise": {
                "deposits": 20_000_000_000_00, "loans": 16_000_000_000_00,
                "credit_mark": 0.08, "branches": 40, "markets": ["nyc"],
                "rival_bid_bp": 10,
            },
            "bank_name": "Empire Clearing Bank",
        }
        pf = engine.fdic_proforma(state, ev["franchise"], 80)
        self.assertFalse(pf["can_bid"])
        res = engine._resolve_fdic_bid(state, ev, 80)
        self.assertIsInstance(res, str)
        self.assertIn("franchise", res.lower())
        self.assertEqual(state["bank"]["ledger"]["balances"], snap["balances"])

    def test_denied_deal_leaves_ledger_untouched(self):
        state = new_game("Deny", seed=4)
        snap = copy.deepcopy(state["bank"]["ledger"])
        deal = {"name": "Too Big Bank", "assets": 80_000_000_00,
                "price": 12_000_000_00, "market": "caprock",
                "credit_mark": 0.05}
        ev = {"deal": deal}
        res = engine._resolve_bank_purchase(state, ev)
        self.assertIsInstance(res, str)
        self.assertEqual(state["bank"]["ledger"]["balances"], snap["balances"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_buy_stays_community_scale(self):
        state = new_game("Buy", seed=9)
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        assets = L.total_assets(state["bank"]["ledger"])
        t_assets = int(assets * 0.30)
        deal = {"name": "Farmers State Bank", "assets": t_assets,
                "price": 400_000_00, "market": "verhalen",
                "credit_mark": 0.05}
        pf = engine.deal_proforma(state, deal)
        self.assertTrue(pf["can_buy"], pf["blockers"])
        res = engine._resolve_bank_purchase(state, {"deal": deal})
        self.assertIsInstance(res, dict)
        _run(state, 90)
        after = L.total_assets(state["bank"]["ledger"])
        self.assertLess(after, 200_000_000_00)
        self.assertIsNone(state["game_over"])
        self.assertIn(pca_category(capital_ratios(state)), ("well", "adequate"))

    def test_multi_seed_no_whale_jump(self):
        """A few unattended years: no single deal blows a $25M book past $200M."""
        for seed in (1, 7, 14, 21, 33, 44, 55, 88):
            state = new_game("M%d" % seed, seed=seed)
            state["bank"]["loans"]["queue"].clear()
            peak = L.total_assets(state["bank"]["ledger"])
            for _ in range(756):
                before = L.total_assets(state["bank"]["ledger"])
                engine.step_day(state)
                # auto-pass sale offers so we only measure what a buy would do
                for ev in list(state["events"]["pending"]):
                    if ev.get("type") == "bank_for_sale" and ev.get("deal"):
                        after_buy = before + ev["deal"]["assets"]
                        self.assertLess(
                            after_buy, 200_000_000_00,
                            "seed %s deal %s would jump to $%s"
                            % (seed, ev["deal"]["name"],
                               f"{after_buy // 100:,}"))
                        self.assertLessEqual(
                            ev["deal"]["assets"],
                            int(before * 0.40) + 1)
                    if ev.get("type") == "overnight_shortfall":
                        engine.set_policy(state, "funding.overnight_policy", "auto")
                state["events"]["pending"].clear()
                peak = max(peak, L.total_assets(state["bank"]["ledger"]))
            self.assertLess(peak, 80_000_000_00, "seed %s peak $%s"
                            % (seed, f"{peak // 100:,}"))

    def test_absorb_does_not_plant_a_window_farm(self):
        state = new_game("Farm", seed=1)
        before = sum(1 for b in state["bank"]["ops"]["branches"]
                     if b.get("open") and b.get("market") == "austin")
        engine._absorb_franchise(
            state, ["austin"], 500_000_000_00, 300_000_000_00, 40, "Test Bank")
        added = sum(1 for b in state["bank"]["ops"]["branches"]
                    if b.get("open") and b.get("market") == "austin") - before
        self.assertGreaterEqual(added, 1)
        self.assertLessEqual(added, 3)


if __name__ == "__main__":
    unittest.main()
