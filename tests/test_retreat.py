from copy import deepcopy
import unittest

from combat import positioning, retreat
from combat.engine import Simulation
from scenarios import formation_fixture


class RetreatTests(unittest.TestCase):
    def setUp(self):
        base = formation_fixture()
        encounter = deepcopy(base.encounter)
        encounter["retreat"] = {"enabled": True, "health_threshold": .3,
                                "useful_resource_threshold": .2, "trigger_mode": "either",
                                "allow_exhausted_withdrawal": True}
        for c in encounter["combatants"]:
            if c["team"] == "party" and "withdraw" not in c["actions"]:
                c["actions"].append("withdraw")
        self.sim = Simulation(base.balance, base.actions, encounter)
        self.gareth = self.sim.characters["gareth"]
        self.elira = self.sim.characters["elira"]

    def trigger(self):
        self.gareth.stamina = self.elira.stamina = 0
        retreat.check(self.sim)

    def test_useful_resources_exclude_unused_mana(self):
        values = retreat.metrics(self.sim)
        self.assertEqual(values["useful_resources_baseline"], 180)
        self.elira.mana = 10000
        self.trigger()
        self.assertTrue(self.sim.retreat_active)
        self.assertEqual(retreat.metrics(self.sim)["useful_resource_fraction"], 0)

    def test_mana_is_included_when_an_action_uses_it(self):
        self.sim.actions["ranged_attack"]["resource_type"] = "mana"
        retreat.initialize(self.sim)
        self.assertEqual(retreat.metrics(self.sim)["useful_resources_baseline"], 230)
        self.assertIn("mana", self.sim.retreat_resources["elira"])

    def test_health_threshold_is_inclusive_and_retreat_stays_active(self):
        self.gareth.health, self.elira.health = 54, 30
        retreat.check(self.sim)
        self.assertTrue(self.sim.retreat_active)
        self.gareth.health, self.elira.health = 180, 100
        retreat.check(self.sim)
        self.assertEqual(sum(e["event"] == "retreat_triggered" for e in self.sim.events), 1)

    def test_both_requires_both_thresholds(self):
        self.sim.encounter["retreat"]["trigger_mode"] = "both"
        self.trigger()
        self.assertFalse(self.sim.retreat_active)
        self.gareth.health = self.elira.health = 10
        retreat.check(self.sim)
        self.assertTrue(self.sim.retreat_active)

    def test_incapacitated_member_remains_in_baseline(self):
        self.gareth.incapacitated = True
        self.gareth.health = 0
        values = retreat.metrics(self.sim)
        self.assertEqual(values["health_baseline"], 280)
        self.assertAlmostEqual(values["health_fraction"], 100 / 280)
        self.assertAlmostEqual(values["useful_resource_fraction"], 80 / 180)

    def test_disabled_and_null_thresholds(self):
        self.sim.encounter["retreat"]["enabled"] = False
        self.trigger()
        self.assertFalse(self.sim.retreat_active)
        self.sim.encounter["retreat"].update(enabled=True,health_threshold=None,useful_resource_threshold=None)
        retreat.check(self.sim)
        self.assertFalse(self.sim.retreat_active)

    def test_no_useful_resource_pool_does_not_trigger_by_itself(self):
        self.sim.retreat_resources = {c.id:set() for c in self.sim.retreat_party}
        self.sim.retreat_resource_baseline = 0
        retreat.check(self.sim)
        self.assertIsNone(retreat.metrics(self.sim)["useful_resource_fraction"])
        self.assertFalse(self.sim.retreat_active)

    def test_exhausted_withdrawal_pays_only_remaining_resource(self):
        self.trigger()
        self.gareth.stamina = 1
        self.sim.decide(self.gareth)
        self.assertEqual(self.gareth.action, "withdraw")
        self.assertEqual(self.gareth.stamina, 0)
        cost = next(e for e in self.sim.events if e["event"] == "resource_spent")
        self.assertEqual(cost["amount"], 1)
        self.sim.encounter["retreat"]["allow_exhausted_withdrawal"] = False
        self.sim.decide(self.elira)
        self.assertEqual(self.elira.phase, "Idle")

    def test_retreat_finishes_existing_preparation_and_recovery(self):
        positioning.refresh(self.sim)
        self.sim.decide(self.gareth)
        previous = (self.gareth.phase,self.gareth.action,self.gareth.phase_end_tick)
        self.trigger()
        self.assertEqual((self.gareth.phase,self.gareth.action,self.gareth.phase_end_tick),previous)

    def test_backline_escape_and_no_post_escape_actions(self):
        self.gareth.band = self.elira.band = "Backline"
        self.gareth.stamina = self.elira.stamina = 0
        report = self.sim.run()
        self.assertEqual(report["result"], "Successful Retreat")
        self.assertEqual(report["duration_seconds"], .5)
        for c in (self.gareth,self.elira):
            self.assertTrue(c.escaped)
            self.assertNotIn(c,self.sim.active())
            self.assertFalse(c.engagements or c.controlled_by)
            self.assertEqual(c.phase,"Idle")
            previous = len(self.sim.events)
            self.sim.decide(c)
            self.sim.execute(c)
            self.assertEqual(len(self.sim.events), previous)
            self.assertFalse(positioning.attack_access(self.sim.characters["brute"],c,self.sim.actions["ranged_attack"]))

    def test_final_escape_uses_same_failure_partial_and_clean_contest(self):
        for margin, expected in [(-5,"Failure"),(0,"Partial Success"),(5,"Clean Success")]:
            with self.subTest(margin=margin):
                self.setUp()
                self.elira.band = "Backline"
                self.elira.definition["engagement_capacity"] = 1
                enemy = self.sim.characters["skirmisher_2"]
                enemy.reached = "Backline"
                for key in enemy.definition["attributes"]:
                    enemy.definition["attributes"][key] = 50
                enemy.definition["skills"]["control"] = 50
                for key in self.sim.actions["withdraw"]["attribute_weights"]:
                    self.elira.definition["attributes"][key] = 50 + margin
                self.elira.definition["skills"]["movement"] = 50
                positioning.refresh(self.sim)
                self.elira.action,self.elira.target = "withdraw","elira"
                self.sim.execute(self.elira)
                self.assertEqual(self.elira.escaped, expected!="Failure")
                contests=[e for e in self.sim.events if e["event"]=="movement_contest" and e["actor"]=="elira"]
                self.assertEqual(contests[-1]["outcome"],expected)
                self.assertEqual(sum(e["event"]=="opportunity_attack" for e in self.sim.events),int(expected=="Partial Success"))

    def test_incapacitated_allies_do_not_prevent_success_but_wipe_is_defeat(self):
        self.gareth.incapacitated = True
        self.elira.escaped = True
        self.assertEqual(self.sim.completion(),"Successful Retreat")
        self.elira.escaped = False
        self.elira.incapacitated = True
        self.assertEqual(self.sim.completion(),"Defeat")

    def test_attack_prepared_against_escaped_target_cancels(self):
        enemy=self.sim.characters["brute"]
        enemy.action,enemy.target="heavy_attack","gareth"
        self.gareth.escaped=True
        self.sim.execute(enemy)
        self.assertFalse(any(e["event"]=="damage" for e in self.sim.events))
        self.assertTrue(any(e["event"]=="action_cancelled" for e in self.sim.events))

    def test_invalid_policy_is_rejected(self):
        for key,value in (("health_threshold",1.1),("trigger_mode","random"),("allow_exhausted_withdrawal","yes")):
            with self.subTest(key=key):
                self.setUp()
                self.sim.encounter["retreat"][key]=value
                with self.assertRaises(ValueError): self.sim.validate()


if __name__ == "__main__":
    unittest.main()
