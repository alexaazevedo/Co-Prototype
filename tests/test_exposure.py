import unittest

from combat import positioning
from scenarios import formation_fixture


class ExposureTests(unittest.TestCase):
    def setUp(self):
        self.sim = formation_fixture()
        self.actor = self.sim.characters["elira"]
        self.enemy = self.sim.characters["skirmisher_2"]
        positioning.refresh(self.sim)

    def expose(self):
        self.enemy.reached = "Midline"
        positioning.refresh(self.sim)

    def test_exposed_action_cannot_start_or_spend_resources(self):
        self.expose()
        self.sim.decide(self.actor)
        self.assertEqual(self.actor.phase, "Idle")
        self.assertEqual(self.actor.stamina, 80)
        self.assertFalse(any(e["event"] == "resource_spent" for e in self.sim.events))
        self.assertIn("Exposed", self.sim.events[-1]["rejected"][0]["reason"])

    def test_exposure_during_preparation_cancels_at_execution(self):
        self.sim.decide(self.actor)
        self.assertEqual(self.actor.phase_end_tick, 5)
        self.expose()
        self.assertEqual(self.actor.phase, "Preparing")
        self.sim.tick = 5
        self.sim.execute(self.actor)
        self.assertEqual(self.actor.stamina, 77)
        self.assertEqual((self.actor.phase, self.actor.phase_end_tick), ("Recovering", 12))
        self.assertFalse(any(e["event"] == "damage" for e in self.sim.events))
        cancellation = next(e for e in self.sim.events if e["event"] == "action_cancelled")
        self.assertIn("Exposed", cancellation["reason"])

    def test_missing_or_false_flag_allows_action(self):
        for conditions in ({}, {"prevent_when_exposed": False}):
            with self.subTest(conditions=conditions):
                self.setUp()
                self.expose()
                self.sim.actions["ranged_attack"]["usage_conditions"] = conditions
                self.sim.decide(self.actor)
                self.sim.execute(self.actor)
                self.assertTrue(any(e["event"] == "damage" for e in self.sim.events))

    def test_condition_is_shared_by_other_action_and_resource_types(self):
        action = self.sim.actions["sword_attack"]
        action["usage_conditions"] = {"prevent_when_exposed": True}
        action["resource_type"] = "mana"
        self.actor.definition["actions"] = ["sword_attack"]
        self.expose()
        self.sim.decide(self.actor)
        self.assertEqual(self.actor.mana, 50)
        self.assertIn("Exposed", self.sim.events[-1]["rejected"][0]["reason"])

    def test_action_returns_when_threat_is_incapacitated(self):
        self.expose()
        self.sim.decide(self.actor)
        self.enemy.incapacitated = True
        self.enemy.health = 0
        positioning.refresh(self.sim)
        self.assertEqual(self.actor.positional_states, {"Protected"})
        self.sim.decide(self.actor)
        self.assertEqual(self.actor.phase, "Preparing")

    def test_condition_validation(self):
        for conditions in ({"prevent_when_exposed": "true"}, {"unknown": True}, []):
            with self.subTest(conditions=conditions):
                self.sim.actions["ranged_attack"]["usage_conditions"] = conditions
                with self.assertRaises(ValueError):
                    self.sim.validate()


if __name__ == "__main__":
    unittest.main()
