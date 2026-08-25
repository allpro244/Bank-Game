"""Player-facing chrome: franchise strip, structured memos, market previews."""

import unittest

from bankgame.sim.newgame import new_game
from bankgame.server import Game


class TestPlayerUI(unittest.TestCase):
    def test_summary_franchise_and_unlock(self):
        g = Game()
        g.state = new_game("UI", seed=1)
        s = g.summary()
        self.assertIn("Caprock", s["franchise"]["home"])
        self.assertIn("lender", s["franchise"]["people"].lower())
        self.assertTrue(s["franchise"]["cash"])
        self.assertTrue(s["franchise"]["exam"])
        self.assertEqual(s["unlock"]["branches"], 1)
        self.assertEqual(s["unlock"]["months_closed"], 0)
        self.assertGreater(s["unlock"]["months_to_exam"], 6)
        self.assertIsInstance(s["econ"]["fed_funds"], float)
        self.assertGreater(s["econ"]["fed_funds"], 0)

    def test_lending_queue_has_counter_preview(self):
        g = Game()
        g.state = new_game("UI", seed=1)
        lend = g.section("lending", {})
        app = lend["queue"][0]
        self.assertEqual(app["name"], "Culpepper Cattle Co.")
        self.assertIn("counter_preview", app)
        self.assertLess(app["counter_preview"]["amount"], app["amount"])
        self.assertIn("participate_preview", app)

    def test_markets_section_has_grouped_previews(self):
        g = Game()
        g.state = new_game("UI", seed=1)
        mk = g.section("markets", {})
        self.assertIn("previews", mk)
        self.assertIn("kind_order", mk)
        self.assertIn("caprock", mk["previews"])
        self.assertIn("verdict", mk["previews"]["caprock"])
        self.assertEqual(mk["regions"]["caprock"]["kind"], "rural")


if __name__ == "__main__":
    unittest.main()
