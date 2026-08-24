"""Same seed + same inputs => identical outcomes; save/load is lossless."""

import json
import os
import tempfile
import unittest

from bankgame.sim.newgame import new_game
from bankgame.sim import engine
from bankgame.store import Store


def run_days(state, n):
    for _ in range(n):
        engine.step_day(state)
        state["events"]["pending"].clear()   # keep the clock moving


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_world(self):
        a = new_game("A", seed=777)
        b = new_game("A", seed=777)
        run_days(a, 90)
        run_days(b, 90)
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))

    def test_different_seed_different_world(self):
        a = new_game("A", seed=777)
        b = new_game("A", seed=778)
        run_days(a, 90)
        run_days(b, 90)
        self.assertNotEqual(json.dumps(a["economy"], sort_keys=True),
                            json.dumps(b["economy"], sort_keys=True))

    def test_save_load_roundtrip_continues_identically(self):
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "t.db")
            store = Store(db)
            a = new_game("RT", seed=42)
            run_days(a, 40)
            store.create_save("RT", 42)
            store.snapshot(a)
            # branch A continues in memory
            run_days(a, 40)
            # branch B reloads from disk and continues
            b = store.load("RT")
            self.assertIsNotNone(b)
            run_days(b, 40)
            self.assertEqual(json.dumps(a, sort_keys=True),
                             json.dumps(b, sort_keys=True))

    def test_rollback_discards_future(self):
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "t.db")
            store = Store(db)
            a = new_game("RB", seed=9)
            store.create_save("RB", 9)
            run_days(a, 10)
            store.snapshot(a)
            day10 = a["time"]["day_index"]
            run_days(a, 10)
            store.snapshot(a)
            back = store.load("RB", day_index=day10)
            self.assertEqual(back["time"]["day_index"], day10)
            snaps = store.list_snapshots("RB")
            self.assertTrue(all(s["day_index"] <= day10 for s in snaps))


if __name__ == "__main__":
    unittest.main()
