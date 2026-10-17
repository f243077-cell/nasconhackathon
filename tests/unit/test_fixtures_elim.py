from collections import Counter

import pytest

from app.domain.fixtures import generate
from app.domain.fixtures.bracket import seed_order
from app.errors import ApiError

FIELDS = {"match_id", "bracket", "round", "index", "home", "away", "home_seed", "away_seed", "bye", "winner",
          "loser", "winner_to", "loser_to"}


def teams(n):
    return [f"t{i}" for i in range(1, n + 1)]


def se(n, **params):
    return generate({"format": "single_elim", "teams": teams(n), "params": params})


def de(n, **params):
    return generate({"format": "double_elim", "teams": teams(n), "params": params})


def all_matches(out):
    if out["format"] == "single_elim":
        return [m for r in out["rounds"] for m in r["matches"]]
    return ([m for r in out["winners"] for m in r["matches"]] + [m for r in out["losers"] for m in r["matches"]]
            + out["grand_final"])


def test_seed_order():
    assert seed_order(2) == [1, 2]
    assert seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]


@pytest.mark.parametrize("n", [2, 3, 5, 6, 7, 8, 13, 16, 100, 128])
def test_single_elim_structure(n):
    out = se(n)
    b = out["bracket_size"]
    assert b >= n and b // 2 < n and b & (b - 1) == 0
    assert len(out["rounds"]) == b.bit_length() - 1
    order = seed_order(b)
    for r in out["rounds"]:
        assert len(r["matches"]) == b // 2 ** r["round"]
        for m in r["matches"]:
            assert set(m) >= FIELDS and m["match_id"] == f"R{m['round']}M{m['index']}"
    for i, m in enumerate(out["rounds"][0]["matches"], 1):
        s1, s2 = sorted(order[2 * i - 2: 2 * i])
        assert m["home"] == f"t{s1}" and m["home_seed"] == s1
        if s2 > n:
            assert m["bye"] and m["away"] is None and m["winner"] == m["home"]
        else:
            assert not m["bye"] and m["away"] == f"t{s2}" and m["away_seed"] == s2 and m["winner"] is None
        dest = m["winner_to"]
        if len(out["rounds"]) > 1:
            assert dest == {"match_id": f"R2M{(i + 1) // 2}", "slot": "home" if i % 2 else "away"}
            if m["bye"]:
                nxt = next(x for x in out["rounds"][1]["matches"] if x["match_id"] == dest["match_id"])
                assert nxt[dest["slot"]] == m["home"]
    assert out["rounds"][-1]["matches"][0]["winner_to"] is None


def test_single_elim_results_and_third_place():
    out = se(4, third_place_match=True, results=[
        {"match_id": "R2M1", "winner": "t3"},  # out of order on purpose
        {"match_id": "R1M1", "winner": "t1"}, {"match_id": "R1M2", "winner": "t3"},
        {"match_id": "TP", "winner": "t2"}])
    by = {m["match_id"]: m for m in all_matches(out)}
    assert by["R1M1"]["loser_to"] == {"match_id": "TP", "slot": "home"}
    assert by["R1M2"]["loser_to"] == {"match_id": "TP", "slot": "away"}
    assert by["TP"]["bracket"] == "third_place"
    assert (by["R1M2"]["winner"], by["R1M2"]["loser"]) == ("t3", "t2")
    assert (by["R2M1"]["home"], by["R2M1"]["away"]) == ("t1", "t3")
    assert by["R2M1"]["home_seed"] == 1 and by["R2M1"]["away_seed"] == 3
    assert by["TP"]["home"] == "t4" and by["TP"]["away"] == "t2" and by["TP"]["winner"] == "t2"


@pytest.mark.parametrize("params", [
    {"results": [{"match_id": "R9M1", "winner": "t1"}]},
    {"results": [{"match_id": "R1M1", "winner": "t2"}]},
    {"results": [{"match_id": "R2M1", "winner": "t1"}]},
    {"results": "x"},
    {"results": [{"match_id": "R1M1"}]},
    {"third_place_match": "yes"},
])
def test_single_elim_bad_results(params):
    with pytest.raises(ApiError) as e:
        se(4, **params)
    assert e.value.status == 400


