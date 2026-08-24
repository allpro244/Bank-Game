"""Regressions from the dual playtest (Fable + this agent)."""

import math
import os
import tempfile
import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import funding as FUND
from bankgame.sim import securities, operations, deposits as DEP
from bankgame.sim import loans as LN
from bankgame.sim import goals as GOALS
from bankgame.server import Game
from bankgame.store import Store


class TestCapitalCaps(unittest.TestCase):
    def test_trillion_raise_is_refused(self):
        state = new_game("Cap", seed=1)
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "raise_common",
                                  {"amount": 10 ** 14})
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "issue_brokered",
                                  {"amount": 10 ** 14, "term": 12})
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "issue_preferred",
                                  {"amount": 10 ** 14})
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "issue_subdebt",
                                  {"amount": 10 ** 14})
        self.assertLess(L.total_assets(state["bank"]["ledger"]),
                        100_000_000_00)

    def test_five_million_common_raise_still_clears(self):
        state = new_game("Raise", seed=3)
        engine.perform_action(state, "raise_common",
                              {"amount": 5_000_000_00})
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        self.assertGreater(state["bank"]["ledger"]["balances"]["1000"],
                           4_000_000_00)


class TestHtmSale(unittest.TestCase):
    def test_selling_starter_htm_leaves_1210_tied(self):
        state = new_game("HTM", seed=1)
        htm = [l for l in state["bank"]["securities"]["lots"]
               if l["cls"] == "HTM"]
        self.assertTrue(htm)
        securities.sell(state, htm[0]["id"])
        book = sum(l["book"] for l in state["bank"]["securities"]["lots"]
                   if l["cls"] == "HTM")
        self.assertEqual(state["bank"]["ledger"]["balances"]["1210"], book)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)


class TestSubledgerTies(unittest.TestCase):
    def test_prune_posts_crumb_to_ledger(self):
        state = new_game("Crumb", seed=2)
        cfg = state["bank"]["loans"]
        cfg["pools"].append({
            "product": "ci", "market": "caprock", "tier": "B",
            "vint": "1990", "balance": 91, "rate": 0.06, "quality": 1.0,
            "d30": 0, "d60": 0, "d90": 0, "npl": 0, "accrued": 0,
        })
        L.post(state["bank"]["ledger"], state["time"]["date"],
               "test crumb on books",
               [["1300", 91, 0], ["1000", 0, 91]], tag="test")
        before = state["bank"]["ledger"]["balances"]["1300"]
        LN._prune_pools(state, cfg)
        self.assertEqual(state["bank"]["ledger"]["balances"]["1300"],
                         before - 91)
        self.assertEqual(LN.total_loans(cfg),
                         state["bank"]["ledger"]["balances"]["1300"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_absorb_franchise_no_cent_leak(self):
        state = new_game("Abs", seed=4)
        deps = 10_000_000_07
        loans_amt = 6_000_000_05
        before_d = DEP.totals(state["bank"]["deposits"])["_total"]
        before_l = LN.total_loans(state["bank"]["loans"])
        engine._absorb_franchise(
            state, ["caprock", "verhalen", "plainview"],
            deps, loans_amt, 3, "Test Bank")
        after_d = DEP.totals(state["bank"]["deposits"])["_total"]
        after_l = LN.total_loans(state["bank"]["loans"])
        self.assertEqual(after_d - before_d, deps)
        self.assertEqual(after_l - before_l, loans_amt)


class TestOvernightHonesty(unittest.TestCase):
    def test_wait_does_not_reask_the_next_day(self):
        state = new_game("Wait", seed=5)
        from tests.test_funding_decisions import _drain_cash
        _drain_cash(state, 800_000_00)
        evs = FUND.manage_overnight(state)
        short = [e for e in evs if e.get("type") == "overnight_shortfall"]
        self.assertTrue(short)
        ev = engine.push_event(state, short[0])
        engine.perform_action(state, "event_choice",
                              {"event_id": ev["id"], "choice": "wait"})
        state["events"]["pending"] = [
            e for e in state["events"]["pending"] if e["id"] != ev["id"]]
        again = FUND.manage_overnight(state)
        self.assertFalse(any(e.get("type") == "overnight_shortfall"
                             for e in again))

    def test_fed_funds_choice_respects_limit(self):
        state = new_game("FF", seed=6)
        from tests.test_funding_decisions import _drain_cash
        _drain_cash(state, 50_000_000_00)
        evs = FUND.manage_overnight(state)
        short = [e for e in evs if e.get("type") == "overnight_shortfall"]
        self.assertTrue(short)
        ev = engine.push_event(state, short[0])
        engine.perform_action(state, "event_choice",
                              {"event_id": ev["id"], "choice": "fed_funds"})
        limit = FUND._ff_purchase_limit(state)
        self.assertLessEqual(-state["bank"]["ledger"]["balances"]["2110"],
                             limit)
        self.assertGreaterEqual(state["bank"]["ledger"]["balances"]["1000"], 0)

    def test_negative_vault_accrues_interest(self):
        state = new_game("OD", seed=7)
        led = state["bank"]["ledger"]
        L.post(led, state["time"]["date"], "test od",
               [["5170", led["balances"]["1000"] + 200_000_00, 0],
                ["1000", 0, led["balances"]["1000"] + 200_000_00]],
               tag="test")
        before_int = led["balances"]["5010"]
        FUND.accrue_day(state, 30)
        self.assertGreater(led["balances"]["5010"], before_int)


class TestInputHygiene(unittest.TestCase):
    def test_nan_policy_is_refused(self):
        state = new_game("NaN", seed=1)
        with self.assertRaises(engine.ActionError):
            engine.set_policy(state, "deposits.offsets_bp.money_market",
                              float("nan"))

    def test_unknown_repay_kind_is_clean(self):
        state = new_game("Repay", seed=1)
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "repay_funding",
                                  {"kind": "nope", "item_id": 1})

    def test_skip_inbox_advances_past_a_memo(self):
        state = new_game("Skip", seed=77)
        blocked = engine.advance(state, "month")
        self.assertEqual(blocked["days"], 0)
        self.assertTrue(blocked["inbox"])
        ran = engine.advance(state, "week", skip_inbox=True)
        self.assertGreater(ran["days"], 0)


class TestBranchGuards(unittest.TestCase):
    def test_cannot_open_second_home_branch(self):
        state = new_game("Dup", seed=77)
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "open_branch", {"market": "caprock"})

    def test_cannot_close_last_branch(self):
        state = new_game("Last", seed=77)
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "close_branch", {"branch_id": 1})
        self.assertEqual(len([b for b in state["bank"]["ops"]["branches"]
                              if b.get("open")]), 1)


