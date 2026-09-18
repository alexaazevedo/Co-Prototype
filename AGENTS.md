## Change workflow

- Before editing source code or configuration files, explain the intended change and
  wait for explicit user approval.
- Read-only inspection, diagnostics, and running existing tests or simulations do not
  require approval.
- Before proposing edits, inspect the relevant current files and `git diff` / `git status`
  when available so user-authored changes are not mistaken for baseline behavior.
- A user approval for a proposed implementation covers the described source changes
  and the tests/documentation directly required by that implementation. Do not request
  separate approval for each affected file unless the scope changes materially.
- If implementation reveals a materially different design choice, stop and explain
  the choice before proceeding.
- Do not add third-party dependencies without explicit user approval.

## Project conventions

- Favor replaceable configuration over clever abstractions.
- Keep balance values, action properties, character attributes, and encounter policy
  in JSON configuration when they are intended to be tunable.
- Preserve user-authored configuration values unless the approved change specifically
  modifies them.
- Use `Character` as the generic entity name. Use `combatant` for a character
  participating in an encounter.
- Read `README.md` before proposing changes to existing combat mechanics.
- The project targets Python 3.10 or newer and currently uses only the standard library.

## Determinism

- Simulation state must not depend on wall-clock time, process state, unordered
  collection traversal, random UUIDs, or other external nondeterministic values.
- Any randomness used by the simulation must come from the encounter's deterministic
  random source / seed.
- When multiple events are eligible at the same simulation point, their resolution
  order must be explicitly defined rather than relying on incidental Python ordering.
- Changes to resolution order are combat-rule changes and require appropriate tests.

## Rule resolution

- Keep the order in which combat rules are applied explicit and traceable.
- Do not introduce ambiguous chains of modifiers whose result depends on implementation
  details rather than a documented rule order.
- Rounding, clamping, minimum/maximum values, and threshold comparisons should be
  defined consistently and covered by tests where they affect combat outcomes.
- Prefer configurable formulas and thresholds when they are balance decisions;
  keep fundamental simulation semantics in code.

## Events and simulation output

- The simulation engine is authoritative for combat outcomes.
- Record outcomes as structured events containing the information needed by renderers
  and tests.
- Transcript renderers may format or omit event information for presentation, but must
  not calculate damage, select targets, apply statuses, or otherwise alter outcomes.
- Avoid making simulation rules depend on transcript text.

## Configuration validation

- Validate encounter, action, defense, and balance configuration before simulation
  begins whenever practical.
- Reject unknown or unsupported mechanic values when accepting them would hide a
  configuration mistake.
- Do not silently substitute defaults for malformed explicit values.
- When changing the configuration schema, update controlled test fixtures and relevant
  README documentation as part of the same approved change.
- Preserve backward compatibility when it is inexpensive and intentional; do not add
  compatibility behavior merely to conceal obsolete configuration.

## Testing

- Run the complete test suite after changes to simulation rules or configuration schemas:

  ```powershell
  python -m unittest discover -s tests -v
  ```

- Add a focused regression test for bug fixes when the behavior can be reproduced
  deterministically.
- Prefer small controlled fixtures that isolate one mechanic over large encounter
  snapshots.
- Tests for one mechanic should avoid depending unnecessarily on unrelated balance
  values.
- Test externally visible combat behavior and important intermediate events rather
  than private implementation details.
- Do not update expected test results merely to make a failing test pass unless the
  behavior change is intentional.
