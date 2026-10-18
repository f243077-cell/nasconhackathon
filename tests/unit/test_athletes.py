import pytest

from app.domain import athletes as ath
from app.errors import ApiError


def proj(mid, home, away, hs, as_, status="completed", outcome=None, winner=None, at=None, league="league-alpha-1"):
    if outcome is None and status == "completed":
        outcome = "draw" if hs == as_ else ("home_win" if hs > as_ else "away_win")
        winner = None if hs == as_ else (home if hs > as_ else away)
    return {"match_id": mid, "league_id": league, "status": status, "outcome": outcome or "pending",
            "winner_team_id": winner, "home": {"team_id": home, "score": hs}, "away": {"team_id": away, "score": as_},
            "scheduled_at": at, "venue": "Falcon Park"}


MATCHES = [
    proj("m1", "club-a", "club-b", 2, 1, at="2026-10-01T10:00:00Z"),           # W at home
    proj("m2", "club-c", "club-a", 3, 0, at="2026-10-05T10:00:00Z"),           # L away
    proj("m3", "club-a", "club-c", 1, 1, at="2026-10-09T10:00:00Z"),           # D
    proj("m4", "club-b", "club-c", 4, 0, at="2026-10-10T10:00:00Z"),           # not ours
    proj("m5", "club-a", "club-b", 1, 1, status="completed", outcome="undecided", at="2026-10-11T10:00:00Z"),
    proj("m6", "club-a", "club-b", 0, 0, status="in_progress", at="2026-10-18T10:00:00Z"),
    proj("m7", "club-b", "club-a", 0, 0, status="upcoming", at="2026-10-25T10:00:00Z"),
    proj("m8", "club-a", "club-c", 0, 0, status="postponed", at="2026-10-20T10:00:00Z"),
    proj("m9", "club-a", "club-c", 0, 0, status="upcoming", at=None),
    proj("m10", "club-c", "club-a", 0, 0, status="cancelled", at="2026-10-21T10:00:00Z"),
    proj("m11", "club-b", "club-a", 1, 2, at="2026-10-12T10:00:00Z"),          # W away, tiebreak-free
]


def test_career_counts_only_completed_decided_matches_of_own_clubs():
    c = ath.career({"club-a"}, MATCHES)
    assert (c["played"], c["won"], c["drawn"], c["lost"]) == (4, 2, 1, 1)
    assert c["win_rate"] == 0.5
    assert [r["match_id"] for r in c["recent_matches"]] == ["m11", "m3", "m2", "m1"]  # newest first
    m2 = next(r for r in c["recent_matches"] if r["match_id"] == "m2")
    assert m2 == {"match_id": "m2", "league_id": "league-alpha-1", "club_id": "club-a", "opponent_id": "club-c",
                  "result": "L", "score": "0-3", "scheduled_at": "2026-10-05T10:00:00Z", "vod_route": "/web/matches/m2/vod"}


def test_career_empty_and_tiebreak_win_counts_as_win():
    assert ath.career(set(), MATCHES) == {"played": 0, "won": 0, "drawn": 0, "lost": 0, "win_rate": 0.0,
                                          "recent_matches": []}
    shootout = proj("t1", "club-a", "club-b", 1, 1, outcome="home_win", winner="club-a", at="2026-10-02T00:00:00Z")
    assert ath.career({"club-a"}, [shootout])["won"] == 1


def test_recent_matches_are_capped():
    many = [proj(f"x{i}", "club-a", "club-b", 1, 0, at=f"2026-09-{i + 1:02d}T00:00:00Z") for i in range(25)]
    c = ath.career({"club-a"}, many)
    assert c["played"] == 25 and len(c["recent_matches"]) == ath.RECENT_LIMIT


def test_upcoming_soonest_first_unscheduled_last_with_postponed():
    up = ath.upcoming({"club-a"}, MATCHES)
    assert [u["match_id"] for u in up] == ["m8", "m7", "m9"]
    assert up[1] == {"match_id": "m7", "league_id": "league-alpha-1", "club_id": "club-a", "opponent_id": "club-b",
                     "home": False, "status": "upcoming", "scheduled_at": "2026-10-25T10:00:00Z", "venue": "Falcon Park"}


def test_affiliations_from_roster_placements():
    player = {"player_id": "p1", "club_id": "club-a"}
    placements = [{"league_id": "l1", "squad_id": "sq-b", "club_id": "club-b", "parent_squad_id": "sq-a",
                   "parent_club_id": "club-a"},
                  {"league_id": "l2", "squad_id": None, "club_id": None, "parent_squad_id": None, "parent_club_id": None}]
    assert ath.affiliations(player, placements) == [
        {"club_id": "club-b", "league_id": "l1", "squad_id": "sq-b", "status": "on_loan", "on_loan_from": "club-a"}]


def test_affiliations_fall_back_to_registered_club_only_without_roster():
    player = {"player_id": "p1", "club_id": "club-a"}
    assert ath.affiliations(player, []) == [
        {"club_id": "club-a", "league_id": None, "squad_id": "club-a", "status": "registered", "on_loan_from": None}]
    released = [{"league_id": "l1", "squad_id": None, "club_id": None}]
    assert ath.affiliations(player, released) == []
    assert ath.affiliations({"player_id": "p2", "club_id": None}, []) == []


def test_profile_assembles_everything():
    player = {"player_id": "p1", "name": "Ali", "position": "fw", "role": "starter", "tenant_id": "tenant-alpha",
              "club_id": "club-a"}
    affs = ath.affiliations(player, [])
    vods = [{"vod_id": 1, "ended_at": "2026-10-01T00:00:00Z"}, {"vod_id": 2, "ended_at": "2026-10-03T00:00:00Z"}]
    out = ath.profile(player, affs, MATCHES, vods, follower_count=7, following=True)
    assert out["athlete_id"] == "p1" and out["name"] == "Ali" and out["tenant_id"] == "tenant-alpha"
    assert out["career"]["played"] == 4 and [u["match_id"] for u in out["upcoming_fixtures"]] == ["m8", "m7", "m9"]
    assert [v["vod_id"] for v in out["vods"]] == [2, 1]
    assert (out["follower_count"], out["following"]) == (7, True)


def test_follow_rules():
    ath.check_follow("user-1", "player-alpha-2", "player-alpha-1")
    ath.check_follow("user-1", "player-alpha-2", None)
    with pytest.raises(ApiError) as e:
        ath.check_follow("user-1", "player-alpha-1", "player-alpha-1")
    assert (e.value.status, e.value.code, e.value.details["fields"]) == (400, "VALIDATION_ERROR", ["athlete_id"])
    with pytest.raises(ApiError):
        ath.check_follow(None, "player-alpha-1")


def test_follow_view():
    assert ath.follow_view("p1", "u1", False, 0) == {"athlete_id": "p1", "follower_id": "u1", "following": False,
                                                     "follower_count": 0}
