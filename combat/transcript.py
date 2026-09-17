"""Human-readable presentation of recorded events; no combat rules live here."""


def number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def render_transcript(events, report, definitions, actions, *, verbose=False):
    characters = {character["id"]: character for character in definitions}
    lines = [report["encounter"], "=" * 64]
    preparation_costs = {}
    defense_costs = {}
    defenses = {}

    def name(actor):
        return characters[actor]["name"]

    def action_name(action):
        return actions[action]["name"]

    def heading(event, message):
        lines.extend(["", f"{event['timestamp']:5.1f}s  {message}"])

    def detail(message):
        lines.append(f"        {message}")

    def resource_line(event):
        return (f"{event['resource'].title()}: {number(event['before'])} -> "
                f"{number(event['after'])} (spent {number(event['amount'])})")

    def quality_line(label, values):
        detail(f"{label}: capability {number(values['capability'])} + "
               f"skill modifier {number(values['skill_modifier'])} + "
               f"state modifier {number(values['state_modifier'])} = {number(values['total'])}")

    for event in events:
        kind, actor = event["event"], event["actor"]
        if kind == "encounter_start":
            for character in definitions:
                detail(f"{character['name']}: Health {number(character['maximum_health'])}, "
                       f"Stamina {number(character['maximum_stamina'])}, Mana {number(character['maximum_mana'])}")
            if verbose:
                detail("Same-time resolution: " + " then ".join(name(key) for key in event["order"]))
        elif kind == "resource_spent":
            if event["reason"] == "preparation":
                preparation_costs[actor] = event
            elif event["reason"] == "opportunity attack":
                detail(f"{name(actor)} {resource_line(event)} for Opportunity Attack.")
            else:
                defense_costs[actor] = event
        elif kind == "preparation_start":
            movement = actions[event['action']]["category"] == "movement"
            heading(event, f"{name(actor)} prepares {action_name(event['action'])} -> "
                    f"{actions[event['action']]['direction'] if movement else name(event['target'])} ({number(event['duration'])}s)")
            cost = preparation_costs.pop(actor, None)
            if cost:
                detail(resource_line(cost))
        elif kind == "defense_decision":
            defenses[actor] = event
        elif kind == "damage":
            target = event["target"]
            defense = event["active_defense"]
            defense_label = action_name(defense) if defense != "none" else "No active defense"
            verb = "attacks" if event["final_damage"] == 0 else "hits"
            heading(event, f"{name(actor)} {verb} {name(target)} with {action_name(event['action'])}"
                    f" — {event['outcome'].upper()}")
            contest = f"Attack Quality {number(event['attack_quality']['total'])}"
            if event["defense_quality"] is not None:
                contest += f" vs {defense_label} Quality {number(event['defense_quality']['total'])}"
            else:
                contest += " (Brace: no Quality contest)" if defense == "brace" else " (unopposed)"
            detail(contest)
            after_defense = event["incoming_damage"] - event["active_defense_reduction"]
            detail(f"Damage: {number(event['raw_damage'])} raw"
                   f" -> {number(after_defense)} after {defense_label if defense != 'none' else 'active defense'}"
                   f" -> {number(event['final_damage'])} after armor")
            detail(f"{name(target)} Health: {number(event['health_before'])} -> {number(event['health_after'])}")
            if defense in {"dodge", "parry"}:
                if event["outcome"] in {"Strong Defense", "Defense"}:
                    detail(f"{defense_label} avoids all damage.")
                elif event["outcome"] == "Contested":
                    detail(f"{defense_label}: partial contact.")
                else:
                    detail(f"{defense_label} fails; full raw damage reaches armor.")
            if event["final_damage"] > event["health_lost"] + 1e-9:
                detail(f"Health lost: {number(event['health_lost'])}; remaining damage is overkill.")
            choice = defenses.pop(target, None)
            cost = defense_costs.pop(target, None)
            if cost:
                detail(f"{name(target)} {resource_line(cost)} for {defense_label}.")
                detail(f"{defense_label} prevents {number(event['active_defense_reduction'])} damage."
                       if event["active_defense_reduction"] else f"{defense_label} prevents no damage.")
            elif choice:
                detail(f"No active defense: {choice['reason']}.")
            if verbose:
                quality_line("Attack Quality calculation", event["attack_quality"])
                if event["defense_quality"] is not None:
                    quality_line("Defense Quality calculation", event["defense_quality"])
                detail(f"Base power {number(event['base_power'])}; raw damage {number(event['raw_damage'])}.")
                detail(f"Protection rating {number(event['protection_rating'])}: "
                       f"{event['protection_mitigation']:.1%} mitigation removes {number(event['protection_reduction'])} damage.")
                if choice:
                    detail(f"Defense choice: {choice['reason']}; available Stamina {number(choice['available_stamina'])}.")
                    for candidate in choice["candidates"]:
                        components = ", ".join(f"{key.replace('_', ' ')} {number(value)}"
                                               for key, value in candidate["components"].items())
                        detail(f"{action_name(candidate['defense'])}: score {number(candidate['score'])} "
                               f"({components}); cost {number(candidate['cost'])}; {candidate['outcome']}.")
                        if candidate["quality"] is not None:
                            quality_line(f"{action_name(candidate['defense'])} candidate Quality", candidate["quality"])
                    for rejected in choice["rejected"]:
                        detail(f"Rejected {action_name(rejected['defense'])}: {rejected['reason']} "
                               f"(cost {number(rejected['cost'])}).")
        elif kind == "stagger":
            heading(event, f"{name(actor)} is STAGGERED by {name(event['source'])}'s Parry.")
            detail(f"Recovery extended by {number(event['added_recovery_seconds'])}s.")
        elif kind == "stagger_ignored":
            heading(event, f"{name(actor)}'s Opportunity Attack is strongly parried.")
            detail(event["reason"] + ".")
        elif kind in {"engagement_start", "engagement_end"}:
            verb = "engages" if kind == "engagement_start" else "releases"
            heading(event, f"{name(actor)} {verb} {name(event['target'])}.")
            if kind == "engagement_start":
                detail(f"Automatic control; Engagement Capacity {event['capacity']}.")
        elif kind == "position_state":
            heading(event, f"{name(actor)}: {', '.join(event['states']) or 'inactive'}.")
            detail(f"Own band: {event['band']}; opposing band reached: {event['reached']}.")
        elif kind == "movement_contest":
            heading(event, f"{name(actor)} attempts {event['movement_kind']} past {name(event['target'])} — {event['outcome'].upper()}")
            detail(f"Movement Quality {number(event['mover_quality']['total'])} vs Control Quality "
                   f"{number(event['control_quality']['total'])}; difference {number(event['margin'])}.")
            if verbose:
                quality_line("Movement", event["mover_quality"])
                quality_line("Control", event["control_quality"])
        elif kind == "movement":
            heading(event, f"{name(actor)} moves — {event['outcome'].upper()}")
            detail(f"Own band: {event['from_band']} -> {event['band']}; "
                   f"opposing band reached: {event['from_reached']} -> {event['reached']}.")
        elif kind == "movement_failed":
            heading(event, f"{name(actor)} stays in place: {event['reason']}.")
        elif kind == "opportunity_attack":
            heading(event, f"{name(actor)} makes an OPPORTUNITY ATTACK -> {name(event['target'])}.")
        elif kind == "opportunity_skipped":
            heading(event, f"{name(actor)} cannot make an Opportunity Attack: {event['reason']}.")
        elif kind == "incapacitated":
            heading(event, f"{name(actor)} is INCAPACITATED (not dead).")
            if event.get("cancelled_action"):
                detail(f"{action_name(event['cancelled_action'])} stopped during {event['cancelled_phase'].lower()}.")
        elif kind == "idle":
            heading(event, f"{name(actor)} waits: {event['reason']}.")
            for rejected in event.get("rejected", []):
                target_label = f" -> {name(rejected['target'])}" if "target" in rejected else ""
                detail(f"{action_name(rejected['action'])}{target_label}: {rejected['reason']} "
                       f"({number(rejected['available'])} available).")
        elif kind == "action_cancelled":
            heading(event, f"{name(actor)}'s action is cancelled: {event['reason']}.")
        elif kind == "encounter_complete":
            heading(event, f"{event['result'].upper()} — {event['reason']}.")
        elif verbose and kind == "decision":
            heading(event, f"{name(actor)} chooses {action_name(event['selected']['action'])} "
                    f"-> {name(event['selected']['target'])}")
            detail(event["reason"] + ".")
            for candidate in event["candidates"]:
                components = ", ".join(f"{key.replace('_', ' ')} {number(value)}"
                                       for key, value in candidate["components"].items())
                detail(f"{action_name(candidate['action'])} -> {name(candidate['target'])}: "
                       f"score {number(candidate['score'])} ({components})")
            for rejected in event["rejected"]:
                target_label = f" -> {name(rejected['target'])}" if "target" in rejected else ""
                detail(f"Rejected {action_name(rejected['action'])}{target_label}: {rejected['reason']} "
                       f"({number(rejected['available'])} available).")
        elif verbose and kind == "execution":
            heading(event, f"{name(actor)} executes {action_name(event['action'])}.")
        elif verbose and kind == "recovery_start":
            heading(event, f"{name(actor)} recovers for {number(event['duration'])}s.")
        elif verbose and kind == "recovery_end":
            heading(event, f"{name(actor)} finishes recovery.")

    lines.extend(["", f"RESULT: {report['result']} at {report['duration_seconds']:.1f}s", ""])
    rows = [["Combatant", "Health left", "Stamina left", "Mana left", "HP lost", "Stamina spent"]]
    for character in report["combatants"]:
        initial = characters[character["id"]]
        rows.append([character["name"],
                     *[f"{number(character[r])} / {number(initial[f'maximum_{r}'])}" for r in ("health", "stamina", "mana")],
                     number(character["health_lost"]), number(character["stamina_spent"])])
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for index, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
        if index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines) + "\n"
