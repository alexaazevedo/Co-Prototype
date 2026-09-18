"""Explicit combat rules; content and tuning live in JSON."""

from dataclasses import dataclass, field
from decimal import Decimal
import json
from pathlib import Path
from . import positioning, retreat


@dataclass
class Character:
    definition: dict
    health: float = field(init=False)
    stamina: float = field(init=False)
    mana: float = field(init=False)
    phase: str = "Idle"
    action: str | None = None
    target: str | None = None
    phase_end_tick: int = 0
    stagger_end_tick: int = 0
    pending_recovery_extension_ticks: int = 0
    incapacitated: bool = False
    retreating: bool = False
    escaped: bool = False
    band: str = field(init=False)
    reached: str = "Frontline"
    engagements: set = field(default_factory=set)
    controlled_by: set = field(default_factory=set)
    positional_states: set = field(default_factory=set)

    def __post_init__(self):
        self.band = self.definition["band"]
        for resource in ("health", "stamina", "mana"):
            setattr(self, resource, float(self.definition[f"maximum_{resource}"]))

    @property
    def id(self):
        return self.definition["id"]


def quality(character, template, balance):
    weights = template["attribute_weights"]
    capability = sum(character.definition["attributes"][key] * weight
                     for key, weight in weights.items()) / sum(weights.values())
    skill = character.definition["skills"][template["skill"]]
    skill_modifier = (skill - balance["skill_baseline"]) * balance["skill_scale"]
    return {"capability": capability, "skill": skill, "skill_modifier": skill_modifier,
            "state_modifier": 0, "total": capability + skill_modifier}


def outcome_for(margin, balance):
    for band in balance["outcomes"]:
        threshold = band["minimum_defender_margin"]
        if threshold is None or (margin > threshold if band.get("exclusive") else margin >= threshold):
            return band
    raise ValueError("Outcome configuration needs a catch-all band")


