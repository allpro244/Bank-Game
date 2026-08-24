"""E2/E3/E4: counter, participate, relationships, mortgage-sale preview."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import loans as LN
from bankgame.sim import advisor


class TestCredit(unittest.TestCase):
    def _app(self, state, amount=1_800_000_00, **kw):
        app = {
            "id": 900, "name": "Test Ranch Properties", "product": "cre",
            "market": "caprock", "amount": amount, "rate": 0.085,
            "tier": kw.get("tier", "B"), "dscr": kw.get("dscr", 1.25),
            "ltv": 0.70, "memo": "m", "days_left": 60, "term_m": 120,
            "can_fund": True,
        }
        app.update(kw)
        state["bank"]["loans"]["queue"].append(app)
        return app

    def test_counter_books_smaller_hold_at_higher_rate(self):
        state = new_game("Ctr", seed=4)
        state["bank"]["loans"]["queue"].clear()
        self._app(state, amount=1_000_000_00, tier="C", dscr=1.05)
        before = LN.total_loans(state["bank"]["loans"])
        # Force accept by using a C-tier thin DSCR (low walk chance) and retry
        accepted = False
        for seed in range(20):
            s = new_game("Ctr%d" % seed, seed=seed)
            s["bank"]["loans"]["queue"].clear()
            self._app(s, amount=1_000_000_00, tier="C", dscr=1.05)
            loans0 = LN.total_loans(s["bank"]["loans"])
            res = engine.perform_action(s, "counter_loan",
                                        {"app_id": 900, "extra_bp": 50,
                                         "hold_frac": 0.80})
            if res.get("accepted"):
                accepted = True
                self.assertLess(LN.total_loans(s["bank"]["loans"]) - loans0,
                                1_000_000_00)
                self.assertGreater(LN.total_loans(s["bank"]["loans"]), loans0)
                self.assertEqual(L.trial_balance(s["bank"]["ledger"]), 0)
                rel = LN._find_relationship(s["bank"]["loans"],
                                            "Test Ranch Properties")
                self.assertIsNotNone(rel)
                self.assertEqual(rel["status"], "performing")
                break
        self.assertTrue(accepted, "counter never accepted across 20 seeds")
        # original helper still works on a leftover state
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        _ = before

    def test_counter_reject_leaves_books_untouched(self):
        # A-tier + harsh terms walks often
        walked = False
        for seed in range(30):
            s = new_game("Walk%d" % seed, seed=seed)
            s["bank"]["loans"]["queue"].clear()
            self._app(s, amount=2_000_000_00, tier="A", dscr=1.7)
            loans0 = LN.total_loans(s["bank"]["loans"])
            res = engine.perform_action(s, "counter_loan",
                                        {"app_id": 900, "extra_bp": 150,
                                         "hold_frac": 0.45})
            if not res.get("accepted"):
                walked = True
                self.assertEqual(LN.total_loans(s["bank"]["loans"]), loans0)
                self.assertEqual(L.trial_balance(s["bank"]["ledger"]), 0)
                rel = LN._find_relationship(s["bank"]["loans"],
                                            "Test Ranch Properties")
                self.assertEqual(rel["status"], "declined")
                break
        self.assertTrue(walked, "harsh A-tier counter never walked")

    def test_participate_books_only_the_hold(self):
        state = new_game("Part", seed=9)
        state["bank"]["loans"]["queue"].clear()
        self._app(state, amount=1_000_000_00)
        loans0 = LN.total_loans(state["bank"]["loans"])
        res = engine.perform_action(state, "participate_loan",
                                    {"app_id": 900, "hold_frac": 0.40})
        added = LN.total_loans(state["bank"]["loans"]) - loans0
        self.assertEqual(added, res["hold"])
        self.assertEqual(res["hold"] + res["sold"], 1_000_000_00)
        self.assertLess(res["hold"], 1_000_000_00)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)
        rel = LN._find_relationship(state["bank"]["loans"],
                                    "Test Ranch Properties")
        self.assertEqual(rel["status"], "performing")

    def test_decline_is_remembered(self):
        state = new_game("Dec", seed=2)
        state["bank"]["loans"]["queue"].clear()
        self._app(state, tier="A")
        engine.perform_action(state, "decline_loan", {"app_id": 900})
        rel = LN._find_relationship(state["bank"]["loans"],
                                    "Test Ranch Properties")
        self.assertEqual(rel["status"], "declined")

    def test_seeded_culpepper_is_a_relationship(self):
        state = new_game("Cul", seed=1)
        rel = LN._find_relationship(state["bank"]["loans"],
                                    "Culpepper Cattle Co.")
        self.assertIsNotNone(rel)

    def test_applications_carry_structured_memo_fields(self):
        state = new_game("Memo", seed=1)
        app = state["bank"]["loans"]["queue"][0]
        self.assertEqual(app["name"], "Culpepper Cattle Co.")
        for k in ("why", "rival", "dscr_gloss", "ltv_gloss",
                  "relationship_line", "exception", "collateral"):
            self.assertTrue(app.get(k), "missing %s" % k)
        gen = LN._make_application(state, engine._rng(state, "credit"),
                                   "caprock", 200_000_00)
        if gen:
            for k in ("why", "rival", "dscr_gloss", "ltv_gloss", "collateral"):
                self.assertIn(k, gen)
            terms = LN.counter_terms(gen)
            self.assertLess(terms["amount"], gen["amount"])
            self.assertGreater(terms["rate"], gen["rate"])

    def test_mortgage_preview_and_advisor_card_is_a_legal_set(self):
        state = new_game("Mort", seed=5)
        prev = LN.mortgage_sale_preview(state, 0.50)
        self.assertIn("sold", prev)
        self.assertGreaterEqual(prev["sold"], 0)
        # Force the card's condition
        if state["metrics"]:
            state["metrics"][-1]["loan_to_deposit"] = 1.10
        else:
            state["metrics"].append({"loan_to_deposit": 1.10, "equity": 1,
                                     "assets": 1, "roe": 0.05})
        state["bank"]["loans"]["mortgage_sale_frac"] = 0.0
        card = advisor._r_sell_mortgages(state)
        if card:
            step = card["actions"][0]["steps"][0]
            self.assertEqual(step["kind"], "set")
            engine.set_policy(state, step["path"], step["value"])
            self.assertAlmostEqual(state["bank"]["loans"]["mortgage_sale_frac"],
                                   0.50)


if __name__ == "__main__":
    unittest.main()
