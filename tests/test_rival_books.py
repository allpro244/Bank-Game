"""Rival call-report books: identity, published scalars, determinism."""

import json
import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import competitors as C
from bankgame.sim import engine
from bankgame.server import Game


def _run(state, days):
    for _ in range(days):
        engine.step_day(state)
        state["events"]["pending"].clear()


class TestRivalBooks(unittest.TestCase):
    def test_every_rival_balances_and_ties_published(self):
        state = new_game("Books", seed=17)
        banks = state["competitors"]["banks"]
        self.assertGreaterEqual(len(banks), 12)
        for b in banks:
            books = C.rival_books(state, b["id"])
            self.assertIsNotNone(books, b["id"])
            bs = books["balance_sheet"]
            self.assertEqual(bs["total_assets"],
                             bs["total_liabilities"] + bs["total_equity"],
                             b["name"])
            self.assertEqual(bs["total_assets"], b["assets"])
            self.assertEqual(sum(v for _, v in bs["assets"]
                                 if _ not in ("Loans, gross",
                                              "  less: allowance for credit losses")),
                             bs["total_assets"])
            self.assertEqual(sum(v for lab, v in bs["liabilities"]
                                 if lab != "Total deposits"),
                             bs["total_liabilities"])
            self.assertEqual(sum(v for _, v in bs["equity"]),
                             bs["total_equity"])
            self.assertEqual(bs["total_equity"],
                             int(round(b["assets"] * b["equity_ratio"])))
            self.assertEqual(books["income_ttm"]["net_income"],
                             int(round(b["assets"] * b["roa"])))
            self.assertEqual(books["income_ttm"]["nii"],
                             int(round(b["assets"] * b["nim"])))
            self.assertEqual(books["quality"]["npa"],
                             int(round(b["assets"] * b["npa_ratio"])))
            ni_line = dict(books["income_ttm"]["lines"])["NET INCOME"]
            self.assertEqual(ni_line, books["income_ttm"]["net_income"])
            # P&L identity
            lines = dict(books["income_ttm"]["lines"])
            self.assertEqual(
                lines["Interest income"] + lines["Interest expense"],
                lines["NET INTEREST INCOME"])
            rebuilt = (lines["NET INTEREST INCOME"]
                       + lines["Provision for credit losses"]
                       + lines["Noninterest income"]
                       + lines["Securities gains (losses)"]
                       + lines["Noninterest expense"]
                       + lines["Income tax"])
            self.assertEqual(rebuilt, lines["PRETAX INCOME"] + lines["Income tax"])
            self.assertEqual(lines["PRETAX INCOME"] + lines["Income tax"],
                             lines["NET INCOME"])
            if books["income_ttm"]["nii"] + books["income_ttm"]["fee_income"]:
                self.assertAlmostEqual(
                    books["ratios"]["efficiency"], b["efficiency"], places=4)
            self.assertEqual(sum(books["mix"]["loans"].values()),
                             dict(bs["assets"])["Loans, gross"])
            self.assertEqual(sum(books["mix"]["deposits"].values()),
                             dict(bs["liabilities"])["Total deposits"])
            self.assertTrue(books["markets"])
            self.assertIn("deposit", books["posted_rates"])
            self.assertIn("loan", books["posted_rates"])

    def test_determinism_and_no_state_mutation(self):
        state = new_game("Det", seed=99)
        before = json.dumps(state, sort_keys=True)
        a = C.rival_books(state, "cb0")
        b = C.rival_books(state, "cb0")
        after = json.dumps(state, sort_keys=True)
        self.assertEqual(before, after)
        self.assertEqual(a, b)
        other = new_game("Det", seed=99)
        self.assertEqual(C.rival_books(other, "cb0"), a)
        different = new_game("Det", seed=100)
        self.assertNotEqual(
            C.rival_books(different, "cb0")["balance_sheet"]["assets"],
            a["balance_sheet"]["assets"])

    def test_unknown_id_is_none(self):
        state = new_game("X", seed=1)
        self.assertIsNone(C.rival_books(state, "nope"))
        self.assertIsNone(C.rival_books(state, ""))

    def test_failed_rival_still_has_last_books(self):
        state = new_game("Fail", seed=3)
        dead = state["competitors"]["banks"][0]
        dead["alive"] = False
        books = C.rival_books(state, dead["id"])
        self.assertIsNotNone(books)
        self.assertFalse(books["alive"])
        self.assertEqual(
            books["balance_sheet"]["total_assets"],
            books["balance_sheet"]["total_liabilities"]
            + books["balance_sheet"]["total_equity"])

    def test_strategy_tilts_the_mix(self):
        state = new_game("Tilt", seed=5)
        by_strat = {b["strategy"]: b for b in state["competitors"]["banks"]}
        agr = C.rival_books(state, by_strat["aggressive_lender"]["id"])
        con = C.rival_books(state, by_strat["conservative"]["id"])
        dig = C.rival_books(state, by_strat["digital"]["id"])
        self.assertGreater(agr["ratios"]["ldr"], con["ratios"]["ldr"])
        agr_sec = (dict(agr["balance_sheet"]["assets"])
                   ["Securities held-to-maturity (amortized cost)"])
        con_sec = (dict(con["balance_sheet"]["assets"])
                   ["Securities held-to-maturity (amortized cost)"])
        self.assertGreater(con_sec / con["balance_sheet"]["total_assets"],
                           agr_sec / agr["balance_sheet"]["total_assets"])
        dig_prem = dict(dig["balance_sheet"]["assets"])["Premises and equipment"]
        con_prem = dict(con["balance_sheet"]["assets"])["Premises and equipment"]
        self.assertLess(dig_prem / dig["balance_sheet"]["total_assets"],
                        con_prem / con["balance_sheet"]["total_assets"])
        self.assertGreater(dig["ratios"]["uninsured"], con["ratios"]["uninsured"])

    def test_books_follow_updated_scalars(self):
        state = new_game("Later", seed=8)
        before = C.rival_books(state, "cb6")
        _run(state, 80)
        after = C.rival_books(state, "cb6")
        live = C.find_rival(state, "cb6")
        self.assertEqual(after["balance_sheet"]["total_assets"], live["assets"])
        self.assertEqual(
            after["balance_sheet"]["total_assets"],
            after["balance_sheet"]["total_liabilities"]
            + after["balance_sheet"]["total_equity"])
        # Size almost certainly moved after ~4 months
        self.assertNotEqual(before["balance_sheet"]["total_assets"],
                            after["balance_sheet"]["total_assets"])

    def test_api_section_rival(self):
        g = Game()
        g.state = new_game("API", seed=1)
        mk = g.section("markets", {})
        self.assertTrue(all("id" in b for b in mk["competitors"]))
        self.assertTrue(all("id" in b for b in mk["peers"]))
        first = mk["competitors"][0]["id"]
        books = g.section("rival", {"id": [first]})
        self.assertNotIn("error", books)
        self.assertEqual(books["id"], first)
        self.assertEqual(
            books["balance_sheet"]["total_assets"],
            books["balance_sheet"]["total_liabilities"]
            + books["balance_sheet"]["total_equity"])
        self.assertEqual(g.section("rival", {"id": ["ghost"]}),
                         {"error": "unknown rival"})


if __name__ == "__main__":
    unittest.main()