class Simulation:
    def __init__(self, balance, actions, encounter):
        self.balance, self.actions, self.encounter = balance, actions, encounter
        self.tick = 0
        self.events = []
        self.result = None
        self.positioning = encounter.get("positioning", False)
        self.characters = {d["id"]: Character(d) for d in encounter["combatants"]}
        self.validate()
        retreat.initialize(self)

    def ticks(self, seconds):
        ratio = Decimal(str(seconds)) / Decimal(str(self.balance["tick_seconds"]))
        if ratio != ratio.to_integral_value():
            raise ValueError(f"Duration {seconds} must be a multiple of tick_seconds")
        return int(ratio)

    def validate_effects(self, action):
        effects = action.get("effects", [])
        if not isinstance(effects, list):
            raise ValueError("Action effects must be a list")
        outcomes = {band["name"] for band in self.balance["outcomes"]}
        required = {"type", "outcome", "recipient", "duration_seconds"}
        for effect in effects:
            if not isinstance(effect, dict) or set(effect) != required:
                raise ValueError("Effects require type, outcome, recipient and duration_seconds")
            if effect["type"] != "stagger":
                raise ValueError(f"Unsupported effect type: {effect['type']}")
            if effect["outcome"] not in outcomes:
                raise ValueError("Unknown effect outcome")
            if effect["recipient"] not in {"attacker", "defender"}:
                raise ValueError("Effect recipient must be attacker or defender")
            duration = effect["duration_seconds"]
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
                raise ValueError("Effect duration must be positive")
            self.ticks(duration)

    def validate(self):
        b = self.balance
        if b["tick_seconds"] <= 0 or b["max_duration_seconds"] <= 0 or b["protection_k"] <= 0 or b["capability_baseline"] <= 0:
            raise ValueError("Clock, duration, K and capability baseline must be positive")
        if b["block_stamina_per_prevented_damage"] < 0:
            raise ValueError("Block cost cannot be negative")
        self.ticks(b["max_duration_seconds"])
        definitions = self.encounter["combatants"]
        if len(self.characters) != len(definitions) or len(definitions) < 2:
            raise ValueError("Encounter requires at least two characters with unique IDs")
        if len({f.definition["team"] for f in self.characters.values()}) != 2:
            raise ValueError("Encounter requires exactly two opposing teams")
        if self.encounter["party_team"] not in {f.definition["team"] for f in self.characters.values()}:
            raise ValueError("Party team is missing")
        for f in self.characters.values():
            d = f.definition
            if f.health <= 0 or min(f.stamina, f.mana, d["physical_protection"], d["magical_protection"]) < 0:
                raise ValueError("Invalid starting resources or protection")
            if d["band"] not in positioning.BANDS:
                raise ValueError("Unknown positional band")
            if not self.positioning and (d["band"] != "Frontline" or len(definitions) != 2):
                raise ValueError("Enable positioning for formation encounters")
            if d["engagement_capacity"] < 0 or not isinstance(d["engagement_capacity"], int):
                raise ValueError("Engagement Capacity must be a nonnegative integer")
            if self.positioning:
                quality(f, b["control_quality"], b)
                if b["movement_clear_margin"] <= 0:
                    raise ValueError("Movement boundary must be positive")
                opportunity = d.get("opportunity_attack")
                if opportunity and (opportunity not in d["actions"] or self.actions[opportunity]["category"] != "physical_attack"
                                    or self.actions[opportunity]["range_requirement"] not in {"duel", "melee"}):
                    raise ValueError("Opportunity Attack must reference an available melee physical attack")
            for key in d["actions"] + d["defenses"]:
                a = self.actions[key]
                conditions = a.get("usage_conditions", {})
                if not isinstance(conditions, dict) or set(conditions) - {"prevent_when_exposed"}:
                    raise ValueError("Unknown action usage condition")
                if "prevent_when_exposed" in conditions and not isinstance(conditions["prevent_when_exposed"], bool):
                    raise ValueError("prevent_when_exposed must be a boolean")
                self.validate_effects(a)
                if a["category"] == "defense":
                    if key not in {"block", "dodge", "parry", "brace"}:
                        raise ValueError("Unknown active defense")
                    if key != "block" and a["stamina_cost"] < 0:
                        raise ValueError("Defense cost cannot be negative")
                    if key == "brace":
                        if not 0 <= a["damage_reduction"] < 1:
                            raise ValueError("Brace must reduce, but never negate, damage")
                        continue
                    if key in {"dodge", "parry"}:
                        for band in b["outcomes"]:
                            if not 0 <= a["outcome_reductions"][band["name"]] <= 1:
                                raise ValueError("Defense reductions must be between zero and one")
                    if key == "parry":
                        if a["difficult_quality_penalty"] > 0:
                            raise ValueError("Invalid Parry difficulty penalty")
                weights = a["attribute_weights"]
                if not weights or any(w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
                    raise ValueError("Attribute weights must be nonnegative with a positive total")
                quality(f, a, b)  # Also verifies referenced attributes and skills.
                if a["category"] == "defense":
                    continue
                if not isinstance(a.get("interruptible"), bool):
                    raise ValueError("Actions must define interruptible as a boolean")
                if a["category"] == "movement":
                    if a["direction"] not in {"advance", "withdraw"} or a["movement_kind"] not in {"breakthrough", "withdraw", "move"}:
                        raise ValueError("Invalid movement direction or kind")
                elif a["category"] != "physical_attack" or a["target_type"] != "enemy" or a["range_requirement"] not in {"duel", "melee", "ranged"}:
                    raise ValueError("Only physical attacks and band movement are implemented")
                if set(a["allowed_defenses"]) - {"block", "dodge", "parry", "brace"}:
                    raise ValueError("Unknown allowed defense")
                if a.get("parryability", "parryable") not in {"parryable", "difficult", "not_parryable"}:
                    raise ValueError("Unknown parryability")
                if a["resource_type"] not in ("stamina", "mana") or min(a["resource_cost"], a["base_power"]) < 0:
                    raise ValueError("Invalid action resource or power")
                if self.ticks(a["preparation_seconds"]) < 1 or self.ticks(a["recovery_seconds"]) < 1:
                    raise ValueError("Preparation and recovery must each take at least one tick")
        retreat.validate(self)

    def log(self, event, actor=None, **data):
        self.events.append({"timestamp": float(Decimal(self.tick) * Decimal(str(self.balance["tick_seconds"]))),
                            "event": event, "actor": actor, **data})

    def active(self):
        return [f for f in self.characters.values() if not f.incapacitated and not f.escaped]

    def completion(self):
        party = self.encounter["party_team"]
        alive = self.active()
        survivors = [f for f in self.characters.values() if f.definition["team"] == party and not f.incapacitated]
        if not survivors:
            return "Defeat"
        if all(f.escaped for f in survivors):
            return "Successful Retreat"
        if not any(f.definition["team"] != party for f in alive):
            return "Victory"
        return None

    def action_block_reason(self, actor, action):
        if action.get("usage_conditions", {}).get("prevent_when_exposed", False):
            if any(positioning.can_access(enemy, actor) for enemy in self.active()):
                return "actor is Exposed; action requires protection from melee access"
        return None

    def decide(self, actor):
        if actor.incapacitated or actor.escaped or self.tick < actor.stagger_end_tick:
            return
        candidates, rejected = [], []
        tactics = actor.definition["tactics"]
        for key in actor.definition["actions"]:
            action = self.actions[key]

            available = getattr(actor, action["resource_type"])
            if actor.retreating and not retreat.is_withdraw(action):
                rejected.append({"action": key, "reason": "party retreat active; prioritize Withdraw", "available": available})
                continue
            if retreat.is_withdraw(action) and not actor.retreating:
                rejected.append({"action": key, "reason": "Withdraw is reserved for active retreat", "available": available})
                continue
            cost = retreat.action_cost(self, actor, action)
            reason = self.action_block_reason(actor, action)
            if reason:
                rejected.append({"action": key, "reason": reason, "available": available})
                continue
            if available + 1e-9 < cost:
                rejected.append({"action": key, "reason": "insufficient resource", "available": available})
                continue

            movement = action["category"] == "movement"
            if movement:
                reason = positioning.movement_reason(self, actor, action)
                if reason:
                    rejected.append({"action": key, "reason": reason, "available": available})
                    continue
            targets = [actor] if movement else sorted(self.active(), key=lambda f: f.id)
            for target in targets:
                if not movement and target.definition["team"] == actor.definition["team"]:
                    continue
                if not movement and self.positioning and not positioning.attack_access(actor, target, action):
                    rejected.append({"action": key, "target": target.id, "reason": f"target outside {action['range_requirement']} access",
                                     "available": available})
                    continue
                parts = {"base_usefulness": action["base_usefulness"],
                         "tactical_bonus": tactics["action_bonuses"].get(key, 0),
                         "target_preference": tactics["target_preferences"].get(target.id, 0),
                         "resource_penalty": -cost * tactics["resource_penalty_per_point"]}
                if self.positioning and not movement:
                    parts["engagement_bonus"] = tactics.get("engaged_target_bonus", 0) if target.id in actor.controlled_by | actor.engagements else 0
                    parts["penetrating_threat_bonus"] = tactics.get("penetrating_target_bonus", 0) if target.reached != "Frontline" else 0
                candidates.append({"action": key, "target": target.id, "score": sum(parts.values()), "components": parts})
        candidates.sort(key=lambda c: (-c["score"], c["action"], c["target"]))
        if not candidates:
            # Log changes to idle availability once, rather than on every tick.
            if actor.phase_end_tick != -1:
                self.log("idle", actor.id, reason="no affordable legal action", rejected=rejected)
                actor.phase_end_tick = -1
            return
        selected = candidates[0]
        self.log("decision", actor.id, selected=selected, candidates=candidates, rejected=rejected,
                 reason="highest utility; ties use action ID then target ID")
        actor.action, actor.target = selected["action"], selected["target"]
        a = self.actions[actor.action]
        self.spend(actor, a["resource_type"], retreat.action_cost(self, actor, a), "preparation", actor.action)
        actor.phase = "Preparing"
        actor.phase_end_tick = self.tick + self.ticks(a["preparation_seconds"])
        self.log("preparation_start", actor.id, action=actor.action, target=actor.target,
                 duration=a["preparation_seconds"], ends_at_tick=actor.phase_end_tick)

    def spend(self, actor, resource, amount, reason, action):
        before = getattr(actor, resource)
        if before + 1e-9 < amount:
            raise ValueError("Cannot spend an unaffordable resource cost")
        setattr(actor, resource, max(0.0, before - amount))
        self.log("resource_spent", actor.id, action=action, resource=resource, amount=amount,
                 before=before, after=getattr(actor, resource), reason=reason)

    def apply_stagger(self, source, target, source_action, duration_seconds, *, suppressed_reason=None):
        """Apply the one supported temporary effect according to the target's current phase."""
        phase = target.phase
        common = {"source": source.id, "source_action": source_action,
                  "duration": duration_seconds, "target_phase": phase}
        if suppressed_reason:
            self.log("stagger_ignored", target.id, reason=suppressed_reason, **common)
            return False
        if self.tick < target.stagger_end_tick:
            self.log("stagger_ignored", target.id, reason="already_staggered",
                     active_until_tick=target.stagger_end_tick, **common)
            return False

        duration_ticks = self.ticks(duration_seconds)
        target.stagger_end_tick = self.tick + duration_ticks
        details = {**common, "ends_at_tick": target.stagger_end_tick}
        if phase == "Preparing":
            previous_end_tick = target.phase_end_tick
            target.phase_end_tick += duration_ticks
            details.update(consequence="preparation_extended", delayed_action=target.action,
                           added_preparation_seconds=duration_seconds,
                           previous_preparation_end_tick=previous_end_tick,
                           preparation_ends_at_tick=target.phase_end_tick)
        elif phase == "Recovering":
            target.phase_end_tick += duration_ticks
            details.update(consequence="recovery_extended", added_recovery_seconds=duration_seconds,
                           recovery_ends_at_tick=target.phase_end_tick)
        elif phase == "Executing":
            target.pending_recovery_extension_ticks = duration_ticks
            details.update(consequence="recovery_extended", added_recovery_seconds=duration_seconds)
        else:
            details["consequence"] = "action_lockout"
        self.log("stagger", target.id, **details)
        return True

    def apply_effects(self, effects, outcome, attacker, defender, source, source_action,
                      *, suppress_for_opportunity=False):
        for effect in effects:
            if effect["outcome"] != outcome:
                continue
            recipient = attacker if effect["recipient"] == "attacker" else defender
            self.apply_stagger(source, recipient, source_action, effect["duration_seconds"],
                               suppressed_reason=("opportunity_attack_exception"
                                                  if suppress_for_opportunity else None))

    def choose_defense(self, actor, target, action, attack_quality, raw):
        """Score only legal, affordable reactions; ties use defense ID."""
        candidates, rejected = [], []
        tactics = target.definition["tactics"]
        for key in sorted(target.definition["defenses"]):
            template = self.actions[key]
            reason = self.action_block_reason(target, template)
            if reason:
                pass
            elif key not in action["allowed_defenses"]:
                reason = "attack does not allow this defense"
            elif key == "parry" and action.get("parryability", "parryable") == "not_parryable":
                reason = "attack is not parryable"
            elif key == "dodge" and not target.definition.get("dodge_practical", True):
                reason = "movement for Dodge is not practical"
            defense_quality = None
            if key == "brace":
                outcome = "No contest"
                reduction = template["damage_reduction"]
            else:
                defense_quality = quality(target, template, self.balance)
                if key == "parry" and action.get("parryability", "parryable") == "difficult":
                    defense_quality["state_modifier"] += template["difficult_quality_penalty"]
                    defense_quality["total"] += template["difficult_quality_penalty"]
                band = outcome_for(defense_quality["total"] - attack_quality["total"], self.balance)
                outcome = band["name"]
                reduction = band["block_reduction"] if key == "block" else template["outcome_reductions"][outcome]
            prevented = raw * reduction
            cost = prevented * self.balance["block_stamina_per_prevented_damage"] if key == "block" else template["stamina_cost"]
            if reason is None and target.stamina + 1e-9 < cost:
                reason = "insufficient stamina"
            if reason:
                rejected.append({"defense": key, "reason": reason, "cost": cost})
                continue
            components = {"damage_prevented": prevented,
                          "resource_penalty": -cost * tactics["resource_penalty_per_point"],
                          "tactical_preference": tactics["defense_preferences"].get(key, 0)}
            candidates.append({"defense": key, "cost": cost, "quality": defense_quality,
                               "outcome": outcome, "reduction": reduction,
                               "components": components, "score": sum(components.values())})
        candidates.sort(key=lambda c: (-c["score"], c["defense"]))
        chosen = candidates[0] if candidates else {
            "defense": "none", "cost": 0, "quality": None,
            "outcome": self.balance["unopposed_outcome"], "reduction": 0}
        self.log("defense_decision", target.id, incoming_actor=actor.id, defense=chosen["defense"],
                 reason="highest defense utility; ties use defense ID" if candidates else "no valid affordable defense",
                 selected=chosen, candidates=candidates, rejected=rejected, available_stamina=target.stamina)
        return chosen

    def opportunity_attack(self, controller, mover):
        key = controller.definition.get("opportunity_attack")
        if not key or controller.incapacitated or controller.escaped or mover.incapacitated or mover.escaped:
            self.log("opportunity_skipped", controller.id, target=mover.id, reason="no available Opportunity Attack")
            return
        a = self.actions[key]
        reason = self.action_block_reason(controller, a)
        if reason:
            self.log("opportunity_skipped", controller.id, target=mover.id, reason=reason)
            return
        if a["range_requirement"] == "ranged":
            self.log("opportunity_skipped", controller.id, target=mover.id, reason="ranged Opportunity Attacks are not supported")
            return
        if getattr(controller, a["resource_type"]) + 1e-9 < a["resource_cost"]:
            self.log("opportunity_skipped", controller.id, target=mover.id, reason="insufficient resource")
            return
        self.log("opportunity_attack", controller.id, action=key, target=mover.id)
        self.spend(controller, a["resource_type"], a["resource_cost"], "opportunity attack", key)
        self.execute(controller, action_key=key, target_id=mover.id, opportunity=True)

    def execute(self, actor, *, action_key=None, target_id=None, opportunity=False):
        if actor.incapacitated or actor.escaped:
            return
        action_key = actor.action if action_key is None else action_key
        a = self.actions[action_key]
        target = self.characters[actor.target if target_id is None else target_id]
        if not opportunity:
            actor.phase = "Executing"
        self.log("execution", actor.id, action=action_key, target=target.id, **({"opportunity": True} if opportunity else {}))
        blocked = self.action_block_reason(actor, a)
        if blocked:
            self.log("action_cancelled", actor.id, action=action_key, target=target.id,
                     reason=f"{blocked}; cost not refunded; normal recovery applies")
        elif a["category"] == "movement":
            positioning.execute_movement(self, actor, action_key)
        elif target.incapacitated or target.escaped:
            self.log("action_cancelled", actor.id, reason="target escaped or incapacitated; cost not refunded")
        elif self.positioning and not positioning.attack_access(actor, target, a):
            self.log("action_cancelled", actor.id, reason=f"target moved outside {a['range_requirement']} access; cost not refunded")
        else:
            attack = quality(actor, a, self.balance)
            raw = a["base_power"] * attack["capability"] / self.balance["capability_baseline"] * max(0, 1 + attack["skill_modifier"] / 100)
            chosen = self.choose_defense(actor, target, a, attack, raw)
            if chosen["defense"] != "none":
                self.spend(target, "stamina", chosen["cost"], "active defense", chosen["defense"])
            incoming = raw
            defense_reduction = incoming * chosen["reduction"]
            after_defense = incoming - defense_reduction
            rating = target.definition["physical_protection"]
            mitigation = rating / (rating + self.balance["protection_k"])
            armor_reduction = after_defense * mitigation
            final = after_defense - armor_reduction
            before = target.health
            target.health = max(0.0, target.health - final)
            self.log("damage", actor.id, action=action_key, target=target.id, attack_quality=attack,
                     defense_quality=chosen["quality"], outcome=chosen["outcome"], active_defense=chosen["defense"],
                     base_power=a["base_power"], raw_damage=raw,
                     incoming_damage=incoming, active_defense_reduction=defense_reduction,
                     protection_rating=rating, protection_mitigation=mitigation, protection_reduction=armor_reduction,
                     final_damage=final, health_lost=before-target.health, health_before=before, health_after=target.health)
            if chosen["defense"] != "none":
                defense = self.actions[chosen["defense"]]
                self.apply_effects(defense.get("effects", []), chosen["outcome"], actor, target,
                                   target, chosen["defense"], suppress_for_opportunity=opportunity)
            self.apply_effects(a.get("effects", []), chosen["outcome"], actor, target, actor, action_key)
            if target.health == 0:
                target.incapacitated = True
                self.log("incapacitated", target.id, cancelled_action=target.action, cancelled_phase=target.phase,
                         reason="health reached zero; non-dead")
                target.phase, target.action, target.target = "Idle", None, None
                target.phase_end_tick = 0
                positioning.refresh(self)
        if opportunity:
            return
        if actor.incapacitated or actor.escaped:
            return
        actor.phase = "Recovering"
        duration_ticks = self.ticks(a["recovery_seconds"]) + actor.pending_recovery_extension_ticks
        actor.pending_recovery_extension_ticks = 0
        actor.phase_end_tick = self.tick + duration_ticks
        self.log("recovery_start", actor.id, action=actor.action,
                 duration=float(Decimal(duration_ticks) * Decimal(str(self.balance["tick_seconds"]))),
                 ends_at_tick=actor.phase_end_tick)

    def run(self):
        if self.events:
            raise ValueError("Create a fresh Simulation for each run")
        self.log("encounter_start", name=self.encounter["name"], order=sorted(self.characters),
                 rules="phase completions in ID order, then idle decisions in ID order")
        positioning.refresh(self)
        retreat.check(self)
        for tick in range(self.ticks(self.balance["max_duration_seconds"]) + 1):
            self.tick = tick
            for actor in sorted(self.active(), key=lambda f: f.id):
                if actor.incapacitated or actor.escaped:
                    continue
                if actor.phase == "Preparing" and tick >= actor.phase_end_tick:
                    self.execute(actor)
                elif actor.phase == "Recovering" and tick >= actor.phase_end_tick:
                    self.log("recovery_end", actor.id, action=actor.action)
                    actor.phase, actor.action, actor.target = "Idle", None, None
                self.result = self.completion()
                if self.result:
                    break
                retreat.check(self)
            if self.result:
                break
            if tick == self.ticks(self.balance["max_duration_seconds"]):
                self.result = "Unresolved"
                break
            for actor in sorted(self.active(), key=lambda f: f.id):
                if actor.phase == "Idle":
                    self.decide(actor)
                    retreat.check(self)
        reason = {"Unresolved": "time limit", "Successful Retreat": "all surviving party members escaped",
                  "Defeat": "no surviving party members", "Victory": "no active hostile combatants"}[self.result]
        self.log("encounter_complete", result=self.result, reason=reason)
        return self.report()

    def report(self):
        return {"encounter": self.encounter["name"], "result": self.result,
                "retreat_active": self.retreat_active,
                "duration_seconds": self.events[-1]["timestamp"], "event_count": len(self.events),
                "combatants": [{"id": f.id, "name": f.definition["name"], "health": f.health,
                                "stamina": f.stamina, "mana": f.mana, "incapacitated": f.incapacitated,
                                "retreating": f.retreating, "escaped": f.escaped,
                                "health_lost": f.definition["maximum_health"] - f.health,
                                "stamina_spent": f.definition["maximum_stamina"] - f.stamina,
                                **({"band": f.band, "opposing_band_reached": f.reached,
                                    "engagements": sorted(f.engagements), "controlled_by": sorted(f.controlled_by),
                                    "positional_states": sorted(f.positional_states)} if self.positioning else {})}
                               for f in sorted(self.characters.values(), key=lambda f: f.id)]}


def load_simulation(config_dir, encounter_path=None, *, duel=None, positions="frontline"):
    def read(name):
        return json.loads((Path(config_dir) / f"{name}.json").read_text(encoding="utf-8"))
    encounter = json.loads(Path(encounter_path).read_text(encoding="utf-8")) if encounter_path else read("encounter")
    from .encounters import materialize_encounter
    roster_path = Path(config_dir) / "characters.json"
    roster = json.loads(roster_path.read_text(encoding="utf-8")) if roster_path.exists() else None
    encounter = materialize_encounter(encounter, roster)
    if duel is not None:
        from .encounters import make_duel
        encounter = make_duel(encounter, *duel, positions=positions)
    return Simulation(read("balance"), read("actions"), encounter)
