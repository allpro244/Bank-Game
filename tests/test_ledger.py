"""Accounting invariants: the tests the owner can't run by eye."""

import unittest

from bankgame.sim import ledger as L


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.led = L.new_ledger()

    def test_balanced_posting(self):
        L.post(self.led, "2000-01-03", "seed cash",
               [["1000", 100_00, 0], ["3000", 0, 100_00]])
        self.assertEqual(L.trial_balance(self.led), 0)
        self.assertEqual(L.display_balance(self.led, "1000"), 100_00)
        self.assertEqual(L.display_balance(self.led, "3000"), 100_00)

    def test_unbalanced_posting_rejected(self):
        with self.assertRaises(L.LedgerError):
            L.post(self.led, "2000-01-03", "bad",
                   [["1000", 100_00, 0], ["3000", 0, 99_00]])
        # nothing partially applied
        self.assertEqual(L.trial_balance(self.led), 0)
        self.assertEqual(self.led["balances"]["1000"], 0)

    def test_non_integer_rejected(self):
        with self.assertRaises(L.LedgerError):
            L.post(self.led, "2000-01-03", "float money",
                   [["1000", 100.5, 0], ["3000", 0, 100.5]])

    def test_negative_amount_rejected(self):
        with self.assertRaises(L.LedgerError):
            L.post(self.led, "2000-01-03", "negative",
                   [["1000", -5, 0], ["3000", 0, -5]])

    def test_unknown_account_rejected(self):
        with self.assertRaises(L.LedgerError):
            L.post(self.led, "2000-01-03", "ghost",
                   [["9999", 5, 0], ["3000", 0, 5]])

    def test_trial_balance_many_postings(self):
        L.post(self.led, "2000-01-03", "open",
               [["1000", 1_000_000_00, 0], ["3000", 0, 1_000_000_00]])
        L.post(self.led, "2000-01-04", "loan",
               [["1300", 600_000_00, 0], ["1000", 0, 600_000_00]])
        L.post(self.led, "2000-01-05", "deposit in",
               [["1000", 250_000_00, 0], ["2000", 0, 250_000_00]])
        L.post(self.led, "2000-01-31", "interest accrual",
               [["1400", 4_931_51, 0], ["4000", 0, 4_931_51]])
        self.assertEqual(L.trial_balance(self.led), 0)
        self.assertEqual(L.total_assets(self.led),
                         1_000_000_00 - 600_000_00 + 250_000_00
                         + 600_000_00 + 4_931_51)

    def test_month_close_moves_pl_to_retained(self):
        L.post(self.led, "2000-01-03", "open",
               [["1000", 1_000_00, 0], ["3000", 0, 1_000_00]])
        L.post(self.led, "2000-01-10", "income",
               [["1000", 500_00, 0], ["4000", 0, 500_00]])
        L.post(self.led, "2000-01-15", "expense",
               [["5100", 200_00, 0], ["1000", 0, 200_00]])
        self.assertEqual(L.net_income_open(self.led), 300_00)
        net = L.close_month(self.led, "2000-01", "2000-02-01")
        self.assertEqual(net, 300_00)
        self.assertEqual(L.net_income_open(self.led), 0)
        self.assertEqual(L.display_balance(self.led, "3100"), 300_00)
        self.assertEqual(L.trial_balance(self.led), 0)
        self.assertEqual(self.led["months"][-1]["net_income"], 300_00)
        self.assertEqual(self.led["months"][-1]["pl"]["4000"], 500_00)
        self.assertEqual(self.led["months"][-1]["pl"]["5100"], 200_00)

    def test_equity_includes_open_income(self):
        L.post(self.led, "2000-01-03", "open",
               [["1000", 1_000_00, 0], ["3000", 0, 1_000_00]])
        L.post(self.led, "2000-01-10", "income",
               [["1000", 77_00, 0], ["4000", 0, 77_00]])
        self.assertEqual(L.total_equity(self.led), 1_077_00)
        self.assertEqual(L.total_assets(self.led),
                         L.total_liabilities(self.led) + L.total_equity(self.led))

    def test_audit_flags_problems(self):
        # force a broken balance directly (bypassing post)
        self.led["balances"]["1000"] = 5
        problems = L.audit(self.led)
        self.assertTrue(any("TRIAL BALANCE" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
