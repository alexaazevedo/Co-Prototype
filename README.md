# Combat prototype: defenses and positioning

Python 3.10+; standard library only. From this directory:

```powershell
python -m combat
python -m combat --encounter config/formation.json --output output/formation
python -m unittest discover -s tests -v
```

The default output is a chronological combat transcript with preparations, hits,
defenses, damage layers, resource changes and a final results table.
`python -m combat --verbose` adds AI candidate scores, Quality calculations,
defense reasoning and recovery events.

Each run writes `output/combat.log` (readable transcript),
`output/combat.verbose.log` (detailed transcript), `output/events.jsonl` (full
structured events) and `output/report.json`, replacing the previous run's files.
Use `--output output/experiment-1` to retain separate experiments, and
`--config path/to/config` to run a copied configuration directory.

## What this stage implements

Select a duel directly from an existing encounter without editing its JSON:

```powershell
python -m combat --encounter config/formation.json --duel gareth talen --positions frontline
python -m combat --encounter config/formation.json --duel gareth talen --positions base
```

`frontline` (the default) starts both characters at Frontline. `base` preserves
their configured bands. Both enable the normal positioning, engagement and
exposure rules, including restrictions on ranged actions. The two selected
characters are copied onto opposing teams; their other definitions and the source
file remain unchanged. Victory/Defeat is from the first character's perspective.
Existing action lists determine whether they can close distance in base mode.
Logs default to `output/duels/FIRST-vs-SECOND/MODE/`; `--output` overrides this.
Repeated runs of the same matchup and mode replace that folder's result files.

To compare defenses using the current JSON settings:

```powershell
python -m combat.defense_matrix
```

This prints and saves damage remaining for Block, Dodge, Parry and Brace at
Defense Quality 0–120 in steps of 5, against Attack Quality 80 and incoming damage
100. It assumes zero armor, sufficient Stamina, and a normally parryable attack.
The damage input is already incoming damage; character capability and skill do
not rescale it. Results are saved to `output/defense_matrix.csv` and a readable
`output/defense_matrix.txt`. Each run reads the latest defense configuration.
Use `--attack-quality`, `--damage`, `--min-quality`, `--max-quality`, `--step`,
`--config` or `--output` to vary the comparison. Stamina costs and temporary
combat effects are not included in the damage cells.

The prototype includes the original Gareth-versus-Brute duel plus a configurable
formation scenario. Autonomous physical attacks, reactive defenses, Health,
Stamina and Mana storage, preparation/execution/recovery, Quality, physical
protection, incapacitation, Victory/Defeat and a bounded Unresolved result are
implemented. Content definitions are separate from mutable encounter state. The
engine has no checks for character names or named attacks.

Naming convention: `Character` is the generic entity, and `characters` names
collections of those entities in code. A combatant is a character participating
in an encounter; encounter configuration and combat reports retain `combatants`.

This is not yet the full v0.1 party. The formation scenario implements band
access, Engagement Capacity, breakthrough, withdrawal, retreat and Opportunity Attacks.
Spellcasting, support and temporary effects beyond the narrow Stagger mechanic
are future stages. Pressured and Isolated are not yet modeled. Protected/Exposed
indicate access and grant no generic Quality bonus. The action `interruptible`
field is reserved for a future effect that directly cancels actions; Stagger does
not use it.
Unsupported effects and unknown usage conditions are rejected rather than silently applied.

## Combat access principles

Melee and ranged are access categories, not separate damage systems. Once an
attack is legal, both use the same underlying Quality, damage and protection
pipeline unless the action explicitly defines a different mechanic.

Melee attacks require immediate physical access. Ranged attacks can target across
bands without creating an Engagement. There is no range falloff in the current
prototype. Ordinary ranged attacks do not establish or modify melee control.

Protected primarily describes whether hostile melee access is blocked. It does
not grant a generic defense bonus. Exposed means at least one hostile character
currently has direct melee access; a character can be Exposed without being
assigned to a controller.

There are no random critical hits in the current prototype.

## Action availability while Exposed

An action can opt into this shared condition:

```json
"usage_conditions": {"prevent_when_exposed": true}
```

It prevents starting the action when any active enemy has direct melee access
to its user. It is checked again at Execution: if the user became Exposed during
Preparation, the action is cancelled with no refund and normal Recovery. Exposure
does not itself interrupt Preparation early. Rejection and cancellation reasons
appear in the logs. Omitting the flag or setting it to false leaves the action
available. The check is independent of range, resource and damage type, so future
magical actions can use the same condition without a separate rule.

