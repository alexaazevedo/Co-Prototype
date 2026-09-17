"""Small encounter setup helpers; combat rules stay in the simulation."""

from copy import deepcopy


def make_duel(encounter, first, second, positions="frontline"):
    if first == second:
        raise ValueError("A duel requires two different character IDs")
    if positions not in {"frontline", "base"}:
        raise ValueError("Duel positions must be frontline or base")
    definitions = encounter["combatants"]
    characters = {character["id"]: character for character in definitions}
    if len(characters) != len(definitions):
        raise ValueError("Source encounter contains duplicate character IDs")
    missing = [key for key in (first, second) if key not in characters]
    if missing:
        raise ValueError(f"Unknown character ID(s): {', '.join(missing)}. Available: {', '.join(sorted(characters))}")
    duel = deepcopy(encounter)
    duel["combatants"] = [deepcopy(characters[key]) for key in (first, second)]
    duel["party_team"] = "party"
    duel["positioning"] = True
    for character, team in zip(duel["combatants"], ("party", "enemy")):
        character["team"] = team
        if positions == "frontline":
            character["band"] = "Frontline"
    duel["name"] = (f"Duel: {characters[first]['name']} versus {characters[second]['name']} "
                    f"({positions} positions; perspective: {characters[first]['name']})")
    return duel
