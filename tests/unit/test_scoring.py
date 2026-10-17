import copy

import pytest

from app.domain import scoring
from app.errors import ApiError

EVENT_SPORT = {
    "sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
    "periods": {"count": 2, "duration_minutes": 20},
    "scoring_events": {"raid_point": {"points": 1}, "all_out": {"points": 2}},
    "draw_allowed": False, "overtime": {"policy": "golden_score", "duration_minutes": 5},
    "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2}},
}
INNINGS_SPORT = {
    "sport_id": "mini", "name": "Mini", "scoring_model": "innings",
    "periods": {"innings_per_team": 1, "overs_per_innings": 1, "balls_per_over": 2, "wickets_per_innings": 1},
    "scoring_events": {"hit": {"runs": 4, "legal_ball": True, "wicket": False},
                       "extra": {"runs": 1, "legal_ball": False, "wicket": False},
                       "out": {"runs": 0, "legal_ball": True, "wicket": True}},
    "draw_allowed": True, "overtime": {"policy": "super_over"},
    "roster": {"min_squad_size": 1, "max_squad_size": 2, "required_positions": {}},
}
ROUND_SPORT = {
    "sport_id": "bo3", "name": "Bo3", "scoring_model": "round", "periods": {"best_of": 3},
    "scoring_events": {"map": {"rounds": 1}}, "draw_allowed": False, "overtime": {"policy": "none"},
    "roster": {"min_squad_size": 1, "max_squad_size": 5, "required_positions": {}},
}
MATCH = {"match_id": "m1", "sport_id": "x", "league_id": None, "home": "A", "away": "B"}


def ev(seq, eid, etype, payload):
    return {"sequence": seq, "event_id": eid, "type": etype, "payload": payload, "signature": "s"}


def errcode(fn, *a):
    with pytest.raises(ApiError) as e:
        fn(*a)
    return e.value.code


# ---------------------------------------------------------------- validate_sport

@pytest.mark.parametrize("sport", [EVENT_SPORT, INNINGS_SPORT, ROUND_SPORT])
def test_valid_sports_normalize_with_default_tie_break(sport):
    cfg = scoring.validate_sport(copy.deepcopy(sport))
    assert cfg["sport_id"] == sport["sport_id"]
    assert cfg["tie_break_order"] == list(scoring.TIE_TOKENS)


@pytest.mark.parametrize("mutate,field", [
    (lambda s: s.update(sport_id="x'; DROP TABLE sports;--"), "sport_id"),
    (lambda s: s.update(sport_id="A"), "sport_id"),
    (lambda s: s.update(name=""), "name"),
    (lambda s: s.update(scoring_model="points"), "scoring_model"),
    (lambda s: s.update(periods={"count": 0, "duration_minutes": 1}), "periods"),
    (lambda s: s.update(periods="x"), "periods"),
    (lambda s: s.update(scoring_events={}), "scoring_events"),
    (lambda s: s.update(scoring_events={"Bad-Key": {"points": 1}}), "scoring_events"),
    (lambda s: s.update(scoring_events={"a": {"points": 0}}), "scoring_events"),
    (lambda s: s.update(scoring_events={"a": {"points": True}}), "scoring_events"),
    (lambda s: s.update(draw_allowed="no"), "draw_allowed"),
    (lambda s: s.update(overtime={"policy": "sudden"}), "overtime"),
    (lambda s: s.update(overtime={"policy": "none", "duration_minutes": -1}), "overtime"),
    (lambda s: s.update(tie_break_order=["scored", "scored"]), "tie_break_order"),
    (lambda s: s.update(tie_break_order=["coin"]), "tie_break_order"),
    (lambda s: s.update(roster={"min_squad_size": 5, "max_squad_size": 2, "required_positions": {}}), "roster"),
    (lambda s: s.update(roster={"min_squad_size": 1, "max_squad_size": 2, "required_positions": {"gk": -1}}), "roster"),
    (lambda s: s.update(roster="x"), "roster"),
])
def test_invalid_sport_fields(mutate, field):
    s = copy.deepcopy(EVENT_SPORT)
    mutate(s)
    with pytest.raises(ApiError) as e:
        scoring.validate_sport(s)
    assert e.value.status == 400 and e.value.code == "VALIDATION_ERROR"
    assert field in e.value.details["fields"]