`ranged_attack` currently enables this condition. Engagement is not itself the
condition; direct melee access is. A character can be Exposed without being
assigned to a controller. The user's live action weights and formation remain
editable; historical scenario names and results below describe earlier experiments.

## Replaceable configuration

- `config/characters.json`: reusable, complete character definitions without
  encounter-specific teams or starting bands.
- `config/encounter.json`: the default encounter composition and policies.
- `config/formation.json`: the positioning test composition and policies.
- `config/novicencounter.json`: an additional experimental composition.
- `config/actions.json`: powers, costs, weights, skills and timings.
- `config/balance.json`: clock, maximum duration, Quality bands, defense
  reductions/costs and protection K.

Edit JSON and run again. Changing definitions does not require an engine rewrite.
Adding a new kind of mechanic still requires an explicit rule in the engine.

An encounter can continue to contain complete inline character definitions. It can
also select characters from `config/characters.json` using placements containing
only `id`, `team`, and `band`:

```json
"combatants": [
  {"id": "gareth", "team": "party", "band": "Frontline"},
  {"id": "skirmisher_1", "team": "enemy", "band": "Frontline"}
]
```

The loader copies the referenced roster definitions and adds the placement fields
before constructing the simulation. It rejects unknown IDs, duplicate roster IDs,
placement overrides, and encounters that mix placements with inline definitions.
This keeps encounter setup independent without adding templates or inheritance.

## Provisional rules

Time advances in 0.1-second ticks stored as integers; action durations must be
exact multiples of the configured tick. At a timestamp, phase completions resolve
in combatant-ID order; then idle combatants choose actions in ID order. Death
prevents later same-timestamp actions. This ordering is deterministic and can
favor the earlier ID in a lethal tie; it is not simultaneous damage resolution.

Execution is immediate. Costs are paid at preparation start, without refunds.
All defenses are reactive, including while Staggered and during Preparation or
Recovery. Defending does not itself change the defender's action timing. No
regeneration occurs. With no affordable action a character remains idle. A duration
limit reports Unresolved, never a false victory.

Quality = weighted capability + (skill - 50) × 0.4 + state modifiers. Difficult
Parry applies a configured Quality penalty; final Quality is not clamped. Continuous Quality differences
use ±5 and ±15 boundaries: between -5 and +5 is Contested; exactly +5/+15 favors
the defender, exactly -5/-15 favors the attacker (defender-minus-attacker margin).

Raw damage = base power × (capability / 50) × max(0, 1 + skill modifier / 100).
Quality selects the chosen defense's damage result. Apply defense reduction to
raw damage, then physical protection rating / (rating + 100). Block costs 15% of
the damage it prevents before armor, configured by
`block_stamina_per_prevented_damage` in `config/balance.json`. A Block preventing
no damage costs no Stamina. Affordability and defense utility use this
outcome-dependent cost. Having no valid affordable defense means an unopposed Hit:
raw damage goes directly to protection, with no invented defense Quality. Health
bottoms out at zero; logs distinguish calculated final damage from actual health
lost on overkill.

AI chooses the highest affordable legal action/target score: base usefulness +
configured action bonus + target preference - cost-based resource penalty.
Ties use action ID then target ID. Formation encounters also use configurable
engaged-target and penetrating-threat bonuses, restricted to accessible targets.

## Active defenses

The engine and default duel support Block, Dodge, Parry and Brace.
Controlled tests also exercise all defenses independently of encounter balance.
Attributes live on each Character definition, not on the defense. Templates
reference those attributes with editable weights: Dodge uses Gross Coordination
40%, Balance 35%, Reflexes 25%; Parry currently uses Grip & Control 35%, Gross
Coordination 30%, Reflexes 35%. Both use the character's corresponding defense skill.
Balance and Reflexes currently match each fixture's Gross Coordination as
provisional starting values. All these values can be replaced in encounter JSON.
The sword is parryable and the Brute's heavy attack is difficult to parry.
Ranged Attack allows Block, Dodge and Brace, but cannot be parried.

The current damage-taken table is:

| Outcome | Block | Dodge | Parry | Brace |
|---|---:|---:|---:|---:|
| Strong Hit | 100% | 100% | 100% | 80% |
| Hit | 80% | 100% | 100% | 80% |
| Contested | 60% | 70% | 65% | 80% |
| Defense | 45% | 35% | 30% | 80% |
| Strong Defense | 35% | 10% | 15% | 80% |

Block's Stamina cost is outcome-dependent as described above. Dodge costs 5
Stamina. Parry costs 3 Stamina. Brace costs zero Stamina and always leaves 80%
of incoming raw damage before armor.

