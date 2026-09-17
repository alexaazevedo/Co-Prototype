"""Party retreat policy, with encounter-owned thresholds and fixed baselines."""


def validate(sim):
    policy = sim.encounter.get("retreat", {})
    allowed = {"enabled", "health_threshold", "useful_resource_threshold", "trigger_mode", "allow_exhausted_withdrawal"}
    if not isinstance(policy, dict) or set(policy) - allowed:
        raise ValueError("Unknown retreat setting")
    for key in ("enabled", "allow_exhausted_withdrawal"):
        if key in policy and not isinstance(policy[key], bool):
            raise ValueError(f"retreat.{key} must be a boolean")
    for key in ("health_threshold", "useful_resource_threshold"):
        value = policy.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1):
            raise ValueError(f"retreat.{key} must be null or a fraction from zero to one")
    if policy.get("trigger_mode", "either") not in {"either", "both"}:
        raise ValueError("retreat.trigger_mode must be either or both")
    if policy.get("enabled", False):
        if not sim.positioning:
            raise ValueError("Retreat requires positioning")
        for character in sim.characters.values():
            if character.definition["team"] == sim.encounter["party_team"]:
                if not any(is_withdraw(sim.actions[key]) for key in character.definition["actions"]):
                    raise ValueError(f"Retreating party member {character.id} needs a Withdraw action")


def is_withdraw(action):
    return action["category"] == "movement" and action["direction"] == "withdraw"


def useful_resources(character, actions, balance):
    useful = set()
    for key in character.definition["actions"]:
        action = actions[key]
        if action["resource_cost"] > 0:
            useful.add(action["resource_type"])
    for key in character.definition["defenses"]:
        if (key == "block" and balance["block_stamina_per_prevented_damage"] > 0
                or actions[key].get("stamina_cost", 0) > 0):
            useful.add("stamina")
    return useful


def initialize(sim):
    sim.retreat_active = False
    sim.retreat_party = [c for c in sim.characters.values() if c.definition["team"] == sim.encounter["party_team"]]
    sim.retreat_resources = {c.id: useful_resources(c, sim.actions, sim.balance) for c in sim.retreat_party}
    sim.retreat_health_baseline = sum(c.definition["maximum_health"] for c in sim.retreat_party)
    sim.retreat_resource_baseline = sum(c.definition[f"maximum_{resource}"] for c in sim.retreat_party
                                       for resource in sim.retreat_resources[c.id])


def metrics(sim):
    survivors = [c for c in sim.retreat_party if not c.incapacitated]
    health = sum(c.health for c in survivors)
    resources = sum(getattr(c, resource) for c in survivors for resource in sim.retreat_resources[c.id])
    return {"health_fraction": health / sim.retreat_health_baseline,
            "useful_resource_fraction": resources / sim.retreat_resource_baseline if sim.retreat_resource_baseline else None,
            "health_remaining": health, "health_baseline": sim.retreat_health_baseline,
            "useful_resources_remaining": resources, "useful_resources_baseline": sim.retreat_resource_baseline}


def check(sim):
    policy = sim.encounter.get("retreat", {})
    if sim.retreat_active or not policy.get("enabled", False) or sim.completion():
        return
    values = metrics(sim)
    checks = {}
    for setting, metric in (("health_threshold", "health_fraction"),
                            ("useful_resource_threshold", "useful_resource_fraction")):
        if policy.get(setting) is not None and values[metric] is not None:
            checks[setting] = values[metric] <= policy[setting]
    triggered = bool(checks) and (any(checks.values()) if policy.get("trigger_mode", "either") == "either" else all(checks.values()))
    if not triggered:
        return
    sim.retreat_active = True
    for character in sim.retreat_party:
        if not character.incapacitated and not character.escaped:
            character.retreating = True
            if character.phase == "Idle":
                character.phase_end_tick = 0  # Log a newly blocked retreat attempt if needed.
    sim.log("retreat_triggered", trigger_mode=policy.get("trigger_mode", "either"), checks=checks,
            thresholds={key: policy.get(key) for key in checks}, **values)


def action_cost(sim, character, action):
    cost = action["resource_cost"]
    if character.retreating and is_withdraw(action) and sim.encounter.get("retreat", {}).get("allow_exhausted_withdrawal", False):
        return min(cost, getattr(character, action["resource_type"]))
    return cost
