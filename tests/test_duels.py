from copy import deepcopy
import unittest

from combat.encounters import make_duel
from combat.engine import Simulation
from combat import positioning
from pathlib import Path
from combat.engine import load_simulation


class DuelTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_simulation(Path(__file__).resolve().parent.parent / 'config', Path(__file__).resolve().parent.parent / 'config/formation.json')
        self.original = deepcopy(self.fixture.encounter)

    def duel(self, positions="frontline", first="gareth", second="talen"):
        encounter = make_duel(self.fixture.encounter, first, second, positions)
        return Simulation(self.fixture.balance, self.fixture.actions, encounter)

    def test_frontline_uses_two_opposing_copies_and_preserves_source(self):
        sim = self.duel()
        self.assertEqual(len(sim.characters), 2)
        self.assertEqual(sim.characters["gareth"].definition["team"], "party")
        self.assertEqual(sim.characters["talen"].definition["team"], "enemy")
        self.assertEqual({c.band for c in sim.characters.values()}, {"Frontline"})
        for character in sim.characters.values():
            expected = deepcopy(next(c for c in self.original["combatants"] if c["id"] == character.id))
            expected.update(team=character.definition["team"], band="Frontline")
            self.assertEqual(character.definition, expected)
        positioning.refresh(sim)
        self.assertEqual(sim.characters["talen"].positional_states, {"Exposed"})
        self.assertIsNotNone(sim.action_block_reason(sim.characters["talen"], sim.actions["ranged_attack"]))
        self.assertEqual(self.fixture.encounter, self.original)

    def test_base_keeps_bands_and_existing_range_rules(self):
        sim = self.duel("base")
        self.assertEqual(sim.characters["gareth"].band, "Frontline")
        self.assertEqual(sim.characters["talen"].band, "Backline")
        positioning.refresh(sim)
        self.assertFalse(positioning.can_access(sim.characters["gareth"], sim.characters["talen"]))
        self.assertIsNone(sim.action_block_reason(sim.characters["talen"], sim.actions["ranged_attack"]))
        self.assertEqual(self.fixture.encounter, self.original)

    def test_first_character_sets_result_perspective(self):
        for first, second in (("gareth", "talen"), ("talen", "gareth")):
            with self.subTest(first=first):
                sim = self.duel(first=first, second=second)
                sim.characters[second].incapacitated = True
                self.assertEqual(sim.completion(), "Victory")
                sim.characters[second].incapacitated = False
                sim.characters[first].incapacitated = True
                self.assertEqual(sim.completion(), "Defeat")

    def test_rejects_unknown_or_duplicate_selections(self):
        for first, second in (("gareth", "gareth"), ("missing", "talen")):
            with self.subTest(first=first, second=second), self.assertRaises(ValueError):
                self.duel(first=first, second=second)

    def test_both_modes_run_deterministically_without_mutating_source(self):
        for mode in ("frontline", "base"):
            with self.subTest(mode=mode):
                first, second = self.duel(mode), self.duel(mode)
                self.assertEqual(first.run(), second.run())
                self.assertEqual(first.events, second.events)
        self.assertEqual(self.fixture.encounter, self.original)


if __name__ == "__main__":
    unittest.main()
