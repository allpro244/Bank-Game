"""Interest and pricing math."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import ledger as L, deposits, loans, securities
from bankgame.sim.economy import yield_at


class TestInterest(unittest.TestCase):
    def setUp(self):
        self.state = new_game("Test Bank", seed=1)

    def test_deposit_accrual_exact(self):
        state = self.state
        deps = state["bank"]["deposits"]
        # wipe pools, install one known pool
        for mid in list(deps["pools"]):
            for p in deposits.PRODUCTS:
                deps["pools"][mid][p]["balance"] = 0
        deps["pools"]["caprock"]["savings"]["balance"] = 1_000_000_00
        deps["offsets_bp"]["savings"] = 0
        rate = deposits.effective_rate(state, "savings")
        expense_before = L.display_balance(state["bank"]["ledger"], "5000")
        accrued = deposits.step_day(state, 1)
        expected = int(round(1_000_000_00 * rate / 365.0))
        self.assertEqual(accrued, expected)
        self.assertEqual(L.display_balance(state["bank"]["ledger"], "5000")
                         - expense_before, expected)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_weekend_accrues_three_days(self):
        state = self.state
        deps = state["bank"]["deposits"]
        for mid in list(deps["pools"]):
            for p in deposits.PRODUCTS:
                deps["pools"][mid][p]["balance"] = 0
        deps["pools"]["caprock"]["money_market"]["balance"] = 500_000_00
        rate = deposits.effective_rate(state, "money_market")
        one = deposits.step_day(state, 1)
        three = deposits.step_day(state, 3)
        self.assertEqual(one, int(round(500_000_00 * rate / 365.0)))
        self.assertEqual(three, int(round(500_000_00 * rate * 3 / 365.0)))

    def test_loan_accrual_skips_nonaccrual(self):
        state = self.state
        cfg = state["bank"]["loans"]
        cfg["pools"] = []
        cfg["large"] = []
        loans.add_to_pool(cfg, "ci", "caprock", "B", "2000", 1_000_000_00, 0.0730, 1.0)
        cfg["pools"][0]["npl"] = 0.25   # a quarter of the pool on nonaccrual
        accrued = loans.step_day(state, 1)
        expected = int(round(750_000_00 * 0.0730 / 365.0))
        self.assertEqual(accrued, expected)

    def test_bond_prices_at_par_when_bought(self):
        state = self.state
        lot = securities.buy(state, "treasury", 5.0, 1_000_000_00, "AFS")
        self.assertIsInstance(lot, dict)
        px = securities.price_lot(state["economy"], lot)
        self.assertAlmostEqual(px / lot["par"], 1.0, delta=0.01)

    def test_bond_price_falls_when_rates_rise(self):
        state = self.state
        lot = securities.buy(state, "treasury", 10.0, 1_000_000_00, "AFS")
        econ = state["economy"]
        econ["long_rate"] += 0.02   # +200bp long end
        from bankgame.sim.economy import _build_curve
        econ["curve"] = _build_curve(econ)
        px = securities.price_lot(econ, lot)
        self.assertLess(px, lot["par"] * 0.93)   # ~7yr duration * 2% ~ -14%
        # and AOCI takes the hit for AFS
        securities.revalue(state)
        aoci = -state["bank"]["ledger"]["balances"]["3200"]
        self.assertLess(aoci, 0)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_htm_sale_taints_book(self):
        state = self.state
        book = state["bank"]["securities"]
        htm = [l for l in book["lots"] if l["cls"] == "HTM"]
        self.assertTrue(htm)
        res = securities.sell(state, htm[0]["id"])
        self.assertIsInstance(res, dict)
        self.assertTrue(book["htm_tainted"])
        self.assertFalse(any(l["cls"] == "HTM" for l in book["lots"]))
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        htm_book = sum(l["book"] for l in book["lots"] if l["cls"] == "HTM")
        self.assertEqual(state["bank"]["ledger"]["balances"]["1210"], htm_book)
        self.assertGreaterEqual(state["bank"]["ledger"]["balances"]["1210"], 0)

    def test_yield_curve_interpolation(self):
        econ = self.state["economy"]
        y2 = yield_at(econ, 2.0)
        y3 = yield_at(econ, 3.0)
        y25 = yield_at(econ, 2.5)
        self.assertTrue(min(y2, y3) <= y25 <= max(y2, y3))

    def test_cd_repricing_blends_rates(self):
        pool = {"balance": 1_200_000_00, "accounts": 40, "wavg_rate": 0.05,
                "accrued": 0}

        class FakeRng:
            def chance(self, p):
                return False
        from bankgame.sim.deposits import _cd_flow
        # market fell to 3%: matured slice reprices down, blend must drop
        _cd_flow(pool, "cd_1y", 0.03, 0.03, pool["balance"], 0.12, FakeRng())
        self.assertLess(pool["wavg_rate"], 0.05)
        self.assertGreater(pool["wavg_rate"], 0.029)


if __name__ == "__main__":
    unittest.main()