@pytest.mark.parametrize("n", [3, 4, 5, 6, 8, 13, 16, 33, 128])
@pytest.mark.parametrize("reset", [False, True])
def test_double_elim_structure_and_routing(n, reset):
    out = de(n, bracket_reset=reset)
    b = out["bracket_size"]
    k = b.bit_length() - 1
    assert out["bracket_reset"] is reset
    assert [len(r["matches"]) for r in out["winners"]] == [b // 2 ** r for r in range(1, k + 1)]
    assert len(out["losers"]) == 2 * (k - 1)
    for r in out["losers"]:
        j = (r["round"] + 1) // 2
        assert len(r["matches"]) == b // 2 ** (j + 1)
    assert sum(len(r["matches"]) for r in out["losers"]) == b - 2
    gf_ids = [m["match_id"] for m in out["grand_final"]]
    assert gf_ids == (["GF1", "GF2"] if reset else ["GF1"])

    ms = all_matches(out)
    ids = {m["match_id"] for m in ms}
    feeds = Counter()
    for m in ms:
        assert set(m) >= FIELDS
        if m["bracket"] == "winners":
            assert m["loser_to"] is not None
        if m["bracket"] == "losers":
            assert m["loser_to"] is None
        for d in (m["winner_to"], m["loser_to"]):
            if d:
                assert d["match_id"] in ids
                feeds[(d["match_id"], d["slot"])] += 1
        terminal = m["match_id"] == ("GF2" if reset else "GF1")
        assert (m["winner_to"] is None) == terminal
    for m in ms:
        if m["match_id"].startswith("WR1M"):
            continue
        for slot in ("home", "away"):
            assert feeds[(m["match_id"], slot)] == 1, (m["match_id"], slot)
    by = {m["match_id"]: m for m in ms}
    assert by[f"WR{k}M1"]["winner_to"] == {"match_id": "GF1", "slot": "home"}
    assert by[f"WR{k}M1"]["loser_to"] == {"match_id": f"LR{2 * k - 2}M1", "slot": "away"}
    assert by[f"LR{2 * k - 2}M1"]["winner_to"] == {"match_id": "GF1", "slot": "away"}


def _play_to_gf(n, reset, gf1_winner_is_lb):
    """Higher seed (lower number) always wins until GF1."""
    results = []
    for _ in range(200):
        out = de(n, bracket_reset=reset, results=results)
        pending = [m for m in all_matches(out) if m["winner"] is None and m["home"] and m["away"]
                   and m["match_id"] not in ("GF1", "GF2")]
        if not pending:
            break
        for m in pending:
            w = m["home"] if m["home_seed"] < m["away_seed"] else m["away"]
            results.append({"match_id": m["match_id"], "winner": w})
    gf1 = out["grand_final"][0]
    assert gf1["home"] and gf1["away"]
    results.append({"match_id": "GF1", "winner": gf1["away"] if gf1_winner_is_lb else gf1["home"]})
    return de(n, bracket_reset=reset, results=results)


@pytest.mark.parametrize("n", [3, 5, 8])
def test_double_elim_gf2_required(n):
    out = de(n, bracket_reset=True)
    assert out["grand_final"][1]["conditional"] is True and out["grand_final"][1]["required"] is None
    out = _play_to_gf(n, True, gf1_winner_is_lb=True)
    gf1, gf2 = out["grand_final"]
    assert gf2["required"] is True and (gf2["home"], gf2["away"]) == (gf1["home"], gf1["away"])
    out = _play_to_gf(n, True, gf1_winner_is_lb=False)
    assert out["grand_final"][1]["required"] is False
    out = _play_to_gf(n, False, gf1_winner_is_lb=True)
    assert len(out["grand_final"]) == 1


def test_double_elim_wr1_byes_like_single():
    d, s = de(5), se(5)
    for dm, sm in zip(d["winners"][0]["matches"], s["rounds"][0]["matches"]):
        for f in ("home", "away", "home_seed", "away_seed", "bye", "winner"):
            assert dm[f] == sm[f]


def test_double_elim_min_teams():
    with pytest.raises(ApiError):
        de(2)