def test_invalid_model_specific_shapes():
    s = copy.deepcopy(INNINGS_SPORT)
    s["scoring_events"]["hit"]["legal_ball"] = "yes"
    assert errcode(scoring.validate_sport, s) == "VALIDATION_ERROR"
    s = copy.deepcopy(INNINGS_SPORT)
    s["periods"]["balls_per_over"] = 0
    assert errcode(scoring.validate_sport, s) == "VALIDATION_ERROR"
    r = copy.deepcopy(ROUND_SPORT)
    r["periods"]["best_of"] = 4
    assert errcode(scoring.validate_sport, r) == "VALIDATION_ERROR"
    r = copy.deepcopy(ROUND_SPORT)
    r["scoring_events"]["map"] = {"rounds": 0}
    assert errcode(scoring.validate_sport, r) == "VALIDATION_ERROR"
    assert errcode(scoring.validate_sport, []) == "VALIDATION_ERROR"


def test_effective_tie_break_puts_draw_lots_last():
    assert scoring.effective_tie_break(["draw_lots", "scored"]) == ["scored", "draw_lots"]
    assert scoring.effective_tie_break(["scored"]) == ["scored", "draw_lots"]


# ---------------------------------------------------------------- validate_event_request

@pytest.mark.parametrize("body,field", [
    ({"event_id": "bad|id", "match_id": "m", "type": "match_start", "payload": {}}, "event_id"),
    ({"event_id": "e", "match_id": "", "type": "match_start", "payload": {}}, "match_id"),
    ({"event_id": "e", "match_id": "m", "type": "goal", "payload": {}}, "type"),
    ({"event_id": "e", "match_id": "m", "type": "match_start", "payload": []}, "payload"),
    ({"event_id": "e", "match_id": "m", "type": "match_init", "payload": {"sport_id": "s", "home_team_id": "a"}},
     "payload.away_team_id"),
    ({"event_id": "e", "match_id": "m", "type": "match_init",
      "payload": {"sport_id": "s", "home_team_id": "a", "away_team_id": "a"}}, "payload.away_team_id"),
    ({"event_id": "e", "match_id": "m", "type": "match_init",
      "payload": {"sport_id": "s", "home_team_id": "a", "away_team_id": "b", "league_id": 5}}, "payload.league_id"),
    ({"event_id": "e", "match_id": "m", "type": "score", "payload": {"team_id": "A"}}, "payload.event_type"),
    ({"event_id": "e", "match_id": "m", "type": "discipline", "payload": {"team_id": "A", "points": "1"}},
     "payload.points"),
    ({"event_id": "e", "match_id": "m", "type": "tiebreak_winner", "payload": {}}, "payload.team_id"),
    ({"event_id": "e", "match_id": "m", "type": "compensation", "payload": {"reason": "x"}}, "payload.compensates"),
    ({"event_id": "e", "match_id": "m", "type": "compensation", "payload": {"compensates": "e1", "reason": 3}},
     "payload.reason"),
])
def test_event_request_validation(body, field):
    with pytest.raises(ApiError) as e:
        scoring.validate_event_request(body)
    assert e.value.code == "VALIDATION_ERROR" and field in e.value.details["fields"]


def test_event_request_not_object():
    assert errcode(scoring.validate_event_request, "x") == "VALIDATION_ERROR"


# ---------------------------------------------------------------- projection + rules

def started(*extra):
    return [ev(1, "e1", "match_start", {})] + list(extra)


def test_event_model_projection_with_compensation_and_tiebreak():
    events = started(
        ev(2, "e2", "score", {"team_id": "A", "event_type": "all_out"}),
        ev(3, "e3", "score", {"team_id": "B", "event_type": "raid_point"}),
        ev(4, "e4", "discipline", {"team_id": "B", "points": -2}),
        ev(5, "e5", "compensation", {"compensates": "e2", "reason": "video"}),
        ev(6, "e6", "tiebreak_winner", {"team_id": "B"}),
        ev(7, "e7", "match_end", {}),
    )
    p = scoring.project(MATCH, EVENT_SPORT, events)
    assert p["status"] == "completed" and p["home"]["score"] == 0 and p["away"]["score"] == 1
    assert p["outcome"] == "away_win" and p["winner_team_id"] == "B"
    assert p["away"]["fair_play"] == -2 and p["version"] == 7
    assert p["events"][1]["compensated"] is True and p["events"][1]["compensated_by"] == "e5"
    assert p["home"]["wickets"] is None and p["home"]["overs"] is None


def test_level_without_tiebreak_after_compensation_is_undecided():
    events = started(
        ev(2, "e2", "tiebreak_winner", {"team_id": "A"}),
        ev(3, "e3", "match_end", {}),
        ev(4, "e4", "compensation", {"compensates": "e2", "reason": "x"}),
    )
    p = scoring.project(MATCH, EVENT_SPORT, events)
    assert p["outcome"] == "undecided" and p["winner_team_id"] is None


