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
`--config` or `--output` to vary the comparison. Stamina costs and stagger are
not included in the damage cells.

The original Gareth-versus-Brute duel plus a formation scenario with Gareth,
Elira, a Brute and two Skirmishers. Autonomous physical attacks, reactive defenses, Health,
Stamina and Mana storage, preparation/execution/recovery, Quality, physical
protection, incapacitation, Victory/Defeat and a bounded Unresolved result.
Content definitions are separate from mutable encounter state. The engine has
no checks for character names or named attacks.

Naming convention: `Character` is the generic entity, and `characters` names
collections of those entities in code. A combatant is a character participating
in an encounter; encounter configuration and combat reports retain `combatants`.

This is not yet the full v0.1 party. The formation scenario implements band
access, Engagement Capacity, breakthrough, withdrawal, retreat and Opportunity Attacks.
Elira uses a physical ranged attack from Midline. Spellcasting, support,
interruptions and general temporary effects are future stages.
Her support abilities are not implemented. Pressured and Isolated
are not yet modeled. Protected/Exposed indicate access and grant no Quality bonus.
The action interruptible field is metadata until interruption is implemented.
Unsupported effects and unknown usage conditions are rejected rather than silently applied.

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

- `config/encounter.json`: starting stats, skills, available actions and simple
  tactical action/target preferences and resource penalties.
- `config/formation.json`: the separate positioning validation encounter.
- `config/actions.json`: powers, costs, weights, skills and timings.
- `config/balance.json`: clock, maximum duration, Quality bands,
  Block reductions/cost and protection K.

Edit JSON and run again. Changing definitions does not require an engine rewrite.
Adding a new kind of mechanic still requires an explicit rule in the engine.

## Provisional rules

Time advances in 0.1-second ticks stored as integers; action durations must be
exact multiples of the configured tick. At a timestamp, phase completions resolve
in combatant-ID order; then idle combatants choose actions in ID order. Death
prevents later same-timestamp actions. This ordering is deterministic and can
favor the earlier ID in a lethal tie; it is not simultaneous damage resolution.

Execution is immediate. Costs are paid at preparation start, without refunds.
All defenses are reactive, including during preparation/recovery; they do not delay the
defender's action. No regeneration occurs. With no affordable action a character
remains idle. A duration limit reports Unresolved, never a false victory.

Quality = weighted capability + (skill - 50) × 0.4 + state modifiers. Difficult
Parry applies a configured Quality penalty; final Quality is not clamped. Continuous Quality differences
use ±5 and ±15 boundaries: between -5 and +5 is Contested; exactly +5/+15 favors
the defender, exactly -5/-15 favors the attacker (defender-minus-attacker margin).

Raw damage = base power × (capability / 50) × max(0, 1 + skill modifier / 100).
Quality selects Block's reduction only: Strong Defense 65%, Defense 55%,
Contested 40%, Hit 20%, Strong Hit 0%. There is no Quality-outcome damage
multiplier. Apply Block directly to raw damage, then physical protection
rating / (rating + 100). Block costs 15% of the damage it prevents before armor,
configured by `block_stamina_per_prevented_damage` in `config/balance.json`.
A Block preventing no damage costs no Stamina. Affordability and defense utility
use this outcome-dependent cost. Having no valid affordable defense means an unopposed Hit: raw damage goes
directly to protection, with no invented defense Quality. Health bottoms out at zero; logs distinguish
calculated final damage from actual health lost on overkill.

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
Elira's ranged attack allows Block, Dodge and Brace, but cannot be parried.

- Dodge costs 5 Stamina: Strong Defense/Defense avoid all damage, Contested
  prevents 50%, Hit/Strong Hit prevent none.
- Parry costs 3 Stamina and uses the same prevention table. Strong Defense
  also adds 0.3 seconds to the attacker's upcoming Recovery. Performing the
  defense does not alter the defender's own preparation or recovery.
