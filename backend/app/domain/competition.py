"""FR-1.2 multi-division structures and hybrid formats. Pure functions over standings tables."""
from ..errors import validation_error
from ..validate import is_int


def promotion_relegation(divisions: list[dict], promote: int, relegate: int) -> list[dict]:
    """divisions: [{"division": 1 (top), "league_id", "table": standings rows ordered by rank}].

    Top `promote` of every lower division go up; bottom `relegate` of every higher division go down.
    """
    ordered = sorted(divisions, key=lambda d: d["division"])
    last = len(ordered) - 1
    out = []
    for i, div in enumerate(ordered):
        teams = [row["team_id"] for row in div["table"]]
        out.append({
            "division": div["division"],
            "league_id": div["league_id"],
            "promoted": teams[:promote] if i > 0 else [],
            "relegated": teams[len(teams) - relegate:] if i < last and relegate > 0 else [],
        })
    return out


def knockout_seeds(table: list[dict], qualifiers) -> list[str]:
    """Hybrid format: group-stage table -> seed order for the knockout bracket (rank 1 = seed 1)."""
    if not is_int(qualifiers) or not 2 <= qualifiers <= len(table):
        raise validation_error(["qualifiers"], "qualifiers must be between 2 and the number of teams")
    return [row["team_id"] for row in table[:qualifiers]]
