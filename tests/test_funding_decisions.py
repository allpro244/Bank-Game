"""A4: overnight shortfall is a decision; auto still balances the books."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import funding as FUND
from bankgame.sim import loans as LN


def _drain_cash(state, hole):
    """Force operating cash negative by `hole` cents. Leaves TB = 0."""
    led = state["bank"]["ledger"]
    date = state["time"]["date"]
    liquid = (led["balances"]["1000"] + led["balances"]["1010"]
              + led["balances"]["1100"])
    # consolidate into 1000, then spend past zero
    for acct in ("1010", "1100"):
        bal = led["balances"][acct]
        if bal > 0:
            L.post(led, date, "test: consolidate liquid",
                   [["1000", bal, 0], [acct, 0, bal]], tag="test")
    spend = led["balances"]["1000"] + hole
    L.post(led, date, "test: cash hole",
           [["5170", spend, 0], ["1000", 0, spend]], tag="test")
    self_tb = L.trial_balance(led)
    assert self_tb == 0, self_tb


class TestFundingDecisions(unittest.TestCase):
    def test_ask_does_not_use_window_until_player_chooses(self):
        state = new_game("Ask", seed=5)
        self.assertEqual(state["bank"]["funding"]["overnight_policy"], "ask")
        uses = state["bank"]["funding"]["discount_window_uses"]
        _drain_cash(state, 800_000_00)
        evs = FUND.manage_overnight(state)
        self.assertEqual(state["bank"]["funding"]["discount_window_uses"], uses)
        short = [e for e in evs if e.get("type") == "overnight_shortfall"]
        self.assertTrue(short, "ask policy should raise a shortfall event")
        self.assertTrue(short[0]["blocking"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

        ev = engine.push_event(state, short[0])
        engine.perform_action(state, "event_choice",
                              {"event_id": ev["id"], "choice": "window"})
        self.assertEqual(state["bank"]["funding"]["discount_window_uses"], uses + 1)
        self.assertGreaterEqual(state["bank"]["ledger"]["balances"]["1000"], 0)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_auto_covers_and_keeps_books_balanced(self):
        state = new_game("Auto", seed=6)
        engine.set_policy(state, "funding.overnight_policy", "auto")
        _drain_cash(state, 800_000_00)
        evs = FUND.manage_overnight(state)
        self.assertGreaterEqual(state["bank"]["ledger"]["balances"]["1000"], 0)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        self.assertFalse(any(e.get("type") == "overnight_shortfall" for e in evs))

    def test_fed_balances_cover_a_vault_hole_without_a_popup(self):
        """$800k at the Fed is the bank's money. Do not ask to borrow it."""
        state = new_game("Fed", seed=5)
        led = state["bank"]["ledger"]
        date = state["time"]["date"]
        # leave 1010 intact; drain only vault and FFS so vault goes negative
        if led["balances"]["1100"] > 0:
            L.post(led, date, "test: drain ffs",
                   [["1000", led["balances"]["1100"], 0],
                    ["1100", 0, led["balances"]["1100"]]], tag="test")
        fed = led["balances"]["1010"]
        self.assertGreater(fed, 200_000_00)
        hole = 150_000_00
        L.post(led, date, "test: vault hole smaller than Fed balances",
               [["5170", led["balances"]["1000"] + hole, 0],
                ["1000", 0, led["balances"]["1000"] + hole]], tag="test")
        self.assertLess(led["balances"]["1000"], 0)
        evs = FUND.manage_overnight(state)
        self.assertFalse(any(e.get("type") == "overnight_shortfall" for e in evs))
        self.assertGreaterEqual(led["balances"]["1000"], 0)
        self.assertLess(led["balances"]["1010"], fed)
        self.assertEqual(L.trial_balance(led), 0)

    def test_shortfall_need_is_only_the_remaining_hole(self):
        state = new_game("Hole", seed=5)
        _drain_cash(state, 800_000_00)
        evs = FUND.manage_overnight(state)
        short = [e for e in evs if e.get("type") == "overnight_shortfall"]
        self.assertTrue(short)
        # no extra cash-target cushion on top of the settlement hole
        self.assertEqual(short[0]["need"], 800_000_00)

    def test_wait_leaves_uses_unchanged(self):
        state = new_game("Wait", seed=7)
        uses = state["bank"]["funding"]["discount_window_uses"]
        _drain_cash(state, 400_000_00)
        evs = FUND.manage_overnight(state)
        ev = engine.push_event(state, evs[0])
        engine.perform_action(state, "event_choice",
                              {"event_id": ev["id"], "choice": "wait"})
        self.assertEqual(state["bank"]["funding"]["discount_window_uses"], uses)
        self.assertTrue(state["bank"]["funding"].get("shrink_originations"))

    def test_wait_shrinks_next_month_originations(self):
        a = new_game("A", seed=9)
        b = new_game("B", seed=9)
        a["bank"]["loans"]["queue"].clear()
        b["bank"]["loans"]["queue"].clear()
        b["bank"]["funding"]["shrink_originations"] = True
        LN.originate_month(a, engine._rng(a, "credit"))
        LN.originate_month(b, engine._rng(b, "credit"))
        self.assertLess(b["bank"]["loans"]["stats"]["originated_mtd"],
                        a["bank"]["loans"]["stats"]["originated_mtd"])
        self.assertFalse(b["bank"]["funding"].get("shrink_originations"))

    def test_overnight_fhlb_is_three_months(self):
        state = new_game("Term", seed=5)
        _drain_cash(state, 800_000_00)
        evs = FUND.manage_overnight(state)
        ev = engine.push_event(state, evs[0])
        engine.perform_action(state, "event_choice",
                              {"event_id": ev["id"], "choice": "fhlb"})
        self.assertEqual(state["bank"]["funding"]["fhlb"][-1]["months_left"],
                         FUND.OVERNIGHT_FHLB_MONTHS)

    def test_month_open_card_names_the_notes_we_just_booked(self):
        """The hole is real. The card has to say we just funded the month."""
        state = new_game("Notes", seed=5)
        state["time"]["date"] = "2000-02-01"  # Tuesday, month-open morning
        _drain_cash(state, 0)
        LN.originate_month(state, engine._rng(state, "credit"))
        booked = state["bank"]["loans"]["stats"]["originated_mtd"]
        self.assertGreater(booked, 0)
        self.assertLess(state["bank"]["ledger"]["balances"]["1000"], 0)
        evs = FUND.manage_overnight(state)
        short = [e for e in evs if e.get("type") == "overnight_shortfall"]
        self.assertTrue(short)
        ev = short[0]
        amt = f"{booked // 100:,}"
        self.assertEqual(ev["originated"], booked)
        self.assertIn(amt, ev["cause"])
        self.assertIn("new notes", ev["cause"])
        self.assertIn("vault is empty", ev["cause"])
        self.assertIn(amt, ev["text"])
        self.assertIn("bond book", ev["text"])
        self.assertIn("does not fill this hole", ev["text"])
        self.assertIn(amt, ev["owner_summary"])
        self.assertIn("new loans", ev["owner_summary"])
        # ask still does not touch the window
        self.assertEqual(state["bank"]["funding"]["discount_window_uses"], 0)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_mid_month_hole_does_not_claim_we_just_booked(self):
        state = new_game("Mid", seed=5)
        state["time"]["date"] = "2000-01-18"
        state["bank"]["loans"]["stats"]["originated_mtd"] = 1_500_000_00
        _drain_cash(state, 200_000_00)
        evs = FUND.manage_overnight(state)
        short = [e for e in evs if e.get("type") == "overnight_shortfall"]
        self.assertTrue(short)
        ev = short[0]
        self.assertIsNone(ev.get("cause"))
        self.assertEqual(ev.get("originated") or 0, 0)
        self.assertNotIn("new notes", ev["text"])
        self.assertNotIn("we just funded", ev["text"].lower())


if __name__ == "__main__":
    unittest.main()
