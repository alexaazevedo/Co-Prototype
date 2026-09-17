from pathlib import Path
import unittest

from combat.defense_matrix import build_matrix, DEFENSES
from combat.engine import load_simulation


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.sim = load_simulation(Path(__file__).resolve().parent.parent / "config")

    def test_matrix_matches_engine_for_every_defense_and_row(self):
        rows = build_matrix(self.sim.balance, self.sim.actions)
        self.assertEqual(len(rows), 25)
        self.assertEqual([row[0] for row in rows], list(range(0, 121, 5)))
        defender = self.sim.characters["gareth"]
        attacker = self.sim.characters["brute"]
        for row in rows:
            defender.definition["attributes"] = {key: row[0] for key in defender.definition["attributes"]}
            defender.definition["skills"] = {key: 50 for key in defender.definition["skills"]}
            defender.stamina = 1000
            self.sim.choose_defense(attacker, defender, self.sim.actions["sword_attack"], {"total": 80}, 100)
            candidates = {c["defense"]: c for c in self.sim.events[-1]["candidates"]}
            for key, damage in zip(DEFENSES, row[1:]):
                self.assertAlmostEqual(damage, 100 * (1 - candidates[key]["reduction"]))

    def test_reads_configured_reductions_and_scales_incoming_damage(self):
        self.sim.actions["dodge"]["outcome_reductions"]["Contested"] = .3
        row = build_matrix(self.sim.balance, self.sim.actions, damage=200, minimum=80, maximum=80)[0]
        self.assertEqual(row[2], 140)
        self.assertEqual(row[4], 160)

    def test_invalid_inputs_are_rejected(self):
        for options in ({"step": 0}, {"maximum": -1}, {"damage": -1}, {"damage": float("nan")},
                        {"attack_quality": float("inf")}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                build_matrix(self.sim.balance, self.sim.actions, **options)


if __name__ == "__main__":
    unittest.main()
