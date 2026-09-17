"""Band access and hostile control, without coordinates or fixed slots."""

BANDS = ("Frontline", "Midline", "Backline")


def attack_access(actor, target, action):
    if action["range_requirement"] == "ranged":
        return (not actor.incapacitated and not target.incapacitated
                and actor.definition["team"] != target.definition["team"])
    return can_access(actor, target)


def can_access(actor, target):
    """Melee access determines engagements and Protected/Exposed, even for archers."""
    if actor.incapacitated or target.incapacitated or actor.definition["team"] == target.definition["team"]:
        return False
    if actor.reached != "Frontline":
        return target.reached == "Frontline" and target.band == actor.reached
    if target.reached != "Frontline":
        return actor.band == target.reached
    return actor.band == target.band == "Frontline"


def controllers(sim, mover):
    return sorted((c for c in sim.active() if c.definition["team"] != mover.definition["team"]
                   and c.reached == "Frontline" and c.definition["engagement_capacity"] > 0
                   and can_access(c, mover)),
                  key=lambda c: (-c.definition.get("control_priority", 0), c.id))


def refresh(sim):
    """Preserve legal engagements, then fill free capacity in stable priority order."""
    if not sim.positioning:
        return
    old = {(c.id, other) for c in sim.characters.values() for other in c.engagements}
    for c in sim.characters.values():
        c.engagements.clear()
        c.controlled_by.clear()
    movers = sorted(sim.active(), key=lambda c: (-c.definition.get("engagement_priority", 0), c.id))
    # Preserve all legal assignments before newcomers compete for remaining slots.
    for mover in movers:
        for controller in controllers(sim, mover):
            if (controller.id, mover.id) in old and len(controller.engagements) < controller.definition["engagement_capacity"]:
                controller.engagements.add(mover.id)
                mover.controlled_by.add(controller.id)
                break
    for mover in movers:
        if mover.controlled_by:
            continue
        choices = controllers(sim, mover)
        for controller in choices:
            if len(controller.engagements) < controller.definition["engagement_capacity"]:
                controller.engagements.add(mover.id)
                mover.controlled_by.add(controller.id)
                break
    new = {(c.id, other) for c in sim.characters.values() for other in c.engagements}
    for controller, mover in sorted(old - new):
        sim.log("engagement_end", controller, target=mover)
    for controller, mover in sorted(new - old):
        sim.log("engagement_start", controller, target=mover,
                capacity=sim.characters[controller].definition["engagement_capacity"],
                reason="automatic control within capacity")
    for character in sorted(sim.characters.values(), key=lambda c: c.id):
        states = set() if character.incapacitated else {
            "Exposed" if any(can_access(enemy, character) for enemy in sim.active()) else "Protected"}
        if states != character.positional_states:
            character.positional_states = states
            sim.log("position_state", character.id, states=sorted(states), band=character.band,
                    reached=character.reached)


def destination(character, direction):
    own, reached = BANDS.index(character.band), BANDS.index(character.reached)
    if direction == "advance":
        if own > 0:
            return BANDS[own - 1], "Frontline"
        if reached < 2:
            return "Frontline", BANDS[reached + 1]
    elif direction == "withdraw":
        if reached > 0:
            return "Frontline", BANDS[reached - 1]
        if own < 2:
            return BANDS[own + 1], "Frontline"
    return None


def movement_reason(sim, actor, action):
    if not sim.positioning:
        return "positioning disabled in this encounter"
    if destination(actor, action["direction"]) is None:
        return "already at outermost band"
    if action["movement_kind"] == "breakthrough" and actor.controlled_by:
        return "actively engaged; disengage before bypassing control"
    if action["movement_kind"] == "move" and (actor.controlled_by or actor.engagements):
        return "actively engaged; use Disengage to leave"
    if action["movement_kind"] == "disengage" and not (actor.controlled_by or actor.engagements):
        return "no active engagement to leave"
    if action["movement_kind"] == "breakthrough":
        next_band = destination(actor, action["direction"])[1]
        if actor.band == "Frontline" and not any(
                c.definition["team"] != actor.definition["team"] and c.reached == "Frontline"
                and BANDS.index(c.band) >= BANDS.index(next_band) for c in sim.active()):
            return "no hostile target in deeper bands"
    return None


def execute_movement(sim, actor, action_key):
    from .engine import quality

    action = sim.actions[action_key]
    reason = movement_reason(sim, actor, action)
    if reason:
        sim.log("action_cancelled", actor.id, reason=f"{reason}; cost not refunded")
        return
    before = (actor.band, actor.reached)
    after = destination(actor, action["direction"])
    # Leaving an active engagement uses the same contest, including when the
    # character was the controller. Crossing uncontrolled space needs no roll.
    opposed = {c.id: c for c in controllers(sim, actor)}
    if action["movement_kind"] == "disengage":
        opposed.update({key: sim.characters[key] for key in actor.engagements | actor.controlled_by
                        if not sim.characters[key].incapacitated})
    mover_quality = quality(actor, action, sim.balance)
    partial = []
    failed = False
    for controller in sorted(opposed.values(), key=lambda c: (-c.definition.get("control_priority", 0), c.id)):
        control_quality = quality(controller, sim.balance["control_quality"], sim.balance)
        margin = mover_quality["total"] - control_quality["total"]
        boundary = sim.balance["movement_clear_margin"]
        outcome = "Clean Success" if margin >= boundary else "Failure" if margin <= -boundary else "Partial Success"
        sim.log("movement_contest", actor.id, target=controller.id, action=action_key,
                movement_kind=action["movement_kind"], mover_quality=mover_quality,
                control_quality=control_quality, margin=margin, outcome=outcome)
        failed |= outcome == "Failure"
        if outcome == "Partial Success":
            partial.append(controller)
    if failed:
        sim.log("movement_failed", actor.id, action=action_key, reason="hostile controller won clearly")
        return
    for controller in partial:
        sim.opportunity_attack(controller, actor)
        if actor.incapacitated:
            sim.log("movement_failed", actor.id, action=action_key, reason="incapacitated by Opportunity Attack")
            return
    actor.band, actor.reached = after
    sim.log("movement", actor.id, action=action_key, from_band=before[0], from_reached=before[1],
            band=actor.band, reached=actor.reached,
            outcome="Partial Success" if partial else "Clean Success" if opposed else "Unopposed")
    refresh(sim)
