from collections import Counter

import pytest

from app.domain.fixtures import generate
from app.errors import ApiError


def rr(n, **params):
    return generate({"format": "round_robin", "teams": [f"t{i}" for i in range(1, n + 1)], "params": params})


@pytest.mark.parametrize("n", range(2, 41))
@pytest.mark.parametrize("legs", [1, 2])
def test_structure(n, legs):
    out = rr(n, legs=legs)
    per_leg = n - 1 if n % 2 == 0 else n
    assert out["round_count"] == per_leg * legs
    assert [r["round"] for r in out["rounds"]] == list(range(1, per_leg * legs + 1))
    pairs, ordered = Counter(), Counter()
    for leg in range(1, legs + 1):
        home, away, bye = Counter(), Counter(), Counter()
        for r in out["rounds"][(leg - 1) * per_leg: leg * per_leg]:
            assert len(r["matches"]) == n // 2
            assert len(r["byes"]) == (n % 2)
            seen = list(r["byes"])
            for i, m in enumerate(r["matches"], 1):
                assert m["match_id"] == f"RR-L{leg}-R{r['round']}-M{i}"
                assert m["leg"] == leg and m["status"] == "scheduled" and m["awarded_to"] is None
                seen += [m["home"], m["away"]]
                home[m["home"]] += 1
                away[m["away"]] += 1
                pairs[frozenset((m["home"], m["away"]))] += 1
                ordered[(m["home"], m["away"])] += 1
            assert sorted(seen) == sorted(f"t{i}" for i in range(1, n + 1))
            bye.update(r["byes"])
        for t in (f"t{i}" for i in range(1, n + 1)):
            assert abs(home[t] - away[t]) <= 1
            if n % 2:
                assert bye[t] == 1
    assert len(pairs) == n * (n - 1) // 2 and set(pairs.values()) == {legs}
    if legs == 2:
        assert set(ordered.values()) == {1}
    assert out["summary"] == {"total": legs * n * (n - 1) // 2, "scheduled": legs * n * (n - 1) // 2,
                              "forfeit": 0, "voided": 0}


def test_spec_example_n5_round1():
    r1 = rr(5)["rounds"][0]
    assert r1["byes"] == ["t1"]
    assert r1["matches"][0]["home"] == "t2" and r1["matches"][0]["away"] == "t5"


def test_forfeit_remaining():
    out = rr(5, withdrawals=[{"team_id": "t3", "after_round": 2}])
    for r in out["rounds"]:
        for m in r["matches"]:
            if "t3" in (m["home"], m["away"]):
                if r["round"] > 2:
                    other = m["away"] if m["home"] == "t3" else m["home"]
                    assert m["status"] == "forfeit" and m["awarded_to"] == other
                else:
                    assert m["status"] == "scheduled"
    s = out["summary"]
    assert s["total"] == 10 and s["forfeit"] + s["scheduled"] == 10 and s["voided"] == 0


def test_void_all_and_double_withdrawal():
    out = rr(4, withdrawal_policy="void_all", withdrawals=[{"team_id": "t1", "after_round": 1}])
    for r in out["rounds"]:
        for m in r["matches"]:
            if "t1" in (m["home"], m["away"]):
                assert m["status"] == "voided" and m["awarded_to"] is None
    assert out["summary"]["voided"] == 3

    out = rr(4, withdrawals=[{"team_id": "t1", "after_round": 0}, {"team_id": "t2", "after_round": 0}])
    for r in out["rounds"]:
        for m in r["matches"]:
            if {m["home"], m["away"]} == {"t1", "t2"}:
                assert m["status"] == "voided"
    assert out["summary"] == {"total": 6, "scheduled": 1, "forfeit": 4, "voided": 1}


@pytest.mark.parametrize("body", [
    {"format": "round_robin", "teams": ["t1"]},
    {"format": "round_robin", "teams": ["t1", "t1"]},
    {"format": "round_robin", "teams": [f"t{i}" for i in range(41)]},
    {"format": "round_robin", "teams": ["t1", "bad|id"]},
    {"format": "round_robin", "teams": "t1,t2"},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"legs": 3}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"legs": True}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"legs": "1"}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"withdrawal_policy": "x"}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"withdrawals": [{"team_id": "tx", "after_round": 0}]}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"withdrawals": [{"team_id": "t1", "after_round": 2}]}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"withdrawals": [{"team_id": "t1", "after_round": -1}]}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": {"withdrawals": "x"}},
    {"format": "round_robin", "teams": ["t1", "t2"], "params": []},
    {"format": "nope", "teams": ["t1", "t2"]},
    [],
])
def test_validation(body):
    with pytest.raises(ApiError) as e:
        generate(body)
    assert e.value.status == 400 and e.value.code == "VALIDATION_ERROR"
