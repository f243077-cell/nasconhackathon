from app.domain.standings import compute, lots_key

FOOTBALL = {"sport_id": "football", "scoring_model": "event", "periods": {"count": 2, "duration_minutes": 45},
            "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]}
CRICKET = {"sport_id": "cricket", "scoring_model": "innings",
           "periods": {"innings_per_team": 1, "overs_per_innings": 20, "balls_per_over": 6, "wickets_per_innings": 10}}


def side(team, score, fair_play=0, balls=None, wickets=None):
    return {"team_id": team, "score": score, "balls": balls, "wickets": wickets, "fair_play": fair_play}


def done(h, hs, a, as_, outcome=None, **kw):
    if outcome is None:
        outcome = "home_win" if hs > as_ else "away_win" if as_ > hs else "draw"
    return {"status": "completed", "outcome": outcome, "home": side(h, hs, **kw.get("hk", {})),
            "away": side(a, as_, **kw.get("ak", {}))}


def todo(h, a):
    return {"status": "upcoming", "outcome": "pending", "home": side(h, 0), "away": side(a, 0)}


def league(teams, spots=2, **kw):
    return {"league_id": kw.pop("league_id", "lg-1"), "sport_id": "football", "teams": teams,
            "qualification_spots": spots, "lots_seed": 42, **kw}


def order(out):
    return [r["team_id"] for r in out["table"]]


def test_lots_vector_2():
    keys = {t: lots_key(42, "lg-1", t) for t in ("t1", "t2", "t3")}
    assert keys["t1"] == "0613316991ce0ac31e88d6003e3ff4d5e21bb072ac5f81b42c0cdc6598453293"
    assert keys["t3"] == "c8f28e3c2f1eb6c4f636b4f57050e3362a2b39c07fda9b61742a26dd20397028"
    assert keys["t2"] == "e3e3a14e22727f936e1f288cf5d02a8a9362b1da13c5432725fc10b2c7955dd9"
    out = compute(league(["t1", "t2", "t3"]), FOOTBALL, [])
    assert order(out) == ["t1", "t3", "t2"]
    assert [r["resolved_by"] for r in out["table"]] == ["draw_lots", "draw_lots", None]


def test_basic_table_and_h2h_every_pair():
    out = compute(league(["t1", "t2", "t3"]), FOOTBALL, [done("t1", 2, "t2", 1), done("t2", 1, "t3", 1), todo("t1", "t3")])
    t = {r["team_id"]: r for r in out["table"]}
    assert t["t1"] == {"rank": 1, "team_id": "t1", "played": 1, "won": 1, "drawn": 0, "lost": 0, "scored": 2,
                       "conceded": 1, "diff": 1, "points": 3, "fair_play": 0, "status": t["t1"]["status"],
                       "resolved_by": None}
    assert t["t2"]["drawn"] == 1 and t["t2"]["lost"] == 1 and t["t2"]["points"] == 1
    assert set(out["h2h"]) == {"t1", "t2", "t3"}
    for a in out["h2h"]:
        assert set(out["h2h"][a]) == {"t1", "t2", "t3"} - {a}
    assert out["h2h"]["t1"]["t2"] == {"played": 1, "points": 3, "scored": 2, "conceded": 1}
    assert out["h2h"]["t1"]["t3"] == {"played": 0, "points": 0, "scored": 0, "conceded": 0}
    assert out["league_id"] == "lg-1" and out["sport_id"] == "football" and out["qualification_spots"] == 2


def test_three_way_mini_league_restarts_on_split():
    ms = [done("t1", 1, "t2", 0), done("t2", 1, "t3", 0), done("t3", 1, "t1", 0),
          done("t1", 3, "t4", 0), done("t2", 1, "t4", 0), done("t3", 1, "t4", 0)]
    out = compute(league(["t1", "t2", "t3", "t4"]), FOOTBALL, ms)
    assert order(out) == ["t1", "t2", "t3", "t4"]
    # t1 split off by overall_diff; {t2,t3} restarts at h2h_points (t2 beat t3)
    assert [r["resolved_by"] for r in out["table"]] == ["overall_diff", "h2h_points", None, None]


def test_h2h_uses_only_current_group():
    # t1,t2 level on points; t1 beat t2 head-to-head despite worse overall diff
    ms = [done("t1", 1, "t2", 0), done("t2", 5, "t3", 0), done("t3", 1, "t1", 0)]
    out = compute(league(["t1", "t2", "t3"]), FOOTBALL, ms)
    # all on 3 points: 3-way mini-league h2h_points equal, h2h_diff: t1 0, t2 +4, t3 -4
    assert order(out) == ["t2", "t1", "t3"]
    assert out["table"][0]["resolved_by"] == "h2h_diff"


def test_fair_play_and_scored_and_custom_order():
    ms = [done("t1", 2, "t2", 2, hk={"fair_play": -2}, ak={"fair_play": 0})]
    out = compute(league(["t1", "t2"], tie_break_order=["fair_play"]), FOOTBALL, ms)
    assert order(out) == ["t2", "t1"] and out["table"][0]["resolved_by"] == "fair_play"
    assert out["table"][1]["fair_play"] == -2


def test_tiebreak_win_counts_as_win_and_undecided_not_played():
    ms = [done("t1", 1, "t2", 1, outcome="away_win"),
          {"status": "completed", "outcome": "undecided", "home": side("t1", 2), "away": side("t3", 2)}]
    out = compute(league(["t1", "t2", "t3"], spots=1), FOOTBALL, ms)
    t = {r["team_id"]: r for r in out["table"]}
    assert t["t2"]["won"] == 1 and t["t2"]["points"] == 3 and t["t1"]["lost"] == 1
    assert t["t3"]["played"] == 0 and t["t1"]["played"] == 1


def test_custom_points():
    out = compute(league(["t1", "t2"], points={"win": 2, "draw": 1, "loss": 0}), FOOTBALL, [done("t1", 1, "t2", 0)])
    assert out["table"][0]["points"] == 2


def test_nrr_full_overs_when_all_out():
    ms = [done("t1", 150, "t2", 100, hk={"balls": 120, "wickets": 5}, ak={"balls": 60, "wickets": 10})]
    out = compute({**league(["t1", "t2"]), "sport_id": "cricket"}, CRICKET, ms)
    t = {r["team_id"]: r for r in out["table"]}
    assert t["t1"]["diff"] == 2.5 and t["t2"]["diff"] == -2.5


def test_nrr_partial_overs_rounded():
    ms = [done("t1", 120, "t2", 119, hk={"balls": 91, "wickets": 3}, ak={"balls": 120, "wickets": 8})]
    out = compute({**league(["t1", "t2"]), "sport_id": "cricket"}, CRICKET, ms)
    t = {r["team_id"]: r for r in out["table"]}
    assert t["t1"]["diff"] == round(120 / (91 / 6) - 119 / 20, 3)
    assert t["t2"]["diff"] == round(119 / 20 - 120 / (91 / 6), 3)


def test_round_model_diff():
    sport = {"scoring_model": "round", "periods": {"best_of": 3}}
    out = compute(league(["t1", "t2"]), sport, [done("t1", 2, "t2", 1)])
    assert out["table"][0]["diff"] == 1


def test_qualification_status():
    # 4 teams, 1 spot, win=3. t1 has 9 pts and 0 remaining; others max <= 6
    ms = [done("t1", 1, "t2", 0), done("t1", 1, "t3", 0), done("t1", 1, "t4", 0),
          done("t2", 1, "t3", 0), todo("t2", "t4"), todo("t3", "t4")]
    out = compute(league(["t1", "t2", "t3", "t4"], spots=1), FOOTBALL, ms)
    st = {r["team_id"]: r["status"] for r in out["table"]}
    assert st["t1"] == "clinched"
    assert st["t3"] == "eliminated" and st["t4"] == "eliminated"  # max 3 < 9
    assert st["t2"] == "eliminated"  # max 6 < 9
    out = compute(league(["t1", "t2", "t3", "t4"], spots=2), FOOTBALL, ms)
    st = {r["team_id"]: r["status"] for r in out["table"]}
    assert st["t1"] == "clinched" and st["t2"] == "still_possible" and st["t4"] == "still_possible"


def test_draw_lots_appended_when_missing():
    out = compute(league(["t1", "t2", "t3"], tie_break_order=["scored"]), FOOTBALL, [])
    assert order(out) == ["t1", "t3", "t2"]