def test_level_with_draw_allowed_is_draw_and_tiebreak_home_win():
    sport = dict(EVENT_SPORT, draw_allowed=True)
    p = scoring.project(MATCH, sport, started(ev(2, "e2", "match_end", {})))
    assert p["outcome"] == "draw"
    p = scoring.project(MATCH, sport, started(ev(2, "t", "tiebreak_winner", {"team_id": "A"}),
                                              ev(3, "e", "match_end", {})))
    assert p["outcome"] == "home_win" and p["winner_team_id"] == "A"


def test_pending_outcome_until_completed():
    p = scoring.project(MATCH, EVENT_SPORT, [])
    assert p["status"] == "upcoming" and p["outcome"] == "pending"


def test_innings_projection_and_limits():
    events = started(
        ev(2, "e2", "score", {"team_id": "A", "event_type": "hit"}),
        ev(3, "e3", "score", {"team_id": "A", "event_type": "extra"}),
        ev(4, "e4", "score", {"team_id": "A", "event_type": "hit"}),
    )
    p = scoring.project(MATCH, INNINGS_SPORT, events)
    assert p["home"]["score"] == 9 and p["home"]["balls"] == 2 and p["home"]["overs"] == "1.0"
    assert p["home"]["wickets"] == 0
    assert errcode(scoring.check_append, MATCH, INNINGS_SPORT, events, "score",
                   {"team_id": "A", "event_type": "extra"}) == "INNINGS_COMPLETE"
    scoring.check_append(MATCH, INNINGS_SPORT, events, "score", {"team_id": "B", "event_type": "out"})
    wk = started(ev(2, "w", "score", {"team_id": "B", "event_type": "out"}))
    assert errcode(scoring.check_append, MATCH, INNINGS_SPORT, wk, "score",
                   {"team_id": "B", "event_type": "hit"}) == "INNINGS_COMPLETE"
    # A compensated ball no longer counts toward the limit.
    comp = events + [ev(5, "c", "compensation", {"compensates": "e4", "reason": "x"})]
    scoring.check_append(MATCH, INNINGS_SPORT, comp, "score", {"team_id": "A", "event_type": "hit"})


def test_round_model_series_decided():
    events = started(ev(2, "r1", "score", {"team_id": "A", "event_type": "map"}),
                     ev(3, "r2", "score", {"team_id": "A", "event_type": "map"}))
    assert scoring.project(MATCH, ROUND_SPORT, events)["home"]["score"] == 2
    assert errcode(scoring.check_append, MATCH, ROUND_SPORT, events, "score",
                   {"team_id": "B", "event_type": "map"}) == "SERIES_ALREADY_DECIDED"


def test_state_machine_rules():
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, [], "score",
                   {"team_id": "A", "event_type": "raid_point"}) == "MATCH_NOT_IN_PROGRESS"
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, [], "match_end", {}) == "ILLEGAL_TRANSITION"
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, started(), "match_start", {}) == "ILLEGAL_TRANSITION"
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, started(), "match_end", {}) == "TIE_NOT_ALLOWED"
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, [], "match_init", {}) == "MATCH_EXISTS"
    scoring.check_append(MATCH, EVENT_SPORT, [], "match_start", {})
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, started(), "score",
                   {"team_id": "Z", "event_type": "raid_point"}) == "VALIDATION_ERROR"
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, started(), "score",
                   {"team_id": "A", "event_type": "goal"}) == "UNKNOWN_EVENT_TYPE"
    scoring.check_append(MATCH, EVENT_SPORT, started(), "discipline", {"team_id": "A", "points": -1})
    scoring.check_append(MATCH, EVENT_SPORT, started(ev(2, "s", "score", {"team_id": "A", "event_type": "all_out"})),
                         "match_end", {})


def test_compensation_rules():
    target = {"match_id": "m1", "event_id": "e2", "type": "score"}
    events = started(ev(2, "e2", "score", {"team_id": "A", "event_type": "all_out"}))
    scoring.check_append(MATCH, EVENT_SPORT, events, "compensation", {"compensates": "e2"}, target)
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, events, "compensation",
                   {"compensates": "nope"}, None) == "EVENT_NOT_FOUND"
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, events, "compensation", {"compensates": "e2"},
                   dict(target, match_id="other")) == "INVALID_COMPENSATION"
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, events, "compensation", {"compensates": "e1"},
                   {"match_id": "m1", "event_id": "e1", "type": "match_start"}) == "INVALID_COMPENSATION"
    done = events + [ev(3, "c", "compensation", {"compensates": "e2"})]
    assert errcode(scoring.check_append, MATCH, EVENT_SPORT, done, "compensation", {"compensates": "e2"},
                   target) == "INVALID_COMPENSATION"
