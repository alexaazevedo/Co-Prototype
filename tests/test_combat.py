import copy
from pathlib import Path
import unittest

from combat.engine import Simulation, load_simulation, outcome_for, quality


CONFIG = Path(__file__).resolve().parent.parent / "config"


def block_only_simulation():
    """Keep the original foundation checks independent of new defense choices."""
    sim = load_simulation(CONFIG)
    for character in sim.characters.values():
        character.definition["defenses"] = ["block"]
    return sim


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.sim = block_only_simulation()

    def test_repeated_runs_have_identical_events(self):
        first = self.sim.run()
        second = block_only_simulation()
        self.assertEqual(first, second.run())
        self.assertEqual(self.sim.events, second.events)

    def test_quality_and_unclamped_total(self):
        gareth = self.sim.characters["gareth"]
        q = quality(gareth, self.sim.actions["sword_attack"], self.sim.balance)
        self.assertAlmostEqual(q["capability"], 61.5)
        self.assertAlmostEqual(q["total"], 65.5)
        gareth.definition["attributes"] = {k: 110 for k in gareth.definition["attributes"]}
        self.assertGreater(quality(gareth, self.sim.actions["sword_attack"], self.sim.balance)["total"], 100)

    def test_quality_boundaries_include_fractional_values(self):
        for margin, name in [(15, "Strong Defense"), (14.9, "Defense"), (5, "Defense"),
                             (4.9, "Contested"), (-4.9, "Contested"), (-5, "Hit"),
                             (-14.9, "Hit"), (-15, "Strong Hit")]:
            self.assertEqual(outcome_for(margin, self.sim.balance)["name"], name)

    def test_first_sword_damage_layers(self):
        self.sim.run()
        e = next(e for e in self.sim.events if e["event"] == "damage")
        self.assertEqual(e["actor"], "gareth")
        self.assertEqual(e["timestamp"], 0.5)
        self.assertEqual(e["outcome"], "Strong Hit")
        self.assertAlmostEqual(e["raw_damage"], 27 * 1.23 * 1.04)
        self.assertEqual(e["active_defense_reduction"], 0)
        self.assertAlmostEqual(e["final_damage"], 27 * 1.23 * 1.04 / 1.2)
        self.assertEqual(e["incoming_damage"], e["raw_damage"])
        self.assertAlmostEqual(e["incoming_damage"], e["active_defense_reduction"] + e["protection_reduction"] + e["final_damage"])

    def test_block_reduction_and_stamina_cost(self):
        self.sim.run()
        e = next(e for e in self.sim.events if e["event"] == "damage" and e["actor"] == "brute")
        self.assertEqual(e["outcome"], "Strong Defense")
        self.assertAlmostEqual(e["active_defense_reduction"], e["raw_damage"] * 0.65)
        self.assertAlmostEqual(e["final_damage"], e["raw_damage"] * 0.35 / 1.55)
        cost = next(e for e in self.sim.events if e["event"] == "resource_spent"
                    and e["actor"] == "gareth" and e["action"] == "block")
        self.assertAlmostEqual(cost["amount"], e["active_defense_reduction"] * 0.15)

    def test_timing_and_resource_payment(self):
        self.sim.run()
        events = self.sim.events
        starts = [e["timestamp"] for e in events if e["event"] == "preparation_start" and e["actor"] == "gareth"]
        self.assertEqual(starts[:3], [0.0, 1.2, 2.4])
        paid = next(e for e in events if e["event"] == "resource_spent" and e["actor"] == "gareth")
        self.assertEqual((paid["timestamp"], paid["amount"], paid["after"]), (0, 3, 97))

    def test_exhaustion_and_timeout(self):
        for f in self.sim.characters.values():
            f.stamina = 0
        report = self.sim.run()
        self.assertEqual(report["result"], "Unresolved")
        self.assertEqual(report["duration_seconds"], 120)
        self.assertFalse(any(e["event"] == "damage" for e in self.sim.events))

    def test_unaffordable_block_is_unopposed(self):
        self.sim.characters["brute"].stamina = 0
        self.sim.characters["brute"].definition["skills"]["block"] = 130
        self.sim.run()
        e = next(e for e in self.sim.events if e["event"] == "damage")
        self.assertEqual(e["active_defense"], "none")
        self.assertIsNone(e["defense_quality"])
        self.assertEqual(e["outcome"], "Hit")
        self.assertEqual(e["active_defense_reduction"], 0)

        self.assertEqual(e["incoming_damage"], e["raw_damage"])
        self.assertAlmostEqual(e["final_damage"], e["raw_damage"] / 1.2)

    def test_each_block_outcome_only_applies_its_reduction(self):
        for defense_skill, expected_outcome, reduction in [
            (130, "Strong Defense", 0.65), (110, "Defense", 0.55),
            (85, "Contested", 0.4), (60, "Hit", 0.2), (40, "Strong Hit", 0),
        ]:
            with self.subTest(outcome=expected_outcome):
                sim = block_only_simulation()
                sim.characters["brute"].definition["skills"]["block"] = defense_skill
                sim.run()
                hit = next(e for e in sim.events if e["event"] == "damage")
                self.assertEqual(hit["outcome"], expected_outcome)
                self.assertAlmostEqual(hit["raw_damage"], 34.5384)
                self.assertEqual(hit["incoming_damage"], hit["raw_damage"])
                self.assertAlmostEqual(hit["active_defense_reduction"], 34.5384 * reduction)
                self.assertAlmostEqual(hit["final_damage"], 34.5384 * (1 - reduction) / 1.2)
                cost = next(e for e in sim.events if e["event"] == "resource_spent"
                            and e["actor"] == "brute" and e["action"] == "block")
                self.assertAlmostEqual(cost["amount"], 34.5384 * reduction * 0.15)

    def test_block_preventing_no_damage_is_free_at_zero_stamina(self):
        self.sim.characters["brute"].stamina = 0
        self.sim.run()
        hit = next(e for e in self.sim.events if e["event"] == "damage")
        self.assertEqual(hit["active_defense"], "block")
        self.assertEqual(hit["active_defense_reduction"], 0)
        cost = next(e for e in self.sim.events if e["event"] == "resource_spent"
                    and e["actor"] == "brute" and e["action"] == "block")
        self.assertEqual(cost["amount"], 0)
        self.assertEqual(cost["after"], 0)

    def test_simultaneous_lethal_action_uses_id_order(self):
        self.sim.actions["heavy_attack"]["preparation_seconds"] = 0.5
        self.sim.characters["gareth"].health = 1
        self.sim.characters["brute"].health = 1
        report = self.sim.run()
        self.assertEqual(report["result"], "Defeat")
        damage = [e for e in self.sim.events if e["event"] == "damage"]
        self.assertEqual(len(damage), 1)
        self.assertEqual(damage[0]["actor"], "brute")
        self.assertTrue(self.sim.characters["gareth"].incapacitated)

    def test_incapacitated_units_never_act_again(self):
        self.sim.run()
        event = next(e for e in self.sim.events if e["event"] == "incapacitated")
        after = self.sim.events[self.sim.events.index(event) + 1:]
        self.assertFalse(any(e["actor"] == event["actor"] and e["event"] in ("execution", "defense_decision", "preparation_start") for e in after))
        self.assertEqual(self.sim.result, "Victory")

    def test_invalid_tick_duration_is_rejected(self):
        actions = copy.deepcopy(self.sim.actions)
        actions["sword_attack"]["preparation_seconds"] = 0.55
        with self.assertRaisesRegex(ValueError, "multiple"):
            Simulation(self.sim.balance, actions, self.sim.encounter)


if __name__ == "__main__":
    unittest.main()
