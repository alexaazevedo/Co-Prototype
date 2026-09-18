from copy import deepcopy
import unittest

from combat.encounters import materialize_encounter


class EncounterMaterializationTests(unittest.TestCase):
    def setUp(self):
        self.character = {
            "id": "hero",
            "name": "Hero",
            "maximum_health": 100,
            "maximum_stamina": 50,
        }
        self.roster = {"characters": [deepcopy(self.character)]}
        self.encounter = {
            "name": "Roster test",
            "combatants": [{"id": "hero", "team": "party", "band": "Backline"}],
        }

    def test_expands_placement_without_mutating_inputs(self):
        original_roster = deepcopy(self.roster)
        original_encounter = deepcopy(self.encounter)
        expanded = materialize_encounter(self.encounter, self.roster)
        self.assertEqual(expanded["combatants"][0], {
            **self.character, "team": "party", "band": "Backline"})
        self.assertEqual(self.roster, original_roster)
        self.assertEqual(self.encounter, original_encounter)

    def test_complete_inline_encounter_remains_supported(self):
        inline = deepcopy(self.encounter)
        inline["combatants"][0].update(self.character)
        self.assertEqual(materialize_encounter(inline), inline)

    def test_rejects_unknown_duplicate_and_placement_fields_in_roster(self):
        cases = [
            ({"characters": [self.character, deepcopy(self.character)]}, "duplicate IDs"),
            ({"characters": [{**self.character, "team": "party"}]}, "cannot define"),
            ({"characters": []}, "Unknown roster character"),
        ]
        for roster, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                materialize_encounter(self.encounter, roster)

    def test_rejects_mixed_placement_and_inline_definitions(self):
        mixed = deepcopy(self.encounter)
        mixed["combatants"].append({**self.character, "team": "enemy", "band": "Frontline"})
        with self.assertRaisesRegex(ValueError, "cannot mix"):
            materialize_encounter(mixed, self.roster)

    def test_rejects_placement_overrides(self):
        overridden = deepcopy(self.encounter)
        overridden["combatants"][0]["maximum_health_override"] = 200
        with self.assertRaisesRegex(ValueError, "only id, team and band"):
            materialize_encounter(overridden, self.roster)


if __name__ == "__main__":
    unittest.main()
