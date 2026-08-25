"""Per-market pricing, earned busts, listing, weight-class markets."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import deposits as DEP
from bankgame.sim import loans as LN
from bankgame.sim import funding as FUND
from bankgame.sim import operations as OPS
from bankgame.sim import regions as REGN
from bankgame.sim import advisor


class TestTownPricing(unittest.TestCase):
    def test_town_offset_does_not_reprice_the_franchise(self):
        state = new_game("Town", seed=4)
        engine.set_policy(state, "deposits.offsets_bp.money_market", 0)
        home = DEP.effective_rate(state, "money_market", "caprock")
        engine.set_policy(state, "deposits.market_offsets_bp.verhalen.money_market", 50)
        self.assertEqual(DEP.effective_rate(state, "money_market", "caprock"), home)
        self.assertGreater(DEP.effective_rate(state, "money_market", "verhalen"), home)

    def test_leak_card_names_the_town(self):
        state = new_game("Leak", seed=1)
        DEP.open_market(state["bank"]["deposits"], "verhalen")
        state["bank"]["ops"]["branches"].append({
            "id": 9, "market": "verhalen", "open": True, "quality": 2,
            "monthly_cost": 15000_00, "opened": state["time"]["date"],
        })
        state["bank"]["deposits"]["pools"]["verhalen"]["money_market"]["balance"] = 800_000_00
        state["bank"]["deposits"]["pools"]["caprock"]["money_market"]["balance"] = 50_000_00
        state["metrics"] = [{"earnings_ready": True, "roa": 0.01}]
        engine.set_policy(state, "deposits.offsets_bp.money_market", -50)
        card = advisor._r_market_leak(state)
        self.assertIsNotNone(card)
        self.assertIn("verhalen", card["actions"][0]["steps"][0]["path"])


class TestEarnedBusts(unittest.TestCase):
    def test_calm_books_do_not_change(self):
        self.assertEqual(LN.vintage_stress_mult(1.45, 0.05), 1.0)
        self.assertEqual(LN.vintage_stress_mult(0.65, 0.05), 1.0)

    def test_loose_vintage_hurts_more_than_tight_in_a_bust(self):
        loose = LN.vintage_stress_mult(1.45, 0.70)
        tight = LN.vintage_stress_mult(0.65, 0.70)
        self.assertGreater(loose, 1.15)
        self.assertLess(tight, 1.0)
        self.assertGreater(loose, tight * 1.4)


class TestListing(unittest.TestCase):
    def test_community_bank_cannot_list(self):
        state = new_game("Priv", seed=5)
        prev = FUND.listing_preview(state)
        self.assertIsInstance(prev, str)
        self.assertIn("500", prev)

    def test_regional_can_list_and_buyback_hits_the_print(self):
        state = new_game("Pub", seed=5)
        state["bank"]["cached_assets"] = 600_000_000_00
        state["metrics"] = [{"earnings_ready": True, "roa": 0.011, "roe": 0.10}]
        state["bank"]["roe_ttm"] = 0.10
        # Seed cash for fees.
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        prev = FUND.listing_preview(state)
        self.assertIsInstance(prev, dict)
        res = engine.perform_action(state, "list_common", {})
        self.assertNotIsInstance(res, str)
        self.assertTrue(state["bank"]["listed"])
        q = FUND.share_quote(state)
        state["bank"]["share_px"] = 50_00
        bb = FUND.buyback(state, 500_000_00)
        self.assertNotIsInstance(bb, str)
        self.assertEqual(bb["price"], 50_00)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)


class TestWeightClass(unittest.TestCase):
    def test_des_moines_is_locked_at_opening(self):
        state = new_game("IA", seed=2)
        self.assertFalse(REGN.market_unlocked(state, "desmoines"))
        prev = OPS.preview_branch(state, "desmoines")
        self.assertEqual(prev["verdict"], "locked")
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "open_branch", {"market": "desmoines"})

    def test_des_moines_unlocks_at_200m(self):
        state = new_game("IA2", seed=2)
        state["bank"]["cached_assets"] = 200_000_000_00
        self.assertTrue(REGN.market_unlocked(state, "desmoines"))
        self.assertFalse(REGN.market_unlocked(state, "chicago"))

    def test_dallas_90_days_still_holds(self):
        state = new_game("Dallas", seed=11)
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        engine.perform_action(state, "open_branch", {"market": "dallas"})
        for _ in range(90):
            engine.step_day(state)
            state["events"]["pending"].clear()
        dallas = DEP.market_deposits(state, "dallas")
        self.assertLess(dallas, 15_000_000_00)
        self.assertIsNone(state["game_over"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

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
