import itertools
import random

import pytest

from app.domain.fixtures import generate
from app.domain.fixtures.swiss import _min_cost_pairing
from app.errors import ApiError


def teams(n):
    return [f"t{i}" for i in range(1, n + 1)]


def sw(n, **params):
    return generate({"format": "swiss", "teams": teams(n), "params": params})


@pytest.mark.parametrize("n", [2, 3, 4, 5, 8, 9, 64])
def test_round1_exact(n):
    out = sw(n)
    m = n // 2
    assert out["round"] == 1 and out["total_rounds"] == max(1, (n - 1).bit_length())
    assert out["bye"] == (f"t{n}" if n % 2 else None)
    assert [(p["match_id"], p["home"], p["away"]) for p in out["pairings"]] == [
        (f"SW-R1-M{i}", f"t{i}", f"t{i + m}") for i in range(1, m + 1)]
    assert [s["team_id"] for s in out["standings"]] == teams(n)
    assert all(s["score"] == 0.0 and s["buchholz"] == 0.0 for s in out["standings"])


def test_standings_and_buchholz():
    hist = [{"round": 1, "bye": "t5", "matches": [{"home": "t1", "away": "t3", "result": "home"},
                                                   {"home": "t2", "away": "t4", "result": "draw"}]}]
    out = sw(5, round=2, total_rounds=3, history=hist)
    st = {s["team_id"]: s for s in out["standings"]}
    assert st["t1"]["score"] == 1.0 and st["t5"]["score"] == 1.0 and st["t2"]["score"] == 0.5
    assert st["t1"]["buchholz"] == 0.0 and st["t3"]["buchholz"] == 1.0 and st["t5"]["buchholz"] == 0.0
    assert st["t2"]["buchholz"] == 0.5
    assert [s["team_id"] for s in out["standings"]] == ["t1", "t5", "t2", "t4", "t3"]
    assert [s["rank"] for s in out["standings"]] == [1, 2, 3, 4, 5]
    # bye: lowest score without a bye -> t3
    assert out["bye"] == "t3"
    _check_pairing_props(out, hist, 5)


def _check_pairing_props(out, hist, n):
    seen = [out["bye"]] if out["bye"] else []
    played = {frozenset((m["home"], m["away"])) for h in hist for m in h["matches"]}
    for p in out["pairings"]:
        seen += [p["home"], p["away"]]
        assert frozenset((p["home"], p["away"])) not in played
    assert sorted(seen) == sorted(teams(n))


def _brute_min(players, score, played):
    best = None
    def rec(rest, cost):
        nonlocal best
        if not rest:
            best = cost if best is None else min(best, cost)
            return
        a = rest[0]
        for b in rest[1:]:
            if frozenset((a, b)) in played:
                continue
            rec([x for x in rest if x not in (a, b)], cost + abs(score[a] - score[b]))
    rec(players, 0)
    return best


@pytest.mark.parametrize("trial", range(60))
def test_min_cost_matches_brute_force(trial):
    rng = random.Random(trial)
    n = rng.choice([4, 6, 8, 10])
    ps = teams(n)
    score = {t: rng.randint(0, 6) for t in ps}
    played = {frozenset(pr) for pr in itertools.combinations(ps, 2) if rng.random() < 0.35}
    got = _min_cost_pairing(ps, score, played)
    want = _brute_min(ps, score, played)
    if want is None:
        assert got is None
    else:
        assert got is not None
        assert sum(abs(score[a] - score[b]) for a, b in got) == want
        assert all(frozenset(pr) not in played for pr in got)


def test_greedy_would_fail():
    # scores t1=3,t2=3,t3=2,t4=2 but t1-t2 already met: greedy pairs t1-t3? optimum = 2 either way;
    # construct a case where greedy top-down gives 4 but optimum is 2
    score = {"a": 4, "b": 4, "c": 2, "d": 0}
    played = {frozenset(("a", "b"))}
    got = _min_cost_pairing(["a", "b", "c", "d"], score, played)
    assert sum(abs(score[x] - score[y]) for x, y in got) == 6  # a-c(2)+b-d(4) or a-d(4)+b-c(2)


def _play_round(out, rng):
    return {"round": out["round"], "bye": out["bye"],
            "matches": [{"home": p["home"], "away": p["away"], "result": rng.choice(["home", "away", "draw"])}
                        for p in out["pairings"]]}


@pytest.mark.parametrize("n", [5, 7, 8, 16, 33, 64])
def test_full_tournament_properties(n):
    rng = random.Random(n)
    total = min(n - 1, 6)
    hist = []
    for r in range(1, total + 1):
        out = sw(n, round=r, total_rounds=total, history=hist)
        _check_pairing_props(out, hist, n)
        if n % 2:
            assert out["bye"] not in {h["bye"] for h in hist}
        hist.append(_play_round(out, rng))


def test_no_valid_pairing():
    # after 3 rounds {t1,t5,t6} and {t2,t3,t4} are the only allowed pairs: two odd triangles, no pairing
    def rnd(r, *pairs):
        return {"round": r, "bye": None, "matches": [{"home": h, "away": a, "result": "home"} for h, a in pairs]}
    hist = [rnd(1, ("t2", "t5"), ("t3", "t6"), ("t1", "t4")),
            rnd(2, ("t3", "t5"), ("t4", "t6"), ("t1", "t2")),
            rnd(3, ("t4", "t5"), ("t2", "t6"), ("t1", "t3"))]
    with pytest.raises(ApiError) as e:
        sw(6, round=4, total_rounds=5, history=hist)
    assert e.value.status == 409 and e.value.code == "NO_VALID_PAIRING" and e.value.details == {"round": 4}


@pytest.mark.parametrize("params", [
    {"round": 2},  # missing history
    {"round": 0},
    {"total_rounds": 4},
    {"total_rounds": "2"},
    {"round": 1, "history": [{"round": 1, "bye": None, "matches": []}]},
    {"round": 2, "total_rounds": 3, "history": [{"round": 1, "bye": "zz", "matches": []}]},
    {"round": 2, "total_rounds": 3, "history": [{"round": 1, "bye": None,
                                                 "matches": [{"home": "t1", "away": "t1", "result": "home"}]}]},
    {"round": 2, "total_rounds": 3, "history": [{"round": 1, "bye": None,
                                                 "matches": [{"home": "t1", "away": "t2", "result": "win"}]}]},
    {"history": "x"},
])
def test_validation(params):
    with pytest.raises(ApiError) as e:
        sw(4, **params)
    assert e.value.status == 400 and e.value.code == "VALIDATION_ERROR"
