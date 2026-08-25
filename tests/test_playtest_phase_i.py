"""Phase I playtest pass: books, industry, growth, clock."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import funding as FUND
from bankgame.sim import fraud as FR
from bankgame.sim import crises as CRI
from bankgame.sim import deposits as DEP
from bankgame.sim import operations as OPS
from bankgame.sim import loans as LN
from bankgame.sim import competitors as COMP
from bankgame.sim import goals as GOALS
from bankgame.sim import regulation as REG
from bankgame.sim import rng as R


def _passive(state, days):
    state["bank"]["loans"]["queue"].clear()
    state["bank"]["funding"]["overnight_policy"] = "auto"
    for _ in range(days):
        engine.step_day(state)
        state["events"]["pending"].clear()
        state["bank"]["loans"]["queue"].clear()


class TestI6SpendAndCrash(unittest.TestCase):
    def test_bsa_and_fraud_spend_hit_the_ledger(self):
        state = new_game("Spend", seed=11)
        state["bank"]["loans"]["queue"].clear()
        bsa = state["regulation"]["bsa"]["program_spend"]
        fr = state["bank"]["fraud"]["prevention_spend"]
        self.assertGreater(bsa, 0)
        self.assertGreater(fr, 0)
        control = new_game("Spend0", seed=11)
        control["regulation"]["bsa"]["program_spend"] = 0
        control["bank"]["fraud"]["prevention_spend"] = 0
        state["regulation"]["bsa"]["program_spend"] = 6_000_00
        state["bank"]["fraud"]["prevention_spend"] = 6_000_00
        _passive(state, 32)
        _passive(control, 32)
        ni_pay = state["metrics"][-1]["net_income_ttm"]
        ni_free = control["metrics"][-1]["net_income_ttm"]
        self.assertLess(ni_pay, ni_free)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_negative_assets_do_not_crash_fraud_spawn(self):
        state = new_game("Neg", seed=8)
        state["bank"]["cached_assets"] = -5_000_000_00
        rng = R.Rng(R.make_streams(8, ["fraud"])["fraud"])
        ev = FR._spawn_case(state, rng)
        self.assertIn("case_id", ev)
        self.assertGreater(ev.get("case_id", 0) or 1, 0)


class TestI4CapitalAndOvernight(unittest.TestCase):
    def test_raise_preview_matches_post(self):
        state = new_game("Raise", seed=5)
        terms = FUND.preview_raise_common(state, 2_000_000_00)
        self.assertIsInstance(terms, dict)
        self.assertGreaterEqual(terms["price_to_book"], 1.0)
        res = FUND.raise_common(state, 2_000_000_00)
        self.assertEqual(res["price_to_book"], terms["price_to_book"])
        self.assertEqual(res["shares_issued"], terms["shares_issued"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_red_roe_does_not_clear_at_fire_sale(self):
        state = new_game("Fire", seed=5)
        state["bank"]["roe_ttm"] = -0.40
        state["regulation"]["camels"]["composite"] = 4
        # earnings not ready → through-cycle floor
        terms = FUND.preview_raise_common(state, 1_000_000_00)
        self.assertGreaterEqual(terms["price_to_book"], 0.70)

    def test_auto_passive_three_years_avoids_the_window(self):
        uses = []
        for seed in (7, 19, 41, 88):
            state = new_game("Auto%d" % seed, seed=seed)
            _passive(state, 756)
            uses.append(state["bank"]["funding"].get("discount_window_uses", 0))
            self.assertIsNone(state["game_over"])
        self.assertEqual(max(uses), 0, "auto window uses %s" % uses)


class TestI5RunAndExam(unittest.TestCase):
    def test_run_status_payload(self):
        state = new_game("Run", seed=2)
        st = CRI.run_status(state)
        self.assertFalse(st["run"])
        state["crisis"]["rumor"] = 0.6
        state["crisis"]["run_active"] = True
        state["crisis"]["run_days"] = 3
        state["crisis"]["total_run_outflow"] = 1_000_000_00
        st = CRI.run_status(state)
        self.assertTrue(st["run"])
        self.assertTrue(st["cause"])

    def test_exam_recovery_names_the_floor(self):
        state = new_game("Exam", seed=2)
        state["regulation"]["camels"] = {
            "composite": 4, "C": 2, "A": 2, "M": 2, "E": 2, "L": 5, "S": 2}
        adv = REG.exam_recovery_advice(state)
        self.assertEqual(adv["floor"], "L")
        self.assertTrue(adv["actions"])


class TestI2Industry(unittest.TestCase):
    def test_idle_world_stays_populated(self):
        state = new_game("World", seed=7)
        state["bank"]["loans"]["queue"].clear()
        for _ in range(240):  # 20 years of month-steps via day loop is slow;
            # step the rival engine directly — same stream as the month close.
            COMP.step_month(state, engine._rng(state, "comp"))
            state["economy"]["months"] += 1
        living = COMP.living_banks(state["competitors"])
        self.assertGreaterEqual(len(living), 8, "living %d" % len(living))

    def test_empire_does_not_compound_at_nine_percent(self):
        state = new_game("Emp", seed=7)
        empire = next(b for b in state["competitors"]["banks"]
                      if "Empire" in b["name"])
        start = empire["assets"]
        for _ in range(120):
            COMP.step_month(state, engine._rng(state, "comp"))
            state["economy"]["months"] += 1
        end = next(b for b in state["competitors"]["banks"]
                   if "Empire" in b["name"])["assets"]
        # 10 years: 9.3%/yr would be ~2.4×. Cap well under 5%/yr (~1.63×).
        self.assertLess(end / start, 1.70)

    def test_empty_field_is_not_a_world_win(self):
        state = new_game("Empty", seed=8, goal="world")
        for b in state["competitors"]["banks"]:
            b["alive"] = False
        race = GOALS.world_race(state)
        self.assertTrue(race["empty_field"])
        self.assertFalse(race["beats_rivals"])
        p = GOALS.progress(state)
        self.assertIn("empty", p["text"].lower())
        self.assertIsNone(GOALS.check_win(state))


class TestI3Growth(unittest.TestCase):
    def test_second_office_in_home_town(self):
        state = new_game("Two", seed=4)
        engine.perform_action(state, "raise_common", {"amount": 3_000_000_00})
        res = engine.perform_action(state, "open_branch", {"market": "caprock"})
        self.assertNotIsInstance(res, str)
        n = sum(1 for b in state["bank"]["ops"]["branches"] if b.get("open"))
        self.assertEqual(n, 2)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_dallas_year1_gather_is_a_trade_area(self):
        state = new_game("Dal", seed=11)
        g = DEP.year1_gather_estimate(state, "dallas")
        self.assertGreater(g, 2_000_000_00)
        self.assertLess(g, 80_000_000_00)

    def test_hire_lender_preview_is_ni_positive(self):
        state = new_game("Hire", seed=1)
        prev = LN.preview_hire_lender(state)
        self.assertTrue(prev["positive"])

    def test_digital_scales_down_for_a_20m_bank(self):
        sticker = OPS.digital_upgrade_cost(0)
        scaled = OPS.digital_upgrade_cost(0, 20_000_000_00)
        self.assertLess(scaled, sticker)
        self.assertGreaterEqual(scaled, 250_000_00)
        state = new_game("Dig", seed=1)
        p = OPS.preview_digital(state)
        self.assertIn("too_big", p)


class TestI1PlayUntil(unittest.TestCase):
    def test_box_approves_a_tier_and_play_until_crosses_the_memo(self):
        state = new_game("Box", seed=2)
        self.assertTrue(state["bank"]["loans"]["queue"])
        app = state["bank"]["loans"]["queue"][0]
        app["tier"] = "A"
        app["amount"] = 400_000_00
        box = LN.credit_box(state)
        box["enabled"] = True
        box["max_hold"] = 2_000_000_00
        n = LN.apply_credit_box(state)
        self.assertGreaterEqual(n, 1)
        self.assertFalse(state["bank"]["loans"]["queue"])
        res = engine.advance(state, "until", max_days=90)
        self.assertGreater(res["days"], 0)
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_play_until_stops_on_a_memo_outside_the_box(self):
        state = new_game("Stop", seed=2)
        box = LN.credit_box(state)
        box["enabled"] = True
        # Seeded first credit is $620k B-tier — inside default box if we
        # shrink the hold so it is outside.
        box["max_hold"] = 100_000_00
        box["participate_over"] = False
        res = engine.advance(state, "until", max_days=20)
        self.assertEqual(res["days"], 0)
        self.assertEqual(res.get("stopped"), "credit")

    def test_box_declines_d_tier_and_clock_continues(self):
        state = new_game("Dtier", seed=2)
        state["bank"]["loans"]["queue"].clear()
        state["events"]["pending"].clear()
        box = LN.credit_box(state)
        box["enabled"] = True
        app = {
            "id": 99, "name": "Dusty D", "product": "ci", "market": "caprock",
            "tier": "D", "amount": 400_000_00, "rate": 0.09,
            "days_left": 30, "memo": "test",
        }
        state["bank"]["loans"]["queue"].append(app)
        n = LN.apply_credit_box(state)
        self.assertEqual(n, 1)
        self.assertFalse(state["bank"]["loans"]["queue"])
        res = engine.advance(state, "until", max_days=10)
        self.assertGreater(res["days"], 0)
        self.assertNotEqual(res.get("stopped"), "credit")


class TestI5ExamMoves(unittest.TestCase):
    def test_l_only_4_recovers_after_window_is_cleared(self):
        state = new_game("L4", seed=3)
        state["bank"]["funding"]["discount_window_uses"] = 10
        REG.run_exam(state, engine._rng(state, "misc"))
        self.assertGreaterEqual(state["regulation"]["camels"]["L"], 4)
        self.assertGreaterEqual(state["regulation"]["camels"]["composite"], 3)
        state["bank"]["funding"]["discount_window_uses"] = 0
        REG.run_exam(state, engine._rng(state, "misc"))
        self.assertLessEqual(state["regulation"]["camels"]["L"], 2)
        self.assertLessEqual(state["regulation"]["camels"]["composite"], 3)


class TestI2DealWeight(unittest.TestCase):
    def test_community_bank_is_not_offered_a_whale(self):
        state = new_game("Small", seed=9)
        # Force many draws; community-era deals stay 10–35% of assets.
        seen = []
        rng = engine._rng(state, "event")
        for _ in range(400):
            for ev in engine._ma_opportunities(state, rng):
                if ev.get("type") == "bank_for_sale":
                    seen.append(ev["deal"]["assets"])
        me = state["bank"]["cached_assets"]
        self.assertTrue(seen, "expected at least one private deal in 400 draws")
        self.assertLessEqual(max(seen) / me, 0.36)

    def test_regional_may_see_larger_than_self(self):
        state = new_game("Reg", seed=9)
        state["bank"]["cached_assets"] = 2_500_000_000_00
        seen = []
        rng = engine._rng(state, "event")
        for _ in range(400):
            for ev in engine._ma_opportunities(state, rng):
                if ev.get("type") == "bank_for_sale":
                    seen.append(ev["deal"]["assets"])
        self.assertTrue(seen)
        self.assertGreater(max(seen), 2_500_000_000_00 * 0.9)


class TestI3SecondOfficeGather(unittest.TestCase):
    def test_second_caprock_office_gathers_less_than_the_book_already_there(self):
        state = new_game("Inc", seed=4)
        already = DEP.market_deposits(state, "caprock")
        inc = DEP.year1_gather_estimate(state, "caprock")
        self.assertGreater(already, 0)
        self.assertGreater(inc, 0)
        self.assertLess(inc, already)


class TestI7AdvisorGates(unittest.TestCase):
    def test_hire_lender_card_stays_off_when_ni_is_red(self):
        from bankgame.sim import advisor
        state = new_game("NoHire", seed=1)
        state["bank"]["ops"]["staff"]["lenders"]["salary"] = 5_000_000_00
        # Force utilization high enough that the card would otherwise fire.
        state["bank"]["loans"]["stats"]["originated_mtd"] = LN.lender_capacity(state)
        cards = advisor.cards(state)
        self.assertNotIn("hire_lender", [c["id"] for c in cards])
        self.assertFalse(LN.preview_hire_lender(state)["positive"])

    def test_second_county_card_never_names_dallas(self):
        from bankgame.sim import advisor
        state = new_game("Peer", seed=1)
        # Fake a ready year so the card is allowed to consider a county.
        state["metrics"] = [{"earnings_ready": True, "roa": 0.01, "nim": 0.03,
                             "efficiency": 0.55, "npa_ratio": 0.005,
                             "cet1_ratio": 0.12, "liquidity_ratio": 0.15,
                             "loan_to_deposit": 0.75, "equity": 3_000_000_00,
                             "assets": 22_000_000_00, "deposits": 18_000_000_00,
                             "roe": 0.08}]
        engine.perform_action(state, "raise_common", {"amount": 5_000_000_00})
        cards = advisor.cards(state)
        for c in cards:
            for a in c.get("actions") or []:
                for s in a.get("steps") or []:
                    if s.get("kind") == "action" and s.get("action") == "open_branch":
                        self.assertNotEqual((s.get("payload") or {}).get("market"),
                                            "dallas")


class TestCamelsOrderLoop(unittest.TestCase):
    def test_first_exam_is_not_a_four(self):
        state = new_game("Exam1", seed=11)
        REG.run_exam(state, engine._rng(state, "misc"))
        cam = state["regulation"]["camels"]
        self.assertLessEqual(cam["M"], 3)
        self.assertLessEqual(cam["composite"], 3)

    def test_mou_does_not_grade_management(self):
        a = new_game("Mou", seed=3)
        b = new_game("Bare", seed=3)
        a["bank"]["roa_ttm"] = b["bank"]["roa_ttm"] = 0.011
        a["metrics"] = b["metrics"] = [{
            "earnings_ready": True, "roa": 0.011, "roe": 0.09,
            "equity": 3_000_000_00, "assets": 22_000_000_00,
        }]
        a["regulation"]["orders"] = ["Memorandum of understanding"]
        REG.run_exam(a, engine._rng(a, "misc"))
        REG.run_exam(b, engine._rng(b, "misc"))
        self.assertEqual(a["regulation"]["camels"]["M"],
                         b["regulation"]["camels"]["M"])

    def test_clean_books_escape_a_three(self):
        """C/A/L/S fortress + MOU already on the wall → next exam can be a 2."""
        state = new_game("Escape", seed=3)
        state["bank"]["roa_ttm"] = 0.012
        state["metrics"] = [{"earnings_ready": True, "roa": 0.012, "roe": 0.10,
                             "equity": 3_000_000_00, "assets": 22_000_000_00}]
        state["regulation"]["orders"] = ["Memorandum of understanding"]
        REG.run_exam(state, engine._rng(state, "misc"))
        self.assertLessEqual(state["regulation"]["camels"]["composite"], 2)
        self.assertNotIn("Memorandum of understanding",
                         state["regulation"]["orders"])

    def test_play_until_does_not_freeze_on_a_four(self):
        state = new_game("Walk", seed=2)
        state["bank"]["loans"]["queue"].clear()
        state["events"]["pending"].clear()
        state["regulation"]["camels"]["composite"] = 4
        self.assertIsNone(engine.interrupt_reason(state))
        res = engine.advance(state, "until", max_days=5)
        self.assertGreater(res["days"], 0)

    def test_mou_card_says_you_can_grow(self):
        from bankgame.sim import advisor
        state = new_game("MouC", seed=1)
        state["regulation"]["camels"]["composite"] = 3
        state["regulation"]["orders"] = ["Memorandum of understanding"]
        cards = advisor.cards(state)
        self.assertTrue(any(c["id"] == "camels_repair" for c in cards))
        blob = " ".join(c["text"] for c in cards if c["id"] == "camels_repair").lower()
        self.assertIn("grow", blob)


class TestPlaytestLeftovers(unittest.TestCase):
    def test_play_until_does_not_freeze_on_a_run(self):
        state = new_game("RunClk", seed=2)
        state["bank"]["loans"]["queue"].clear()
        state["events"]["pending"].clear()
        state["crisis"]["run_active"] = True
        state["crisis"]["rumor"] = 0.60
        self.assertIsNone(engine.interrupt_reason(state))
        res = engine.advance(state, "until", max_days=3)
        self.assertGreater(res["days"], 0)

    def test_lenders_scale_with_franchise_size(self):
        state = new_game("Book", seed=1)
        opening = LN.lender_capacity(state)
        self.assertTrue(LN.preview_hire_lender(state)["positive"])
        state["bank"]["cached_assets"] = 10_000_000_000_00
        big = LN.lender_capacity(state)
        self.assertGreater(big, opening * 8)
        self.assertLess(big, opening * 16)

    def test_hire_lender_card_fires_when_ldr_is_stuck(self):
        from bankgame.sim import advisor
        state = new_game("Stuck", seed=1)
        state["bank"]["cached_assets"] = 100_000_000_00
        state["metrics"] = [{"loan_to_deposit": 0.29, "earnings_ready": True,
                             "roa": 0.01, "equity": 20_000_000_00,
                             "assets": 100_000_000_00}]
        state["bank"]["loans"]["stats"]["originated_mtd"] = 0
        card = advisor._r_hire_lender(state)
        self.assertIsNotNone(card)
        self.assertIn("deposit", card["text"].lower())

    def test_capital_repair_cools_down_after_a_raise(self):
        from bankgame.sim import advisor
        state = new_game("RaiseSpam", seed=5)
        state["regulation"]["pca"] = "adequate"
        self.assertIn("capital_repair", [c["id"] for c in advisor.cards(state)])
        engine.perform_action(state, "raise_common", {"amount": 1_000_000_00})
        self.assertNotIn("capital_repair", [c["id"] for c in advisor.cards(state)])

    def test_capital_repair_honors_dismiss(self):
        from bankgame.sim import advisor
        state = new_game("RaiseD", seed=5)
        state["regulation"]["pca"] = "adequate"
        self.assertIn("capital_repair", [c["id"] for c in advisor.cards(state)])
        advisor.dismiss(state, "capital_repair")
        self.assertNotIn("capital_repair", [c["id"] for c in advisor.cards(state)])


if __name__ == "__main__":
    unittest.main()
