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


def _park_cash_in_premises(state, target_ratio=0.05):
    """Make liquid/assets fail the 10% MRA without breaking the books."""
    from bankgame.sim import regulation as REG
    bank = state["bank"]
    led = bank["ledger"]
    date = state["time"]["date"]
    for lot in bank["securities"]["lots"]:
        if lot["cls"] == "AFS":
            lot["cls"] = "HTM"
    afs = led["balances"]["1200"]
    if afs > 0:
        L.post(led, date, "test AFS→HTM",
               [["1210", afs, 0], ["1200", 0, afs]], tag="test")
    assets = L.total_assets(led)
    want = int(assets * target_ratio)
    liquid = (led["balances"]["1000"] + led["balances"]["1010"]
              + led["balances"]["1100"])
    dump = max(0, liquid - want)
    for acct in ("1000", "1010", "1100"):
        if dump <= 0:
            break
        take = min(dump, led["balances"][acct])
        if take > 0:
            L.post(led, date, "test drain " + acct,
                   [["1500", take, 0], [acct, 0, take]], tag="test")
            dump -= take
    lr, _ = REG.liquidity_ratio(state)
    return lr


class TestExaminerMRAs(unittest.TestCase):
    def test_a_two_writes_no_mra(self):
        from bankgame.sim import regulation as REG
        state = new_game("Clean", seed=3)
        issued = REG.issue_mras(
            state, {"C": 2, "A": 2, "M": 2, "E": 2, "L": 2, "S": 2}, 2)
        self.assertEqual(issued, [])
        self.assertFalse(REG.live_mras(state["regulation"]))

    def test_first_exam_that_is_a_two_writes_none(self):
        from bankgame.sim import regulation as REG
        state = new_game("Exam2", seed=3)
        state["bank"]["roa_ttm"] = 0.012
        state["metrics"] = [{"earnings_ready": True, "roa": 0.012, "roe": 0.10,
                             "equity": 3_000_000_00, "assets": 22_000_000_00}]
        REG.run_exam(state, engine._rng(state, "misc"))
        self.assertLessEqual(state["regulation"]["camels"]["composite"], 2)
        self.assertFalse(REG.live_mras(state["regulation"]))

    def test_thin_cash_on_a_three_writes_a_liquidity_mra(self):
        from bankgame.sim import regulation as REG
        state = new_game("MRA", seed=3)
        lr = _park_cash_in_premises(state, 0.05)
        self.assertLess(lr, 0.10)
        issued = REG.issue_mras(
            state, {"C": 2, "A": 2, "M": 2, "E": 2, "L": 3, "S": 2}, 3)
        self.assertTrue(issued)
        self.assertEqual(issued[0]["kind"], "liquidity")
        self.assertEqual(issued[0]["status"], "open")
        self.assertIn("10", issued[0]["text"])

    def test_missed_mra_grades_management_once(self):
        from copy import deepcopy
        from bankgame.sim import regulation as REG
        state = new_game("Miss", seed=3)
        _park_cash_in_premises(state, 0.04)
        REG.issue_mras(
            state, {"C": 2, "A": 2, "M": 2, "E": 2, "L": 3, "S": 2}, 3)
        twin = deepcopy(state)
        twin["regulation"]["mras"] = []
        state["bank"]["funding"]["discount_window_uses"] = 3
        twin["bank"]["funding"]["discount_window_uses"] = 3
        REG.run_exam(state, engine._rng(state, "misc"))
        REG.run_exam(twin, engine._rng(twin, "misc"))
        self.assertTrue(REG.missed_mra_outstanding(state["regulation"]))
        self.assertEqual(state["regulation"]["camels"]["M"],
                         twin["regulation"]["camels"]["M"] + 1)

    def test_meeting_an_mra_clears_it(self):
        from bankgame.sim import regulation as REG
        state = new_game("Meet", seed=3)
        _park_cash_in_premises(state, 0.04)
        REG.issue_mras(
            state, {"C": 2, "A": 2, "M": 2, "E": 2, "L": 3, "S": 2}, 3)
        just = REG.grade_open_mras(state)
        self.assertEqual(just[0]["status"], "missed")
        engine.perform_action(state, "raise_common", {"amount": 2_000_000_00})
        # Raised cash sits in the vault — liquid again.
        just = REG.grade_open_mras(state)
        self.assertEqual(just[0]["status"], "met")
        self.assertFalse(REG.missed_mra_outstanding(state["regulation"]))

    def test_mra_card_names_the_deadline(self):
        from bankgame.sim import regulation as REG
        state = new_game("Card", seed=1)
        REG.issue_mras(
            state, {"C": 2, "A": 2, "M": 2, "E": 2, "L": 3, "S": 2}, 3)
        # Liquidity already >10% on a fresh book, so force an open item.
        if not REG.live_mras(state["regulation"]):
            state["regulation"]["mras"].append({
                "id": 1, "kind": "liquidity", "metric": "liquidity_ratio",
                "target": 0.10, "op": "gte", "status": "open",
                "text": "Raise liquid assets above 10 percent.",
                "owner": "Cash must be at least 10% of the book.",
            })
        state["regulation"]["months_to_exam"] = 2
        card = advisor._r_mra_due(state)
        self.assertIsNotNone(card)
        self.assertEqual(card["id"], "mra_due")


