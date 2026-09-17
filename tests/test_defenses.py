"""Controlled fixtures isolate defense rules from encounter balance."""

from pathlib import Path
import unittest

from combat.engine import load_simulation, quality
from combat.transcript import render_transcript


CONFIG = Path(__file__).resolve().parent.parent / "config"


class DefenseTests(unittest.TestCase):
    def test_configured_weights_read_character_attributes(self):
        sim = load_simulation(CONFIG)
        character = sim.characters["gareth"]
        dodge = quality(character, sim.actions["dodge"], sim.balance)
        parry = quality(character, sim.actions["parry"], sim.balance)
        self.assertAlmostEqual(dodge["capability"], 55)
        self.assertAlmostEqual(parry["capability"], 62.5)
        character.definition["attributes"]["reflexes"] += 20
        self.assertAlmostEqual(quality(character, sim.actions["dodge"], sim.balance)["total"] - dodge["total"], 5)
        self.assertAlmostEqual(quality(character, sim.actions["parry"], sim.balance)["total"] - parry["total"], 4)

    def test_full_defense_encounter_is_repeatable(self):
        first, second = load_simulation(CONFIG), load_simulation(CONFIG)
        self.assertEqual(first.run(), second.run())
        self.assertEqual(first.events, second.events)
        decisions = [e for e in first.events if e["event"] == "defense_decision"]
        self.assertTrue(decisions)
        for decision in decisions:
            self.assertEqual(len(decision["candidates"]), 4)
            self.assertEqual(decision["defense"], decision["candidates"][0]["defense"])

    def setUp(self):
        self.sim = load_simulation(CONFIG)
        self.attacker = self.sim.characters["brute"]
        self.defender = self.sim.characters["gareth"]
        self.attack = self.sim.actions["heavy_attack"]
        self.attack["allowed_defenses"] = ["block", "dodge", "parry", "brace"]
        self.attack["parryability"] = "parryable"
        reductions = {"Strong Defense": 1, "Defense": 1, "Contested": 0.5, "Hit": 0, "Strong Hit": 0}
        for defense, cost in (("dodge", 5), ("parry", 3)):
            self.sim.actions[defense] = {
                "name": defense.title(), "category": "defense", "stamina_cost": cost,
                "attribute_weights": {"maximum_force": 1}, "skill": defense,
                "outcome_reductions": dict(reductions),
                "difficult_quality_penalty": -10, "stagger_seconds": 0.3}
            self.defender.definition["skills"][defense] = 50
        self.defender.definition["tactics"]["defense_preferences"] = {}

    def strike(self, defense, capability=47):
        self.defender.definition["defenses"] = [defense]
        self.defender.definition["attributes"]["maximum_force"] = capability
        self.attacker.action, self.attacker.target = "heavy_attack", "gareth"
        self.sim.execute(self.attacker)
        return next(e for e in reversed(self.sim.events) if e["event"] == "damage")

    def test_dodge_and_parry_outcome_tables(self):
        for defense in ("dodge", "parry"):
            for capability, outcome, reduction in [(67, "Strong Defense", 1), (57, "Defense", 1),
                                                   (47, "Contested", 0.5), (37, "Hit", 0), (27, "Strong Hit", 0)]:
                with self.subTest(defense=defense, outcome=outcome):
                    self.setUp()
                    hit = self.strike(defense, capability)
                    self.assertEqual(hit["outcome"], outcome)
                    self.assertAlmostEqual(hit["raw_damage"], 49.9392)
                    self.assertAlmostEqual(hit["active_defense_reduction"], 49.9392 * reduction)
                    self.assertAlmostEqual(hit["final_damage"], 49.9392 * (1 - reduction) / 1.55)
                    self.assertEqual(self.defender.stamina, 100 - (5 if defense == "dodge" else 3))
                    self.assertEqual(self.attacker.phase_end_tick, 13 if defense == "parry" and outcome == "Strong Defense" else 10)

    def test_brace_is_free_and_available_when_exhausted(self):
        self.defender.stamina = 0
        hit = self.strike("brace")
        self.assertEqual(self.defender.stamina, 0)
        self.assertIsNone(hit["defense_quality"])
        self.assertEqual(hit["outcome"], "No contest")
        self.assertAlmostEqual(hit["final_damage"], 49.9392 * 0.8 / 1.55)

    def test_brace_cost_is_configurable(self):
        self.sim.actions["brace"]["stamina_cost"] = 2
        self.strike("brace")
        self.assertEqual(self.defender.stamina, 98)

    def test_difficult_parry_applies_penalty_before_comparison(self):
        self.attack["parryability"] = "difficult"
        hit = self.strike("parry", 67)
        self.assertEqual(hit["defense_quality"]["state_modifier"], -10)
        self.assertEqual(hit["defense_quality"]["total"], 57)
        self.assertEqual(hit["outcome"], "Defense")
        self.assertFalse(any(e["event"] == "stagger" for e in self.sim.events))

    def test_ineligible_defenses_are_rejected(self):
        for defense, restriction, reason in [
            ("parry", "not_parryable", "attack is not parryable"),
            ("dodge", "movement", "movement for Dodge is not practical"),
            ("dodge", "cost", "insufficient stamina"),
            ("parry", "allowed", "attack does not allow this defense")]:
            with self.subTest(restriction=restriction):
                self.setUp()
                if restriction == "not_parryable":
                    self.attack["parryability"] = restriction
                elif restriction == "movement":
                    self.defender.definition["dodge_practical"] = False
                elif restriction == "cost":
                    self.defender.stamina = 4
                else:
                    self.attack["allowed_defenses"] = ["brace"]
                hit = self.strike(defense, 100)
                self.assertEqual(hit["active_defense"], "none")
                decision = next(e for e in self.sim.events if e["event"] == "defense_decision")
                self.assertEqual(decision["rejected"][0]["reason"], reason)

    def test_defending_does_not_change_preparation_or_recovery(self):
        for phase in ("Preparing", "Recovering"):
            for defense in ("block", "dodge", "parry", "brace"):
                with self.subTest(phase=phase, defense=defense):
                    self.setUp()
                    self.defender.phase = phase
                    self.defender.phase_end_tick = 25
                    self.defender.action, self.defender.target = "sword_attack", "brute"
                    self.strike(defense, 67)
                    self.assertEqual((self.defender.phase, self.defender.phase_end_tick,
                                      self.defender.action, self.defender.target),
                                     (phase, 25, "sword_attack", "brute"))

    def test_selection_uses_cost_preferences_and_stable_ties(self):
        self.defender.definition["defenses"] = ["parry", "dodge", "brace"]
        self.defender.definition["attributes"]["maximum_force"] = 67
        args = (self.attacker, self.defender, self.attack, {"total": 47}, 49.9392)
        self.assertEqual(self.sim.choose_defense(*args)["defense"], "parry")
        self.defender.definition["tactics"]["resource_penalty_per_point"] = 0
        self.assertEqual(self.sim.choose_defense(*args)["defense"], "dodge")
        self.defender.definition["tactics"]["defense_preferences"]["brace"] = 100
        self.assertEqual(self.sim.choose_defense(*args)["defense"], "brace")
        self.defender.definition["tactics"]["defense_preferences"] = {}
        self.defender.stamina = 0
        self.assertEqual(self.sim.choose_defense(*args)["defense"], "brace")

    def test_transcript_explains_avoidance_brace_and_stagger(self):
        for defense in ("dodge", "parry", "brace"):
            with self.subTest(defense=defense):
                self.setUp()
                self.strike(defense, 67)
                text = render_transcript(self.sim.events, self.sim.report(), self.sim.encounter["combatants"],
                                         self.sim.actions, verbose=True)
                if defense == "brace":
                    self.assertIn("Brace: no Quality contest", text)
                    self.assertIn("spent 0", text)
                else:
                    self.assertIn("avoids all damage", text)
                    self.assertNotIn("Brute hits Gareth", text)
                if defense == "parry":
                    self.assertIn("Recovery extended by 0.3s", text)
                self.assertIn("highest defense utility", text)


if __name__ == "__main__":
    unittest.main()
