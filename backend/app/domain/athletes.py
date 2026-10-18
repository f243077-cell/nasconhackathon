"""Athlete profile and follow rules (FR-3.1, ADR-11). Pure functions.

- Career records come from the Phase I event logs: every match one of the athlete's clubs played, scored from
  the event projection (never stored counters), so a correction event changes the record on the next read.
- Follower count is derived (COUNT(*) over a follows table with a UNIQUE pair); follow and unfollow are
  idempotent, so concurrent toggles can't drift the count.
"""
from ..errors import validation_error

UPCOMING_STATES = ("upcoming", "postponed")
RECENT_LIMIT = 20


def check_follow(follower_id: str | None, athlete_id: str, athlete_player_id: str | None = None) -> None:
    """A member can follow any athlete but themselves."""
    if not follower_id:
        raise validation_error(["follower_id"], "Sign in to follow athletes")
    if athlete_player_id and athlete_player_id == athlete_id:
        raise validation_error(["athlete_id"], "You can't follow yourself")


def follow_view(athlete_id: str, follower_id: str, following: bool, follower_count: int) -> dict:
    return {"athlete_id": athlete_id, "follower_id": follower_id, "following": following,
            "follower_count": follower_count}


def _result_for(club_ids: set[str], m: dict) -> str | None:
    """W / D / L from the athlete's side, or None when the match doesn't count yet."""
    if m.get("status") != "completed" or m.get("outcome") in (None, "pending", "undecided"):
        return None
    if m["outcome"] == "draw":
        return "D"
    return "W" if m.get("winner_team_id") in club_ids else "L"


def career(club_ids: set[str], matches: list[dict]) -> dict:
    """Record over completed matches. `matches` = score projections with home/away team ids plus
    scheduled_at, venue and league_id; only matches involving one of `club_ids` are counted."""
    played = won = drawn = lost = 0
    recent = []
    for m in matches:
        home, away = m["home"]["team_id"], m["away"]["team_id"]
        if home not in club_ids and away not in club_ids:
            continue
        res = _result_for(club_ids, m)
        if res is None:
            continue
        played += 1
        won += res == "W"
        drawn += res == "D"
        lost += res == "L"
        mine, theirs = (m["home"], m["away"]) if home in club_ids else (m["away"], m["home"])
        recent.append({"match_id": m["match_id"], "league_id": m.get("league_id"), "club_id": mine["team_id"],
                       "opponent_id": theirs["team_id"], "result": res, "score": f"{mine['score']}-{theirs['score']}",
                       "scheduled_at": m.get("scheduled_at"), "vod_route": f"/web/matches/{m['match_id']}/vod"})
    recent.sort(key=lambda r: r["scheduled_at"] or "", reverse=True)
    return {"played": played, "won": won, "drawn": drawn, "lost": lost,
            "win_rate": round(won / played, 3) if played else 0.0, "recent_matches": recent[:RECENT_LIMIT]}


def upcoming(club_ids: set[str], matches: list[dict]) -> list[dict]:
    """Not-yet-played fixtures of the athlete's clubs, soonest first (unscheduled last)."""
    out = []
    for m in matches:
        home, away = m["home"]["team_id"], m["away"]["team_id"]
        if m.get("status") not in UPCOMING_STATES or (home not in club_ids and away not in club_ids):
            continue
        mine = home if home in club_ids else away
        out.append({"match_id": m["match_id"], "league_id": m.get("league_id"), "club_id": mine,
                    "opponent_id": away if mine == home else home, "home": mine == home, "status": m["status"],
                    "scheduled_at": m.get("scheduled_at"), "venue": m.get("venue")})
    out.sort(key=lambda r: (r["scheduled_at"] is None, r["scheduled_at"] or ""))
    return out


def affiliations(player: dict, placements: list[dict]) -> list[dict]:
    """Active club affiliations: the current squad in each roster league (a loan shows both clubs), else the
    player's registered club. `placements` = [{league_id, squad_id, club_id, parent_squad_id, parent_club_id}]."""
    out = []
    for p in placements:
        if not p.get("squad_id"):
            continue  # released in that league
        out.append({"club_id": p["club_id"], "league_id": p["league_id"], "squad_id": p["squad_id"],
                    "status": "on_loan" if p.get("parent_squad_id") else "registered",
                    "on_loan_from": p.get("parent_club_id")})
    if not out and not placements and player.get("club_id"):
        out.append({"club_id": player["club_id"], "league_id": None, "squad_id": player["club_id"],
                    "status": "registered", "on_loan_from": None})
    return out


def club_ids(affs: list[dict]) -> set[str]:
    return {a["club_id"] for a in affs if a.get("club_id")}


def profile(player: dict, affs: list[dict], matches: list[dict], vods: list[dict], follower_count: int,
            following: bool | None) -> dict:
    """GET /api/v1/athletes/{player_id} body."""
    clubs = club_ids(affs)
    return {
        "athlete_id": player["player_id"],
        "name": player["name"],
        "position": player.get("position"),
        "role": player.get("role"),
        "tenant_id": player.get("tenant_id"),
        "affiliations": affs,
        "career": career(clubs, matches),
        "upcoming_fixtures": upcoming(clubs, matches),
        "vods": sorted(vods, key=lambda v: v.get("ended_at") or "", reverse=True),
        "follower_count": follower_count,
        "following": following,
    }
