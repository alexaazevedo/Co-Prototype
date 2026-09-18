"""Small encounter setup helpers; combat rules stay in the simulation."""

from copy import deepcopy


PLACEMENT_KEYS = {"id", "team", "band"}


def materialize_encounter(encounter, roster=None):
    """Expand simple roster placements; preserve complete inline encounters."""
    combatants = encounter.get("combatants", [])
    if not all(isinstance(character, dict) for character in combatants):
        raise ValueError("Encounter combatants must be objects")
    placements = [PLACEMENT_KEYS <= set(character) and "maximum_health" not in character
                  for character in combatants]
    if not any(placements):
        return deepcopy(encounter)
    if not all(placements):
        raise ValueError("Encounter cannot mix roster placements with inline character definitions")
    if any(set(character) != PLACEMENT_KEYS for character in combatants):
        raise ValueError("Roster placements support only id, team and band")
    if not isinstance(roster, dict) or not isinstance(roster.get("characters"), list):
        raise ValueError("Roster encounter requires config/characters.json with a characters list")

    definitions = roster["characters"]
    if not all(isinstance(character, dict) and isinstance(character.get("id"), str)
               for character in definitions):
        raise ValueError("Roster characters require string IDs")
    characters = {character["id"]: character for character in definitions}
    if len(characters) != len(definitions):
        raise ValueError("Character roster contains duplicate IDs")
    if any("team" in character or "band" in character for character in definitions):
        raise ValueError("Roster characters cannot define encounter team or band")

    missing = sorted({placement["id"] for placement in combatants} - set(characters))
    if missing:
        raise ValueError(f"Unknown roster character ID(s): {', '.join(missing)}")

    expanded = deepcopy(encounter)
    expanded["combatants"] = []
    for placement in combatants:
        character = deepcopy(characters[placement["id"]])
        character.update(deepcopy(placement))
        expanded["combatants"].append(character)
    return expanded


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
