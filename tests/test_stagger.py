"""Focused tests for the phase-aware Stagger effect."""

from copy import deepcopy
import unittest

from scenarios import duel_fixture
from combat.transcript import render_transcript


class StaggerTests(unittest.TestCase):
    def setUp(self):
        self.sim = duel_fixture()
        self.source = self.sim.characters["brute"]
        self.target = self.sim.characters["gareth"]

    def stagger(self, duration=0.3):
        return self.sim.apply_stagger(self.source, self.target, "heavy_attack", duration)

    def test_idle_stagger_locks_actions_without_spending_resources(self):
        stamina = self.target.stamina
        self.assertTrue(self.stagger())
        self.assertEqual((self.target.phase, self.target.stagger_end_tick), ("Idle", 3))
        self.assertEqual(self.target.stamina, stamina)

        for tick in (0, 1, 2):
            self.sim.tick = tick
            self.sim.decide(self.target)
            self.assertEqual(self.target.phase, "Idle")
            self.assertEqual(self.target.stamina, stamina)

        self.sim.tick = 3
        self.sim.decide(self.target)
        self.assertEqual(self.target.phase, "Preparing")
        self.assertEqual(self.target.stamina, stamina - 3)

    def test_interruptible_preparation_is_extended_without_another_cost(self):
        self.sim.decide(self.target)
        self.assertEqual((self.target.phase, self.target.stamina), ("Preparing", 97))
        original_end = self.target.phase_end_tick

        self.sim.tick = 1
        self.stagger()
        self.assertEqual((self.target.phase, self.target.action, self.target.target),
                         ("Preparing", "sword_attack", "brute"))
        self.assertEqual(self.target.stamina, 97)
        self.assertEqual((self.target.phase_end_tick, self.target.stagger_end_tick),
                         (original_end + 3, 4))
        event = next(event for event in self.sim.events if event["event"] == "stagger")
        self.assertEqual((event["consequence"], event["delayed_action"],
                          event["added_preparation_seconds"],
                          event["previous_preparation_end_tick"],
                          event["preparation_ends_at_tick"]),
                         ("preparation_extended", "sword_attack", 0.3, original_end,
                          original_end + 3))

    def test_non_interruptible_preparation_is_also_extended(self):
        self.sim.actions["sword_attack"]["interruptible"] = False
        self.sim.decide(self.target)
        state = (self.target.phase, self.target.action, self.target.target, self.target.phase_end_tick)

        self.sim.tick = 1
        self.stagger()
        self.assertEqual((self.target.phase, self.target.action, self.target.target,
                          self.target.phase_end_tick), (*state[:3], state[3] + 3))
        event = next(event for event in self.sim.events if event["event"] == "stagger")
        self.assertEqual(event["consequence"], "preparation_extended")

        self.sim.tick = state[-1] + 3
        self.sim.execute(self.target)
        self.assertTrue(any(event["event"] == "damage" and event["actor"] == self.target.id
                            for event in self.sim.events))

    def test_recovery_is_extended_from_its_existing_end(self):
        self.target.phase = "Recovering"
        self.target.action = "sword_attack"
        self.target.phase_end_tick = 10
        self.sim.tick = 2

        self.stagger()
        self.assertEqual(self.target.phase_end_tick, 13)
        event = next(event for event in self.sim.events if event["event"] == "stagger")
        self.assertEqual((event["target_phase"], event["consequence"],
                          event["added_recovery_seconds"], event["recovery_ends_at_tick"]),
                         ("Recovering", "recovery_extended", 0.3, 13))

    def test_staggered_character_can_use_every_reactive_defense(self):
        for defense in ("block", "dodge", "parry", "brace"):
            with self.subTest(defense=defense):
                self.setUp()
                self.target.definition["defenses"] = [defense]
                self.sim.actions["heavy_attack"]["parryability"] = "parryable"
                self.stagger()
                self.source.action, self.source.target = "heavy_attack", self.target.id
                self.sim.execute(self.source)
                decision = next(event for event in self.sim.events
                                if event["event"] == "defense_decision")
                self.assertEqual(decision["defense"], defense)

    def test_repeated_stagger_does_not_refresh_or_extend(self):
        self.stagger()
        self.sim.tick = 1
        self.assertFalse(self.stagger())
        self.assertEqual(self.target.stagger_end_tick, 3)
        self.assertEqual(len([event for event in self.sim.events if event["event"] == "stagger"]), 1)
        ignored = next(event for event in self.sim.events if event["event"] == "stagger_ignored")
        self.assertEqual(ignored["reason"], "already_staggered")

    def test_new_stagger_after_expiry_can_extend_the_same_preparation_again(self):
        self.sim.decide(self.target)
        self.sim.tick = 1
        self.stagger()
        self.assertEqual(self.target.phase_end_tick, 8)
        self.sim.tick = 4
        self.stagger()
        self.assertEqual(self.target.phase_end_tick, 11)
        self.assertEqual(len([event for event in self.sim.events if event["event"] == "stagger"]), 2)

    def test_transcript_explains_preparation_delay_and_ignored_repeat(self):
        self.sim.decide(self.target)
        self.sim.tick = 1
        self.stagger()
        self.sim.tick = 2
        self.stagger()

        text = render_transcript(self.sim.events, self.sim.report(), self.sim.encounter["combatants"],
                                 self.sim.actions, verbose=True)
        self.assertIn("Brute's Heavy Attack", text)
        self.assertIn("Sword Attack Preparation is extended by 0.3s", text)
        self.assertIn("continues normally", text)
        self.assertNotIn("interrupted", text)
        self.assertIn("later effect does not refresh or extend", text)

    def test_strong_parry_staggers_execution_and_extends_upcoming_recovery(self):
        self.target.definition["defenses"] = ["parry"]
        self.target.definition["skills"]["parry"] = 70
        self.sim.actions["heavy_attack"]["parryability"] = "parryable"
        self.source.action, self.source.target = "heavy_attack", self.target.id

        self.sim.execute(self.source)

        hit = next(event for event in self.sim.events if event["event"] == "damage")
        self.assertEqual((hit["active_defense"], hit["outcome"]), ("parry", "Strong Defense"))
        stagger = next(event for event in self.sim.events if event["event"] == "stagger")
        self.assertEqual((stagger["actor"], stagger["source"], stagger["source_action"],
                          stagger["target_phase"], stagger["consequence"]),
                         ("brute", "gareth", "parry", "Executing", "recovery_extended"))
        self.assertEqual(self.source.phase_end_tick, 13)
        recovery = next(event for event in self.sim.events if event["event"] == "recovery_start")
        self.assertEqual(recovery["duration"], 1.3)

    def test_heavy_attack_effect_applies_only_on_strong_hit(self):
        self.target.definition["defenses"] = ["block"]
        for attribute in ("grip_control", "maximum_force", "balance"):
            self.target.definition["attributes"][attribute] = 0
        self.target.definition["skills"]["block"] = 0
        self.source.action, self.source.target = "heavy_attack", self.target.id
        self.sim.execute(self.source)
        hit = next(event for event in self.sim.events if event["event"] == "damage")
        self.assertEqual(hit["outcome"], "Strong Hit")
        stagger = next(event for event in self.sim.events if event["event"] == "stagger")
        self.assertEqual((stagger["source_action"], stagger["actor"], stagger["consequence"]),
                         ("heavy_attack", "gareth", "action_lockout"))

        other = duel_fixture()
        other.characters["gareth"].definition["defenses"] = []
        other.characters["brute"].action = "heavy_attack"
        other.characters["brute"].target = "gareth"
        other.execute(other.characters["brute"])
        hit = next(event for event in other.events if event["event"] == "damage")
        self.assertEqual(hit["outcome"], "Hit")
        self.assertFalse(any(event["event"] == "stagger" for event in other.events))

    def test_opportunity_parry_suppresses_stagger_against_controller(self):
        self.target.definition["opportunity_attack"] = "sword_attack"
        self.source.definition["defenses"] = ["parry"]
        self.source.definition["skills"]["parry"] = 200
        self.target.phase, self.target.phase_end_tick = "Recovering", 20
        self.target.action, self.target.target = "sword_attack", self.source.id

        self.sim.opportunity_attack(self.target, self.source)

        self.assertEqual((self.target.phase, self.target.phase_end_tick), ("Recovering", 20))
        ignored = next(event for event in self.sim.events if event["event"] == "stagger_ignored")
        self.assertEqual(ignored["reason"], "opportunity_attack_exception")

    def test_unknown_and_malformed_effects_are_rejected(self):
        for effect in (
            {"type": "stun", "outcome": "Strong Hit", "recipient": "defender", "duration_seconds": 0.3},
            {"type": "stagger", "outcome": "Strong Hit", "recipient": "defender",
             "duration_seconds": 0.3, "unexpected": True},
        ):
            with self.subTest(effect=effect):
                sim = duel_fixture()
                sim.actions["heavy_attack"]["effects"] = [deepcopy(effect)]
                with self.assertRaises(ValueError):
                    sim.validate()


if __name__ == "__main__":
    unittest.main()