class TestOwnerChrome(unittest.TestCase):
    def test_cash_numbers_agree(self):
        g = Game()
        g.state = new_game("Cash", seed=77)
        summ = g.summary()
        treas = g.section("treasury", {})
        self.assertEqual(summ["bank"]["cash"], treas["cash"])
        self.assertEqual(treas["cash"],
                         treas["vault"] + treas["fed_balances"]
                         + treas["fed_funds_sold"])

    def test_deposit_market_rates_follow_home(self):
        g = Game()
        g.state = new_game("VH", seed=77, home="verhalen")
        ui = g.section("deposits", {})["market_rates"]
        from bankgame.sim import competitors
        home = competitors.market_rates(g.state, "verhalen")["deposit"]
        self.assertEqual(ui["money_market"], home["money_market"])

    def test_world_bar_is_visible_on_day_one(self):
        state = new_game("World", seed=77, goal="world")
        p = GOALS.progress(state)
        self.assertGreater(p["pct"], 0.05)
        self.assertIn("Next to pass", p["text"])

    def test_fp_drag_is_the_computed_fraction(self):
        g = Game()
        g.state = new_game("FP", seed=1)
        drag = g.section("risk", {})["fraud"]["false_positive_drag"]
        self.assertAlmostEqual(drag, 0.006, places=4)


class TestStoreSummaryCache(unittest.TestCase):
    def test_list_saves_uses_cached_summary(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            store = Store(path)
            state = new_game("Cached", seed=9)
            store.create_save("Cached", 9)
            store.snapshot(state)
            loads = {"n": 0}
            orig = store.load

            def wrapped(*a, **k):
                loads["n"] += 1
                return orig(*a, **k)

            store.load = wrapped
            cards = store.list_saves()
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["name"], "Cached")
            self.assertEqual(loads["n"], 0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
