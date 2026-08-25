"""Loan stances write the old levers; the tape names every note."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine, ledger as L
from bankgame.sim import loans as LN
from bankgame.server import Game


class TestLoanStance(unittest.TestCase):
    def test_default_is_hold_without_a_cap(self):
        state = new_game("Hold0", seed=1)
        cfg = state["bank"]["loans"]
        self.assertEqual(LN.infer_stance(cfg, "cre"), "hold")
        self.assertEqual(cfg["spreads"]["cre"], 0)
        self.assertEqual(cfg["standards"]["cre"], 2)
        self.assertEqual(cfg["limits"]["cre"], 0)

    def test_preview_does_not_write(self):
        state = new_game("Prev", seed=1)
        before = (state["bank"]["loans"]["spreads"]["cre"],
                  state["bank"]["loans"]["standards"]["cre"],
                  state["bank"]["loans"]["limits"]["cre"])
        prev = LN.preview_loan_stance(state, "cre", "hunt")
        self.assertTrue(prev["can_apply"])
        self.assertIn("Hunt", prev["owner"])
        self.assertEqual(
            (state["bank"]["loans"]["spreads"]["cre"],
             state["bank"]["loans"]["standards"]["cre"],
             state["bank"]["loans"]["limits"]["cre"]),
            before)

    def test_hunt_writes_price_and_clears_cap(self):
        state = new_game("Hunt", seed=1)
        res = engine.perform_action(state, "set_loan_stance",
                                    {"product": "cre", "stance": "hunt"})
        cfg = state["bank"]["loans"]
        self.assertEqual(cfg["spreads"]["cre"], -75)
        self.assertEqual(cfg["standards"]["cre"], 0)
        self.assertEqual(cfg["limits"]["cre"], 0)
        self.assertEqual(LN.infer_stance(cfg, "cre"), "hunt")
        self.assertIn("Hunt", res["message"])

    def test_starve_locks_todays_mix(self):
        state = new_game("Starve", seed=1)
        res = LN.set_loan_stance(state, "ag", "starve")
        cfg = state["bank"]["loans"]
        self.assertEqual(cfg["spreads"]["ag"], 75)
        self.assertEqual(cfg["standards"]["ag"], 4)
        self.assertGreaterEqual(cfg["limits"]["ag"], 1)
        self.assertEqual(LN.infer_stance(cfg, "ag"), "starve")
        self.assertIn("Cap", res["message"])

    def test_hold_apply_snapshots_a_cap(self):
        state = new_game("HoldCap", seed=1)
        LN.set_loan_stance(state, "cre", "grow")
        self.assertEqual(state["bank"]["loans"]["limits"]["cre"], 0)
        LN.set_loan_stance(state, "cre", "hold")
        self.assertGreaterEqual(state["bank"]["loans"]["limits"]["cre"], 1)
        self.assertEqual(state["bank"]["loans"]["spreads"]["cre"], 0)
        self.assertEqual(state["bank"]["loans"]["standards"]["cre"], 2)

    def test_custom_when_levers_do_not_match(self):
        state = new_game("Custom", seed=1)
        engine.set_policy(state, "loans.spreads.cre", 15)
        self.assertEqual(LN.infer_stance(state["bank"]["loans"], "cre"), "custom")

    def test_hunt_is_more_volume_than_starve(self):
        state = new_game("Vol", seed=1)
        hunt = LN.preview_loan_stance(state, "ci", "hunt")
        starve = LN.preview_loan_stance(state, "ci", "starve")
        self.assertGreater(hunt["vol_ratio"], starve["vol_ratio"])
        self.assertGreater(hunt["quality_ratio"], starve["quality_ratio"])


class TestLoanTape(unittest.TestCase):
    def test_opening_tape_names_every_dollar(self):
        state = new_game("Tape", seed=1)
        cfg = state["bank"]["loans"]
        pool_tot = sum(p["balance"] for p in cfg["pools"])
        self.assertEqual(LN.note_tape_total(cfg), pool_tot)
        self.assertEqual(pool_tot, LN.total_loans(cfg))
        self.assertGreaterEqual(len(cfg["notes"]), 40)
        autos = [n for n in cfg["notes"] if n["product"] == "auto"]
        self.assertTrue(autos)
        self.assertLessEqual(min(n["balance"] for n in autos), 30_000_00)
        self.assertTrue(all(n.get("name") for n in cfg["notes"]))

    def test_tape_is_deterministic(self):
        a = new_game("T1", seed=11)
        b = new_game("T1", seed=11)
        names_a = [n["name"] for n in a["bank"]["loans"]["notes"]]
        names_b = [n["name"] for n in b["bank"]["loans"]["notes"]]
        self.assertEqual(names_a, names_b)
        c = new_game("T2", seed=12)
        names_c = [n["name"] for n in c["bank"]["loans"]["notes"]]
        self.assertNotEqual(names_a, names_c)

    def test_lending_section_exposes_tape_and_mix(self):
        g = Game()
        g.state = new_game("Sec", seed=1)
        lend = g.section("lending", {})
        self.assertIn("tape", lend)
        self.assertIn("mix", lend)
        self.assertGreater(lend["tape"]["total"], 40)
        self.assertEqual(lend["tape"]["dollars"], LN.total_loans(g.state["bank"]["loans"]))
        self.assertTrue(any(r["product"] == "auto" for r in lend["tape"]["rows"]))
        self.assertTrue(any(m["product"] == "ag" and m["stance"] == "hold"
                            for m in lend["mix"]))

    def test_old_save_without_notes_gets_a_tape(self):
        state = new_game("Old", seed=3)
        pools = sum(p["balance"] for p in state["bank"]["loans"]["pools"])
        state["bank"]["loans"]["notes"] = []
        del state["bank"]["loans"]["stances"]
        tape = LN.loan_tape(state)
        self.assertEqual(tape["dollars"], pools)
        self.assertGreater(tape["total"], 10)

    def test_notes_follow_the_pool_after_a_month(self):
        state = new_game("Sync", seed=5)
        state["bank"]["loans"]["queue"].clear()
        state["bank"]["funding"]["overnight_policy"] = "auto"
        state["events"]["pending"].clear()
        # First business day of February closes January.
        while state["time"]["date"] < "2000-02-02":
            engine.step_day(state)
            state["events"]["pending"].clear()
            state["bank"]["loans"]["queue"].clear()
        cfg = state["bank"]["loans"]
        self.assertEqual(LN.note_tape_total(cfg),
                         sum(p["balance"] for p in cfg["pools"]))
        self.assertEqual(L.trial_balance(state["bank"]["ledger"]), 0)

    def test_culpepper_is_on_the_tape_after_approve(self):
        state = new_game("Named", seed=1)
        app = state["bank"]["loans"]["queue"][0]
        engine.perform_action(state, "approve_loan", {"app_id": app["id"]})
        tape = LN.loan_tape(state)
        names = [r["name"] for r in tape["rows"]]
        self.assertIn("Culpepper Cattle Co.", names)


class TestMonthBook(unittest.TestCase):
    def _close_january(self, state):
        state["bank"]["funding"]["overnight_policy"] = "auto"
        while state["time"]["date"] < "2000-02-02":
            engine.step_day(state)
            state["events"]["pending"].clear()

    def test_opening_book_is_not_january_originations(self):
        state = new_game("OpenBk", seed=1)
        opening_ids = {n["id"] for n in state["bank"]["loans"]["notes"]}
        state["bank"]["loans"]["queue"].clear()
        self._close_january(state)
        recap = state["bank"]["loans"]["last_month_book"]
        self.assertIsNotNone(recap)
        new_ids = {e["id"] for e in recap["new"] if e.get("id") is not None}
        self.assertTrue(recap["new_count"] >= 1)
        self.assertFalse(opening_ids & new_ids)

    def test_culpepper_is_named_on_the_month_recap(self):
        state = new_game("CulBk", seed=1)
        app = state["bank"]["loans"]["queue"][0]
        engine.perform_action(state, "approve_loan", {"app_id": app["id"]})
        self._close_january(state)
        recap = state["bank"]["loans"]["last_month_book"]
        names = [e["name"] for e in recap["new"]]
        self.assertIn("Culpepper Cattle Co.", names)
        self.assertTrue(any(e.get("kind") == "large" for e in recap["new"]
                            if e["name"] == "Culpepper Cattle Co."))

    def test_decline_shows_up_as_what_did_not_book(self):
        state = new_game("NoBk", seed=1)
        app = state["bank"]["loans"]["queue"][0]
        engine.perform_action(state, "decline_loan", {"app_id": app["id"]})
        self._close_january(state)
        recap = state["bank"]["loans"]["last_month_book"]
        declined = [e["name"] for e in recap["declined"]]
        self.assertIn("Culpepper Cattle Co.", declined)
        self.assertNotIn("Culpepper Cattle Co.", [e["name"] for e in recap["new"]])

    def test_recap_is_logged_not_blocking(self):
        state = new_game("LogBk", seed=2)
        state["bank"]["loans"]["queue"].clear()
        self._close_january(state)
        evs = [e for e in state["events"]["log"] if e.get("type") == "lending_month"]
        self.assertEqual(len(evs), 1)
        self.assertFalse(evs[0].get("blocking"))
        self.assertNotIn(evs[0]["id"],
                         [e["id"] for e in state["events"]["pending"]])
        self.assertIn("Booked", evs[0]["text"])

    def test_digest_names_the_book(self):
        state = new_game("DigBk", seed=1)
        state["bank"]["loans"]["queue"].clear()
        self._close_january(state)
        d = state["digests"][-1]
        self.assertTrue(d.get("lending"))
        self.assertIn("Booked", d["lending"])
        self.assertTrue(d.get("lending_book"))
        self.assertGreater(d["lending_book"]["new_count"], 0)


if __name__ == "__main__":
    unittest.main()

