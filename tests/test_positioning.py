from pathlib import Path
import unittest

from combat.engine import load_simulation, quality
from combat import positioning
from combat.transcript import render_transcript
from scenarios import formation_fixture


CONFIG = Path(__file__).resolve().parent.parent / "config"


def formation():
    return formation_fixture()


class PositioningTests(unittest.TestCase):
    def setUp(self):
        self.sim = formation()
        self.gareth = self.sim.characters["gareth"]
        self.elira = self.sim.characters["elira"]
        self.mover = self.sim.characters["skirmisher_2"]
        positioning.refresh(self.sim)

    def execute_move(self, character=None, key="breakthrough"):
        character = character or self.mover
        character.action, character.target = key, character.id
        self.sim.execute(character)

    def set_margin(self, margin, character=None):
        character = character or self.mover
        controller_quality = quality(self.gareth, self.sim.balance["control_quality"], self.sim.balance)["total"]
        for attribute in self.sim.actions["breakthrough"]["attribute_weights"]:
            character.definition["attributes"][attribute] = controller_quality + margin
        character.definition["skills"]["movement"] = 50

    def test_capacity_protects_midline_and_extra_enemy_can_attempt_bypass(self):
        self.assertEqual(self.gareth.engagements, {"brute", "skirmisher_1"})
        self.assertEqual(self.mover.controlled_by, set())
        self.assertEqual(self.elira.positional_states, {"Protected"})
        self.assertFalse(positioning.can_access(self.mover, self.elira))
        self.assertIsNone(positioning.movement_reason(self.sim, self.mover, self.sim.actions["breakthrough"]))
        engaged = self.sim.characters["skirmisher_1"]
        self.assertIn("Withdraw", positioning.movement_reason(self.sim, engaged, self.sim.actions["breakthrough"]))

    def test_elira_attacks_from_protected_midline(self):
        self.sim.decide(self.elira)
        self.assertEqual(self.elira.positional_states, {"Protected"})
        self.assertEqual(self.elira.action, "ranged_attack")
        self.assertEqual(self.elira.phase, "Preparing")
        self.assertEqual(self.elira.phase_end_tick, 5)
        self.assertEqual(self.elira.stamina, 77)
        self.assertEqual(self.elira.mana, 50)

    def test_ranged_access_crosses_all_bands(self):
        action = self.sim.actions["ranged_attack"]
        for source_band in positioning.BANDS:
            for target_band in positioning.BANDS:
                with self.subTest(source=source_band, target=target_band):
                    self.elira.band, self.mover.band = source_band, target_band
                    self.assertTrue(positioning.attack_access(self.elira, self.mover, action))
        self.assertFalse(positioning.attack_access(self.elira, self.gareth, action))
        self.mover.incapacitated = True
        self.assertFalse(positioning.attack_access(self.elira, self.mover, action))

    def test_ranged_attack_remains_usable_while_engaged(self):
        self.sim.actions["ranged_attack"]["usage_conditions"]["prevent_when_exposed"] = False
        self.mover.reached = "Midline"
        self.elira.definition["engagement_capacity"] = 1
        positioning.refresh(self.sim)
        self.assertIn(self.mover.id, self.elira.engagements)
        self.sim.decide(self.elira)
        self.assertEqual(self.elira.action, "ranged_attack")
        self.sim.execute(self.elira)
        hit = next(e for e in self.sim.events if e["event"] == "damage")
        self.assertEqual(hit["action"], "ranged_attack")
        decision = next(e for e in self.sim.events if e["event"] == "defense_decision")
        self.assertNotIn("parry", {c["defense"] for c in decision["candidates"]})
        self.assertIn("parry", {c["defense"] for c in decision["rejected"]})

    def test_ranged_damage_uses_physical_protection_after_target_moves(self):
        target = self.sim.characters["brute"]
        self.elira.action, self.elira.target = "ranged_attack", target.id
        target.band = "Backline"
        target.definition["defenses"] = []
        target.definition["magical_protection"] = 10000
        self.sim.execute(self.elira)
        hit = next(e for e in self.sim.events if e["event"] == "damage")
        self.assertAlmostEqual(hit["raw_damage"], 26.73)
        self.assertAlmostEqual(hit["final_damage"], 26.73 / 1.2)
        self.assertEqual(hit["protection_rating"], 20)

    def test_ranged_opportunity_attack_is_rejected(self):
        self.elira.definition["opportunity_attack"] = "ranged_attack"
        with self.assertRaisesRegex(ValueError, "melee physical attack"):
            self.sim.validate()
        before = self.elira.stamina
        self.sim.opportunity_attack(self.elira, self.mover)
        self.assertEqual(self.elira.stamina, before)
        self.assertEqual(self.sim.events[-1]["event"], "opportunity_skipped")

    def test_contest_boundaries(self):
        for margin, expected in [(-5, "Failure"), (-4.99, "Partial Success"), (0, "Partial Success"),
                                 (4.99, "Partial Success"), (5, "Clean Success")]:
            with self.subTest(margin=margin):
                self.setUp()
                self.set_margin(margin)
                self.execute_move()
                contest = next(e for e in self.sim.events if e["event"] == "movement_contest")
                self.assertEqual(contest["outcome"], expected)
                self.assertEqual(self.mover.reached, "Frontline" if expected == "Failure" else "Midline")
                self.assertEqual(sum(e["event"] == "opportunity_attack" for e in self.sim.events), int(expected == "Partial Success"))

    def test_partial_success_exposes_ally_and_preserves_controller_action(self):
        self.gareth.phase, self.gareth.action, self.gareth.target, self.gareth.phase_end_tick = "Preparing", "sword_attack", "brute", 9
        before = self.gareth.stamina
        self.execute_move()
        self.assertEqual((self.gareth.phase, self.gareth.action, self.gareth.target, self.gareth.phase_end_tick),
                         ("Preparing", "sword_attack", "brute", 9))
        self.assertEqual(self.gareth.stamina, before - 3)
        self.assertEqual(self.elira.positional_states, {"Exposed"})
        self.assertTrue(positioning.can_access(self.elira, self.mover))
        self.assertTrue(positioning.can_access(self.mover, self.elira))
        self.assertFalse(positioning.can_access(self.gareth, self.mover))
        self.assertNotIn(self.mover.id, self.gareth.engagements)

    def test_opportunity_uses_normal_defense_and_damage_layers(self):
        self.execute_move()
        hit = next(e for e in self.sim.events if e["event"] == "damage")
        self.assertEqual(hit["active_defense"], "dodge")
        self.assertAlmostEqual(hit["raw_damage"], 34.5384)
        self.assertAlmostEqual(hit["final_damage"], 34.5384 * .5 / 1.1)

    def test_unaffordable_opportunity_does_not_prevent_movement(self):
        self.gareth.stamina = 2
        self.execute_move()
        self.assertEqual(self.mover.reached, "Midline")
        self.assertEqual(self.gareth.stamina, 2)
        self.assertTrue(any(e["event"] == "opportunity_skipped" for e in self.sim.events))

    def test_lethal_opportunity_stops_movement_and_recovery(self):
        self.mover.health = 1
        self.mover.definition["defenses"] = []
        self.execute_move()
        self.assertTrue(self.mover.incapacitated)
        self.assertEqual(self.mover.reached, "Frontline")
        self.assertEqual(self.mover.phase, "Idle")
        self.assertFalse(any(e["event"] == "recovery_start" and e["actor"] == self.mover.id for e in self.sim.events))

    def test_strong_parry_of_opportunity_preserves_controller_timing(self):
        self.mover.definition["defenses"] = ["parry"]
        self.mover.definition["skills"]["parry"] = 150
        self.gareth.phase, self.gareth.phase_end_tick = "Recovering", 20
        self.gareth.action, self.gareth.target = "sword_attack", "brute"
        self.execute_move()
        self.assertEqual((self.gareth.phase, self.gareth.phase_end_tick), ("Recovering", 20))
        self.assertTrue(any(e["event"] == "stagger_ignored" for e in self.sim.events))

    def test_withdrawal_uses_same_contest_and_releases_control(self):
        for margin, expected in [(-5, "Failure"), (0, "Partial Success"), (5, "Clean Success")]:
            with self.subTest(margin=margin):
                self.setUp()
                mover = self.sim.characters["skirmisher_1"]
                self.set_margin(margin, mover)
                self.execute_move(mover, "withdraw")
                event = next(e for e in self.sim.events if e["event"] == "movement_contest")
                self.assertEqual(event["outcome"], expected)
                self.assertEqual(mover.band, "Frontline" if expected == "Failure" else "Midline")
                self.assertEqual(bool(mover.controlled_by), expected == "Failure")

    def test_active_melee_attacker_opposes_withdraw_without_engagement_capacity(self):
        self.gareth.definition["engagement_capacity"] = 0
        positioning.refresh(self.sim)
        self.assertFalse(self.mover.controlled_by)
        self.gareth.phase, self.gareth.action, self.gareth.target = "Preparing", "sword_attack", self.mover.id
        self.execute_move(self.mover, "withdraw")
        contests = [event for event in self.sim.events if event["event"] == "movement_contest"]
        self.assertEqual([event["target"] for event in contests], [self.gareth.id])

    def test_idle_zero_capacity_enemy_does_not_oppose_withdraw(self):
        self.gareth.definition["engagement_capacity"] = 0
        positioning.refresh(self.sim)
        self.execute_move(self.mover, "withdraw")
        self.assertFalse(any(event["event"] == "movement_contest" for event in self.sim.events))
        movement = next(event for event in self.sim.events if event["event"] == "movement")
        self.assertEqual(movement["outcome"], "Unopposed")

    def test_ranged_attacker_does_not_create_melee_withdraw_pressure(self):
        self.gareth.definition["engagement_capacity"] = 0
        positioning.refresh(self.sim)
        self.elira.phase, self.elira.action, self.elira.target = "Preparing", "ranged_attack", self.mover.id
        self.execute_move(self.mover, "withdraw")
        self.assertFalse(any(event["event"] == "movement_contest" for event in self.sim.events))

    def test_plain_move_cannot_bypass_engagement(self):
        engaged = self.sim.characters["skirmisher_1"]
        self.assertIn("Withdraw", positioning.movement_reason(self.sim, engaged, self.sim.actions["advance"]))

    def test_incapacitated_controller_loses_capacity(self):
        self.gareth.health, self.gareth.incapacitated = 0, True
        positioning.refresh(self.sim)
        self.assertEqual(self.gareth.engagements, set())
        self.assertEqual(self.sim.characters["skirmisher_1"].controlled_by, set())
        self.execute_move()
        self.assertFalse(any(e["event"] == "movement_contest" for e in self.sim.events))
        self.assertEqual(self.mover.reached, "Midline")

    def test_targets_are_revalidated_on_execution(self):
        self.gareth.action, self.gareth.target = "sword_attack", self.mover.id
        self.mover.reached = "Midline"
        positioning.refresh(self.sim)
        self.sim.execute(self.gareth)
        self.assertFalse(any(e["event"] == "damage" for e in self.sim.events))
        self.assertTrue(any(e["event"] == "action_cancelled" for e in self.sim.events))

    def test_band_movement_is_one_step_and_reversible(self):
        self.assertEqual(positioning.destination(self.mover, "advance"), ("Frontline", "Midline"))
        self.mover.reached = "Midline"
        self.assertEqual(positioning.destination(self.mover, "advance"), ("Frontline", "Backline"))
        self.assertEqual(positioning.destination(self.mover, "withdraw"), ("Frontline", "Frontline"))
        self.mover.reached = "Backline"
        self.assertIsNone(positioning.destination(self.mover, "advance"))
        self.assertEqual(positioning.destination(self.elira, "advance"), ("Frontline", "Frontline"))
        self.assertEqual(positioning.destination(self.elira, "withdraw"), ("Backline", "Frontline"))

    def test_controller_priority_and_stable_engagements(self):
        # Elira can become a second front controller through configuration.
        self.elira.band = "Frontline"
        self.elira.definition.update(engagement_capacity=1, control_priority=20)
        for c in self.sim.characters.values():
            c.engagements.clear()
        positioning.refresh(self.sim)
        self.assertEqual(self.elira.engagements, {"brute"})
        self.assertEqual(self.gareth.engagements, {"skirmisher_1", "skirmisher_2"})
        self.mover.definition["engagement_priority"] = 100
        positioning.refresh(self.sim)
        self.assertEqual(self.elira.engagements, {"brute"})
        self.assertEqual(self.gareth.engagements, {"skirmisher_1", "skirmisher_2"})

    def test_retreating_character_stops_controlling_but_can_be_controlled(self):
        brute = self.sim.characters["brute"]
        self.gareth.retreating = True
        brute.definition["engagement_capacity"] = 1
        positioning.refresh(self.sim)
        self.assertEqual(self.gareth.engagements, set())
        self.assertEqual(self.gareth.controlled_by, {brute.id})
        self.assertEqual(brute.engagements, {self.gareth.id})

    def test_movement_preparation_pays_cost_and_takes_time(self):
        sim = formation()
        sim.balance["max_duration_seconds"] = .5
        sim.run()
        mover = sim.characters["skirmisher_2"]
        payment = next(e for e in sim.events if e["event"] == "resource_spent" and e["actor"] == mover.id)
        move = next(e for e in sim.events if e["event"] == "movement")
        recovery = next(e for e in sim.events if e["event"] == "recovery_start" and e["actor"] == mover.id)
        self.assertEqual((payment["timestamp"], payment["amount"]), (0, 3))
        self.assertEqual(move["timestamp"], .5)
        self.assertEqual(recovery["duration"], .5)
        self.assertEqual(mover.phase_end_tick, 10)

    def test_full_formation_repeats_and_logs_access_and_movement(self):
        first, second = formation(), formation()
        self.assertEqual(first.run(), second.run())
        self.assertEqual(first.events, second.events)
        self.assertTrue(any(e["event"] == "damage" and e["target"] == "elira" for e in first.events))
        text = render_transcript(first.events, first.report(), first.encounter["combatants"], first.actions, verbose=True)
        self.assertIn("OPPORTUNITY ATTACK", text)
        self.assertIn("PARTIAL SUCCESS", text)
        self.assertIn("target outside melee access", text)


if __name__ == "__main__":
    unittest.main()