Attacks can be `parryable`, `difficult` (-10 Parry Quality), or
`not_parryable`. An attack's `allowed_defenses` further restricts responses.

## Stagger

Stagger is the prototype's first narrow temporary combat effect. Its duration and
trigger are configured on an action or defense. The initial sources are Heavy
Attack on Strong Hit and Parry on Strong Defense, both with a 0.3-second duration:

```json
"effects": [
  {
    "type": "stagger",
    "outcome": "Strong Hit",
    "recipient": "defender",
    "duration_seconds": 0.3
  }
]
```

Stagger has a phase-specific consequence when applied:

- Idle: normal action selection is locked until Stagger expires.
- Preparing: the current Preparation end is extended by the Stagger duration. The
  action and its existing resource payment remain unchanged, regardless of its
  `interruptible` value.
- Recovering: the existing Recovery end is extended by the Stagger duration.
- Executing: the duration extends the Recovery that immediately follows Execution.

Reactive Block, Dodge, Parry and Brace remain available while Staggered. Stagger
does not change defensive Quality, mitigation or costs. A second Stagger during an
active Stagger window is ignored without refreshing or extending the first effect.

A Strong Defense Parry now produces its Recovery extension through this shared
Stagger rule. When an Opportunity Attack is strongly parried, its Stagger effect on
the controller is suppressed so it cannot alter the controller's unrelated normal
action or timing; the suppression is logged. Stun, other temporary effects and a
general status-effect framework remain future work. A future Interrupt effect may
use the `interruptible` property to cancel actions and apply its own costs.

`dodge_practical` is provisional prototype scaffolding. When present and false it
can disable Dodge for a character, but it is not currently a locked general
character-model rule and may be removed or replaced once spatial restrictions are
designed.

Defense utility = raw damage prevented - Stamina cost × resource penalty per
point + tactical preference. The highest-scoring valid affordable defense wins;
ties use defense ID. Candidate Quality calculations, outcomes, scores, costs and
rejection reasons are logged. The score currently values damage prevention only,
not the experimental Parry recovery-delay benefit. No additional damage multiplier
is applied.

Brace's resistance to future incoming displacement or stagger effects remains
reserved for the stage that introduces those mechanics.

## Positioning and hostile control

Run `python -m combat --encounter config/formation.json --output output/formation`.
The original duel remains runnable with `python -m combat`; its encounter does
not enable positioning, preserving the earlier defense test.

Each character has an own formation band and an opposing band reached, initially
Frontline. Advancing from one's Midline/Backline approaches one's Frontline;
advancing from Frontline enters the opposing Midline, then Backline. Withdrawal
reverses this path. Each move changes exactly one band, with no grid or distances.
Characters in opposing Frontlines can attack each other. A penetrator can attack
and be attacked by allies occupying the band it has reached. A frontliner cannot
directly melee a penetrator that has moved beyond it. Access is checked both when
choosing an attack and when executing it; invalidated attacks still consume their
already-paid preparation cost and normal recovery.

Ranged physical attacks have target access across all bands; the enabled
`prevent_when_exposed` condition restricts whether the user can perform them.
They use the same damage and physical-protection rules as melee attacks. Ranged
Attack uses Base Power 27, Stamina cost 3, preparation 0.5s and recovery 0.7s.
The current ranged weights are Fine Motor Control 35%, Spatial Awareness 30%,
Grip & Control 20%, Perception 15%; it reads the character's `ranged` skill.
Ranged access does not change melee engagements or the Protected/Exposed states.
Ranged Opportunity Attacks are not supported. Damage types beyond physical remain
unimplemented.

Controllers hold their own band with a hard capacity. Initial assignment uses
descending `engagement_priority` for movers and `control_priority` for controllers,
then character ID. Existing legal engagements are preserved before filling free
slots. Each mover has at most one assigned controller. Incapacitation or movement
out of reach releases control immediately.

An engaged character must Withdraw to leave; ordinary forward movement cannot bypass
that rule. An extra enemy beyond capacity may Breakthrough. Both use the same
movement-versus-Control Quality contest. A mover advantage of at least 5 is clean
success; a controller advantage of at least 5 is failure; between them is partial
success plus an Opportunity Attack. If multiple controllers cover the departure
band, each is checked; any failure stops movement. Partial contests produce one
Opportunity Attack per relevant controller only if no controller stops movement.
Without hostile control, movement is unopposed.

Movement costs 3 Stamina at preparation start, with 0.5s preparation and 0.5s
recovery. A failed attempt still spends the cost and recovers. These values and
the specification's movement weights live in action configuration; Control
weights and the clear-margin threshold live in balance configuration. Character
attributes and movement/control skills provide all capability values.

