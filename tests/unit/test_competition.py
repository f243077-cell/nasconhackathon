import pytest

from app.domain import competition
from app.errors import ApiError


def table(*teams):
    return [{"rank": i + 1, "team_id": t} for i, t in enumerate(teams)]


def test_three_division_pyramid():
    divs = [{"division": 2, "league_id": "d2", "table": table("e", "f", "g")},
            {"division": 1, "league_id": "d1", "table": table("a", "b", "c")},
            {"division": 3, "league_id": "d3", "table": table("h", "i")}]
    out = competition.promotion_relegation(divs, promote=1, relegate=1)
    assert [d["division"] for d in out] == [1, 2, 3]
    assert out[0]["promoted"] == [] and out[0]["relegated"] == ["c"]
    assert out[1]["promoted"] == ["e"] and out[1]["relegated"] == ["g"]
    assert out[2]["promoted"] == ["h"] and out[2]["relegated"] == []


def test_no_relegation_configured():
    out = competition.promotion_relegation([{"division": 1, "league_id": "a", "table": table("x", "y")},
                                            {"division": 2, "league_id": "b", "table": table("z")}], 1, 0)
    assert out[0]["relegated"] == [] and out[1]["promoted"] == ["z"]


def test_knockout_seeds():
    assert competition.knockout_seeds(table("a", "b", "c", "d", "e"), 4) == ["a", "b", "c", "d"]
    for bad in (1, 6, "4", True):
        with pytest.raises(ApiError):
            competition.knockout_seeds(table("a", "b", "c", "d", "e"), bad)
