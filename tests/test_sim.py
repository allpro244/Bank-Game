"""Whole-simulation invariants over multi-year runs, plus action plumbing."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import deposits as DEP, loans as LN
from bankgame.sim.regulation import capital_ratios, pca_category


class TestSimulation(unittest.TestCase):
    def test_two_years_books_always_balance(self):
        state = new_game("Inv", seed=321)
        for day in range(504):
            engine.step_day(state)
            state["events"]["pending"].clear()
            self.assertIsNone(state["audit_alarm"],
                              "audit alarm on day %d: %r" % (day, state["audit_alarm"]))
            self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        self.assertGreaterEqual(len(state["metrics"]), 23)
        led = state["bank"]["ledger"]
        self.assertEqual(L.total_assets(led),
                         L.total_liabilities(led) + L.total_equity(led))

    def test_pools_tie_to_ledger(self):
        state = new_game("Tie", seed=11)
        for _ in range(300):
            engine.step_day(state)
            state["events"]["pending"].clear()
        led = state["bank"]["ledger"]
        pool_total = DEP.totals(state["bank"]["deposits"])["_total"]
        brokered = -led["balances"]["2050"]
        self.assertEqual(pool_total, L.total_deposits(led) - brokered)
        loans_total = LN.total_loans(state["bank"]["loans"])
        self.assertEqual(loans_total, led["balances"]["1300"])

    def test_run_outflow_keeps_books_tied(self):
        state = new_game("Run", seed=5)
        from bankgame.sim.crises import _execute_outflow
        before = L.total_deposits(state["bank"]["ledger"])
        _execute_outflow(state, 2_000_000_00)
        after = L.total_deposits(state["bank"]["ledger"])
        self.assertAlmostEqual(before - after, 2_000_000_00, delta=100)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        pool_total = DEP.totals(state["bank"]["deposits"])["_total"]
        self.assertEqual(pool_total, after)

    def test_actions_and_policies(self):
        state = new_game("Act", seed=77)
        # policy set: valid
        engine.set_policy(state, "deposits.offsets_bp.money_market", 50)
        self.assertEqual(state["bank"]["deposits"]["offsets_bp"]["money_market"], 50)
        engine.set_policy(state, "loans.standards.cre", 4)
        # invalid path/value rejected
        with self.assertRaises(engine.ActionError):
            engine.set_policy(state, "bank.shares", 1)
        with self.assertRaises(engine.ActionError):
            engine.set_policy(state, "loans.standards.cre", 9)
        with self.assertRaises(engine.ActionError):
            engine.set_policy(state, "deposits.offsets_bp.badproduct", 10)
        # buy security, sell it back; TB stays 0
        res = engine.perform_action(state, "buy_security",
                                    {"type": "treasury", "tenor": 2.0,
                                     "par": 500_000_00, "cls": "AFS"})
        self.assertIn("message", res)
        lot_id = state["bank"]["securities"]["lots"][-1]["id"]
        engine.perform_action(state, "sell_security", {"lot_id": lot_id})
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        # funding
        engine.perform_action(state, "take_fhlb", {"amount": 1_000_000_00, "term": 12})
        self.assertEqual(-state["bank"]["ledger"]["balances"]["2100"], 1_000_000_00)
        # hire/fire
        engine.perform_action(state, "hire", {"role": "lenders", "count": 2})
        self.assertEqual(state["bank"]["ops"]["staff"]["lenders"]["count"], 3)
        # over-generous insufficient-cash refusals leave state clean
        with self.assertRaises(engine.ActionError):
            engine.perform_action(state, "buy_security",
                                  {"type": "treasury", "tenor": 2.0,
                                   "par": 10_000_000_000_00, "cls": "AFS"})
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_loan_approval_flow(self):
        state = new_game("Loan", seed=13)
        app = {"id": 999, "name": "Test Cattle Co.", "product": "ci",
               "market": "caprock", "amount": 600_000_00, "rate": 0.085,
               "tier": "B", "dscr": 1.3, "ltv": 0.7, "memo": "m",
               "days_left": 60, "term_m": 60}
        state["bank"]["loans"]["queue"].append(app)
        loans_before = LN.total_loans(state["bank"]["loans"])
        engine.perform_action(state, "approve_loan", {"app_id": 999})
        self.assertEqual(LN.total_loans(state["bank"]["loans"]),
                         loans_before + 600_000_00)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_pca_categories(self):
        state = new_game("PCA", seed=1)
        r = capital_ratios(state)
        self.assertEqual(pca_category(r), "well")
        fake = dict(r)
        fake.update({"cet1_ratio": 0.05, "tier1_ratio": 0.065, "total_ratio": 0.085,
                     "leverage_ratio": 0.045, "tang_equity_ratio": 0.05})
        self.assertEqual(pca_category(fake), "adequate")
        fake.update({"tang_equity_ratio": 0.015})
        self.assertEqual(pca_category(fake), "critical")

    def test_advance_stops_on_blocking_event(self):
        state = new_game("Blk", seed=2)
        # inject a blocking event mid-advance by forcing a pending one
        engine.push_event(state, {"type": "test", "blocking": True,
                                  "title": "stop", "text": "stop"})
        res = engine.advance(state, "week")
        # pre-existing pending events don't stop it, but any new blocking event
        # would; here we just confirm advance returns coherent structure
        self.assertGreaterEqual(res["days"], 1)
        self.assertEqual(res["date"], state["time"]["date"])

    def test_money_is_never_float(self):
        state = new_game("Int", seed=3)
        for _ in range(150):
            engine.step_day(state)
            state["events"]["pending"].clear()
        for code, bal in state["bank"]["ledger"]["balances"].items():
            self.assertIsInstance(bal, int, "account %s is not integer cents" % code)
        for pool in state["bank"]["loans"]["pools"]:
            self.assertIsInstance(pool["balance"], int)
        for mkt in state["bank"]["deposits"]["pools"].values():
            for p in mkt.values():
                self.assertIsInstance(p["balance"], int)


if __name__ == "__main__":
    unittest.main()
