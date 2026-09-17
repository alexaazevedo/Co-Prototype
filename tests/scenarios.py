"""Small controlled formation fixture, independent of the user's formation edits."""
from copy import deepcopy
from pathlib import Path
import json

from combat.engine import Simulation, load_simulation


def duel_fixture():
    root = Path(__file__).resolve().parent.parent / "config"
    balance = json.loads((root / "balance.json").read_text(encoding="utf-8"))
    actions = json.loads((root / "actions.json").read_text(encoding="utf-8"))
    for key in ("dodge", "parry"):
        actions[key]["outcome_reductions"] = {"Strong Defense":1,"Defense":1,"Contested":.5,"Hit":0,"Strong Hit":0}
    characters = []
    for key, team, hp, stamina, protection, attributes, skills, attack in (
        ("gareth", "party", 180, 100, 55, (60,70,55), (60,75), "sword_attack"),
        ("brute", "enemy", 220, 90, 20, (75,35,35), (40,15), "heavy_attack")):
        characters.append({"id":key,"name":key.title(),"team":team,"band":"Frontline",
            "maximum_health":hp,"maximum_stamina":stamina,"maximum_mana":0,
            "physical_protection":protection,"magical_protection":5,"engagement_capacity":2 if key=="gareth" else 1,
            "attributes":dict(zip(("maximum_force","grip_control","gross_coordination"),attributes),
                              balance=attributes[2],reflexes=attributes[2]),
            "skills":{"melee":skills[0],"block":skills[1],"dodge":50 if key=="gareth" else 25,"parry":skills[0]},
            "actions":[attack],"defenses":["block","dodge","parry","brace"],
            "tactics":{"defense_preferences":{"block":10 if key=="gareth" else 0},"action_bonuses":{},
                       "target_preferences":{},"resource_penalty_per_point":.2 if key=="gareth" else 0}})
    return Simulation(balance, actions, {"name":"Controlled duel fixture","party_team":"party","combatants":characters})


def formation_fixture():
    base = duel_fixture()
    actions = deepcopy(base.actions)
    # Fixed weights keep arithmetic regression checks separate from live tuning.
    actions["block"]["attribute_weights"] = {"grip_control": .6, "maximum_force": .4}
    actions["parry"]["attribute_weights"] = {"grip_control": .5, "gross_coordination": .3, "reflexes": .2}
    actions["ranged_attack"]["attribute_weights"] = {"maximum_force": .4, "grip_control": .3, "gross_coordination": .3}
    gareth, brute = [deepcopy(base.characters[key].definition) for key in ("gareth", "brute")]
    for character in (gareth, brute):
        character["attributes"]["situational_awareness"] = 55 if character["id"] == "gareth" else 35
        character["skills"].update(control=60 if character["id"] == "gareth" else 40, movement=50)
        character["opportunity_attack"] = character["actions"][0]
        character["tactics"].update(engaged_target_bonus=10, penetrating_target_bonus=20)
    gareth["control_priority"] = 10
    gareth["actions"] = ["sword_attack", "withdraw"]
    brute.update(engagement_capacity=0, engagement_priority=20)
    elira = deepcopy(gareth)
    elira.update(id="elira", name="Elira", band="Midline", maximum_health=100,
                 maximum_stamina=80, maximum_mana=50, physical_protection=20,
                 engagement_capacity=0, control_priority=0, actions=["ranged_attack"])
    elira.pop("opportunity_attack", None)
    elira["attributes"] = {"maximum_force":45,"grip_control":50,"gross_coordination":55,
                           "balance":55,"reflexes":55,"situational_awareness":60}
    elira["skills"] = {"ranged":50,"block":40,"dodge":50,"parry":50,"control":50,"movement":50}
    elira["tactics"]["defense_preferences"] = {}
    enemies = []
    for i in (1, 2):
        enemy = deepcopy(brute)
        enemy.update(id=f"skirmisher_{i}", name=f"Skirmisher {i}", maximum_health=65,
                     maximum_stamina=70, physical_protection=10, engagement_priority=10-i,
                     actions=["quick_attack", "breakthrough", "withdraw"], opportunity_attack="quick_attack")
        enemy["attributes"] = {"maximum_force":45,"grip_control":55,"gross_coordination":64,
                               "balance":64,"reflexes":64,"situational_awareness":50}
        enemy["skills"] = {"melee":60,"block":35,"dodge":60,"parry":55,"control":50,"movement":60}
        enemies.append(enemy)
    return Simulation(base.balance, actions, {"name":"Controlled formation fixture", "party_team":"party",
                                              "positioning":True, "combatants":[gareth, elira, brute, *enemies]})
