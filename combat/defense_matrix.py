"""Compare active defenses at explicit Quality values, using current configuration."""

import argparse
import csv
import json
import math
from pathlib import Path
import sys

from .engine import outcome_for


DEFENSES = ("block", "dodge", "parry", "brace")
HEADERS = ("Defense Quality", "Block", "Dodge", "Parry", "Brace")


def build_matrix(balance, actions, attack_quality=80, damage=100, minimum=0, maximum=120, step=5):
    if not math.isfinite(attack_quality) or not math.isfinite(damage) or damage < 0:
        raise ValueError("Attack Quality must be finite; incoming damage must be finite and nonnegative")
    if step <= 0 or maximum < minimum:
        raise ValueError("Step must be positive and maximum must be at least minimum")
    rows = []
    for defense_quality in range(minimum, maximum + 1, step):
        band = outcome_for(defense_quality - attack_quality, balance)
        reductions = {
            "block": band["block_reduction"],
            "dodge": actions["dodge"]["outcome_reductions"][band["name"]],
            "parry": actions["parry"]["outcome_reductions"][band["name"]],
            "brace": actions["brace"]["damage_reduction"],
        }
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in reductions.values()):
            raise ValueError("Defense reductions must be finite values between zero and one")
        rows.append([defense_quality, *[damage * (1 - reductions[key]) for key in DEFENSES]])
    return rows


def format_matrix(rows):
    cells = [list(HEADERS)] + [[str(row[0]), *[f"{value:.2f}" for value in row[1:]]] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(HEADERS))]
    lines = []
    for index, row in enumerate(cells):
        lines.append("  ".join(value.rjust(width) for value, width in zip(row, widths)))
        if index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "config")
    parser.add_argument("--attack-quality", type=float, default=80)
    parser.add_argument("--damage", type=float, default=100, help="Incoming damage before active defense; not rescaled by attributes")
    parser.add_argument("--min-quality", type=int, default=0)
    parser.add_argument("--max-quality", type=int, default=120)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("output/defense_matrix.csv"))
    args = parser.parse_args()
    try:
        balance = json.loads((args.config / "balance.json").read_text(encoding="utf-8"))
        actions = json.loads((args.config / "actions.json").read_text(encoding="utf-8"))
        rows = build_matrix(balance, actions, args.attack_quality, args.damage,
                            args.min_quality, args.max_quality, args.step)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows([[row[0], *[f"{value:.2f}" for value in row[1:]]] for row in rows])
    description = (f"Attack Quality: {args.attack_quality:g} | Incoming damage: {args.damage:g}\n"
                   "Damage after active defense, before armor. Lower is better for the defender.\n"
                   "All defenses eligible and affordable; normal Parry difficulty.\n"
                   "Each row supplies final Defense Quality directly. Brace has no Quality contest.\n")
    report = description + "\n" + format_matrix(rows) + "\n"
    text_path = args.output.with_suffix(".txt")
    if text_path == args.output:
        text_path = args.output.with_name(args.output.stem + "_table.txt")
    text_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"CSV: {args.output.resolve()}")
    print(f"Readable table: {text_path.resolve()}")


if __name__ == "__main__":
    main()