class TestEVE(unittest.TestCase):
    def test_long_bonds_hurt_more_when_rates_jump(self):
        from bankgame.sim import securities as SEC
        state = new_game("EVE", seed=5)
        short = SEC.eve_report(state)
        s200 = next(x for x in short["shocks"] if x["bp"] == 200)
        engine.perform_action(state, "raise_common", {"amount": 6_000_000_00})
        engine.perform_action(state, "buy_security", {
            "type": "treasury", "tenor": 30.0, "par": 5_000_000_00, "cls": "AFS"})
        long = SEC.eve_report(state)
        l200 = next(x for x in long["shocks"] if x["bp"] == 200)
        l100 = next(x for x in long["shocks"] if x["bp"] == 100)
        self.assertLess(l200["delta_eve"], s200["delta_eve"])
        self.assertLess(l200["delta_eve"], l100["delta_eve"])
        self.assertIn("2%", long["owner"])
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_pay_fixed_swap_dampens_a_rate_up_hit(self):
        from bankgame.sim import securities as SEC
        state = new_game("Hedge", seed=5)
        engine.perform_action(state, "raise_common", {"amount": 6_000_000_00})
        engine.perform_action(state, "buy_security", {
            "type": "treasury", "tenor": 30.0, "par": 5_000_000_00, "cls": "AFS"})
        before = next(x for x in SEC.eve_report(state)["shocks"] if x["bp"] == 200)
        SEC.add_hedge(state, "pay_fixed_swap", 5_000_000_00, 5.0)
        after = next(x for x in SEC.eve_report(state)["shocks"] if x["bp"] == 200)
        self.assertGreater(after["delta_eve"], before["delta_eve"])


class TestCreditBoxScale(unittest.TestCase):
    def test_card_recommends_a_raise_and_does_not_enable_the_box(self):
        state = new_game("Box", seed=1)
        state["bank"]["cached_assets"] = 90_000_000_00
        state["metrics"] = [{"earnings_ready": True, "roa": 0.011}]
        card = advisor._r_credit_box_scale(state)
        self.assertIsNotNone(card)
        step = card["actions"][0]["steps"][0]
        self.assertEqual(step["kind"], "set")
        self.assertEqual(step["path"], "loans.credit_box.max_hold")
        self.assertGreaterEqual(step["value"], 5_000_000_00)
        engine.set_policy(state, step["path"], step["value"])
        self.assertFalse(LN.credit_box(state)["enabled"])
        self.assertEqual(LN.credit_box(state)["max_hold"], step["value"])

    def test_card_stays_off_on_a_community_book(self):
        state = new_game("Small", seed=1)
        state["metrics"] = [{"earnings_ready": True, "roa": 0.011}]
        self.assertIsNone(advisor._r_credit_box_scale(state))


if __name__ == "__main__":
    unittest.main()
