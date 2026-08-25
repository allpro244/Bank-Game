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


def _sized_deal(state, name="Farmers State Bank"):
    from bankgame.sim import competitors as C
    assets = state["bank"].get("cached_assets") or L.total_assets(state["bank"]["ledger"])
    deal = {"name": name, "assets": int(assets * 0.25),
            "price": 400_000_00, "market": "verhalen", "credit_mark": 0.05}
    rival = C.circling_rival(state, deal)
    if rival:
        deal["circling_id"] = rival["id"]
        deal["circling_name"] = rival["name"]
    return deal


class TestRivalStealsTarget(unittest.TestCase):
    def test_hold_parks_the_book_and_the_clock_can_run(self):
        state = new_game("Hold", seed=4)
        state["bank"]["loans"]["queue"].clear()
        snap = copy.deepcopy(state["bank"]["ledger"]["balances"])
        deal = _sized_deal(state)
        item = engine.park_deal(state, {"deal": deal})
        self.assertIsInstance(item, dict)
        self.assertEqual(len(state["ma_pipeline"]), 1)
        self.assertEqual(state["bank"]["ledger"]["balances"], snap)
        res = engine.advance(state, "until", max_days=5)
        self.assertGreater(res["days"], 0)

    def test_pass_lets_a_rival_take_the_book(self):
        from bankgame.sim import competitors as C
        state = new_game("Pass", seed=4)
        deal = _sized_deal(state)
        rival = C.find_rival(state, deal["circling_id"])
        before = rival["assets"]
        snap = copy.deepcopy(state["bank"]["ledger"]["balances"])
        res = engine.pass_private_deal(state, deal, force=True)
        self.assertTrue(res["stolen"])
        self.assertEqual(state["bank"]["ledger"]["balances"], snap)
        self.assertGreater(rival["assets"], before)
        self.assertIn("verhalen", rival["markets"])

    def test_close_from_pipeline_buys_the_book(self):
        state = new_game("Close", seed=9)
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        deal = _sized_deal(state)
        item = engine.park_deal(state, {"deal": deal})
        res = engine.close_pipeline_deal(state, item["id"])
        self.assertIsInstance(res, dict)
        self.assertFalse(state["ma_pipeline"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_deadline_steals_the_book(self):
        from bankgame.sim import competitors as C
        state = new_game("Late", seed=4)
        deal = _sized_deal(state)
        rival = C.find_rival(state, deal["circling_id"])
        before = rival["assets"]
        item = engine.park_deal(state, {"deal": deal})
        item["months_left"] = 0
        evs = engine._pipeline_month(state, engine._rng(state, "event"))
        self.assertTrue(evs)
        self.assertEqual(evs[0]["type"], "deal_stolen")
        self.assertTrue(evs[0]["stolen"])
        self.assertFalse(state["ma_pipeline"])
        self.assertGreater(rival["assets"], before)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_advisor_names_the_circling_rival(self):
        from bankgame.sim import advisor
        state = new_game("Card", seed=4)
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        deal = _sized_deal(state)
        engine.park_deal(state, {"deal": deal})
        card = advisor._r_pipeline_deal(state)
        self.assertIsNotNone(card)
        self.assertIn(deal["circling_name"].split()[0], card["title"] + card["text"])


if __name__ == "__main__":
    unittest.main()