Opportunity Attacks use the controller's configured `opportunity_attack` and its
normal resource cost, damage and defenses. They resolve before movement. Lack
of resources skips the attack; damage does not cancel movement unless the mover
is incapacitated. The controller's current action and timing remain unchanged,
including when the Opportunity Attack is strongly parried; that exception is
explicitly logged. Opportunity Attacks do not recursively trigger more attacks.

The formation fixture deliberately tests access rather than encounter balance.
Historical fixture compositions and outcomes may change as the live JSON is used
for later experiments; use the current configuration and generated logs as the
source of truth for a particular run.

## Current damage experiment

The results below are historical tuning experiments; the live configuration has
since changed.

Physical Base Power was increased by 50%: Sword Attack and Ranged Attack 18 -> 27,
Heavy Attack 34 -> 51, Quick Attack 12 -> 18. Health, protection, timings, costs
and AI settings were unchanged. Block's cost still scaled with prevented damage.
The duel ended in Victory at 11.3s (previously 17.3s). In the formation test used
for that experiment, the Brute and first Skirmisher were incapacitated, with the
ranged party member surviving at 2.82 HP. Prior run logs and the previous action
configuration were saved locally under `output/before-damage-increase/` for comparison.

## Configurable retreat and Withdraw

Encounter files can include:

```json
"retreat": {
  "enabled": true,
  "health_threshold": 0.30,
  "useful_resource_threshold": 0.20,
  "trigger_mode": "either",
  "allow_exhausted_withdrawal": true
}
```

Fractions use the original party's combined maximum values as fixed denominators.
Current HP at or below 30%, or useful resources at or below 20%, triggers retreat.
Use `"both"` to require both configured thresholds, `null` to disable an individual
threshold, or `"enabled": false` to disable automatic retreat. An absent retreat
section also disables it. Checks occur at combat start and after phase resolution
and action selection, including resource expenditure. Retreat stays active once
triggered, even if later resource or Health totals increase.

Useful resources sum Stamina/Mana only for each character who has a positive-cost
action or defense that consumes that resource. Unused Mana is excluded; Stamina
used by Block or other defenses is included. Each point has equal weight.
Incapacitated characters contribute zero to current HP and useful resources, but
their initial maximums remain in the denominators. An empty useful-resource pool
does not trigger retreat by itself. Escaped survivors retain their recorded values;
the retreat decision is already latched and is never reversed or reevaluated.

Withdraw replaces the separate Disengage action. It moves one band back along
the existing path, then escapes on a further successful withdrawal from the
character's own Backline. Withdraw is opposed by existing hostile control and
engagements. A hostile with direct melee access who is actively performing a melee
attack against the withdrawing character also opposes it, regardless of Engagement
Capacity. Each opponent uses the same movement-versus-Control Quality contest as
breakthrough, including partial success Opportunity Attacks. Without either source
of opposition, movement is unopposed. Escaping requires preparation but ends
participation immediately on execution; no post-escape recovery, action, defense,
targeting or engagement occurs. An Opportunity Attack that incapacitates the
withdrawer prevents both movement and escape.

The AI selects Withdraw only while retreating, and prioritizes it over attacks.
Already-started preparation and recovery finish normally before the next choice.
Once a character is retreating, they release their engagements and no longer
initiate control over enemies. Hostile characters can still engage or control them,
and active melee pressure can still oppose their Withdraw.

Currently only the party has automatic retreat policy; enemies can use that same
policy when selected as the first character in a duel. All configured characters
have Withdraw available for that purpose. No rescue/carrying system is modeled:
all non-incapacitated surviving party members must escape for Successful Retreat;
if all party members are incapacitated, the result is Defeat.

Cost, preparation, recovery and attribute weights stay in the `withdraw` action
in `config/actions.json`. With `allow_exhausted_withdrawal` enabled, a retreating
character pays whatever remains up to the action's normal cost, even zero.
When false, an unaffordable withdrawal is unavailable. Failure still consumes
the paid cost and normal recovery. Withdraw can fail repeatedly if opposing
Control Quality consistently wins; retreat is not guaranteed.

The initial run with these defaults triggers retreat at 9.4s with 19.1% useful
resources left. Talen escapes at 10.1s and Gareth at 12.1s. The detailed transcript
and report are in `output/retreat/`.

## Reading the result

The structured log records candidate scores, rejected actions, resource balances,
phase transitions, Quality components, defense reasons and each damage layer.
The summary reports remaining resources and attrition. Identical input produces
identical events. Tests cover that property alongside arithmetic, fractional
Quality boundaries, timing, exhaustion, incapacitation and lethal ties.