- Attacks can be `parryable`, `difficult` (-10 Parry Quality), or
  `not_parryable`. An attack's `allowed_defenses` further restricts responses.
- Brace costs zero Stamina, prevents 20% of raw damage, and has no Quality
  contest. Its cost and reduction are editable in `config/actions.json`.
- Dodge is practical by default in the duel. A character's optional
  `dodge_practical` flag can disable it; spatial rules are not implemented yet.

Defense utility = raw damage prevented - Stamina cost × resource penalty per
point + tactical preference. The highest-scoring valid affordable defense wins;
ties use defense ID. Candidate Quality calculations, outcomes, scores, costs and
rejection reasons are logged. The score currently values damage prevention only,
not Parry's extra stagger benefit. No additional damage multiplier is applied.

Brace's resistance to incoming displacement/stagger remains for the stage that
introduces those attack effects. Current stagger is solely the consequence of
a Strong Defense Parry against the attacker.

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
They use the same damage and physical-protection
rules as melee attacks. Elira's Ranged Attack uses Base Power 27, Stamina cost (3),
preparation (0.5s), recovery (0.7s). The current ranged weights are Fine Motor
Control 35%, Spatial Awareness 30%, Grip & Control 20%, Perception 15%; it reads
the character's `ranged` skill. Ranged access does not change
melee engagements or the Protected/Exposed states. Ranged Opportunity Attacks
are not supported. Damage types beyond physical remain unimplemented.

Controllers hold their own band with a hard capacity. Initial assignment uses
descending `engagement_priority` for movers and `control_priority` for controllers,
then character ID. Existing legal engagements are preserved before filling free
slots. Each mover has at most one assigned controller. Incapacitation or movement
out of reach releases control immediately. In this isolated fixture Gareth is
the controller; the three enemies and Elira have zero capacity.

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

The formation fixture deliberately tests access rather than encounter balance:
Gareth holds the Brute and first Skirmisher, while the second achieves partial
breakthrough and reaches Elira. With the current reduced party and no regeneration,
the run ends Unresolved at 120 seconds. Elira and the penetrating Skirmisher
exhaust their Stamina. Gareth has some Stamina left but cannot reach the remaining
Midline enemy: his current action list has no movement action for following it
after his engagements end. This is reported rather than treated as Victory or Defeat.

## Current damage experiment

The results below are historical tuning experiments; the live configuration has
since changed. The current formation has Gareth, Talen, a Brute and three
Skirmishers, with retreat enabled.

Physical Base Power was increased by 50%: Sword Attack and Ranged Attack 18 -> 27,
Heavy Attack 34 -> 51, Quick Attack 12 -> 18. Health, protection, timings, costs
and AI settings are unchanged. Block's cost still scales with prevented damage.
The duel now ends in Victory at 11.3s (previously 17.3s). In the formation test,
the Brute and first Skirmisher are incapacitated, with Elira surviving at 2.82 HP.
Prior run logs and the previous action configuration are saved locally under
`output/before-damage-increase/` for comparison.

## Configurable retreat and Withdraw

Both encounter JSON files now include:

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
character's own Backline. Leaving hostile control uses the same movement-versus-
Control contest as breakthrough, including partial success Opportunity Attacks.
No hostile control means no contest. Escaping requires preparation but ends
participation immediately on execution; no post-escape recovery, action, defense,
targeting or engagement occurs. An Opportunity Attack that incapacitates the
withdrawer prevents both movement and escape.

The AI selects Withdraw only while retreating, and prioritizes it over attacks.
Already-started preparation and recovery finish normally before the next choice.
Currently only the party has automatic retreat policy; enemies can use that
same policy when selected as the first character in a duel. All configured
characters have Withdraw available for that purpose. No rescue/carrying system
is modeled: all non-incapacitated surviving party members must escape for
Successful Retreat; if all party members are incapacitated, the result is Defeat.

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
