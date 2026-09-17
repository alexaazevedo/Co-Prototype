import argparse
import json
import re
import sys
from pathlib import Path

from .engine import load_simulation
from .transcript import render_transcript


def main():
    # Keep redirected output readable on Windows as well as in the terminal.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Deterministic combat foundation")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "config")
    parser.add_argument("--output", type=Path, help="Output directory; duels default to a folder per matchup and position mode")
    parser.add_argument("--encounter", type=Path, help="Encounter JSON override, e.g. config/formation.json")
    parser.add_argument("--duel", nargs=2, metavar=("FIRST", "SECOND"), help="Select two character IDs; first character is the party")
    parser.add_argument("--positions", choices=("frontline", "base"), help="Duel starting bands (default: frontline)")
    parser.add_argument("--verbose", action="store_true", help="Include AI scores, calculations and recovery events")
    args = parser.parse_args()
    if args.positions and not args.duel:
        parser.error("--positions requires --duel")
    positions = args.positions or "frontline"
    try:
        simulation = load_simulation(args.config, args.encounter, duel=args.duel, positions=positions)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    if args.output is None:
        args.output = Path("output")
        if args.duel:
            names = [re.sub(r"[^a-zA-Z0-9_-]", "_", key) for key in args.duel]
            args.output = args.output / "duels" / f"{names[0]}-vs-{names[1]}" / positions
    report = simulation.run()
    args.output.mkdir(parents=True, exist_ok=True)
    events = "\n".join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in simulation.events) + "\n"
    readable = render_transcript(simulation.events, report, simulation.encounter["combatants"], simulation.actions)
    detailed = render_transcript(simulation.events, report, simulation.encounter["combatants"], simulation.actions, verbose=True)
    (args.output / "events.jsonl").write_text(events, encoding="utf-8")
    (args.output / "combat.log").write_text(readable, encoding="utf-8")
    (args.output / "combat.verbose.log").write_text(detailed, encoding="utf-8")
    (args.output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(detailed if args.verbose else readable)
    print(f"Logs and report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
