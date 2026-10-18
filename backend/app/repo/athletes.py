"""Athlete profile, follows and the VOD index (FR-3.1, FR-3.2). Rules in domain/athletes.py."""
import json
from datetime import date

from .. import config
from ..domain import athletes as athletes_domain
from ..domain import roster as roster_domain
from ..errors import ApiError
from ..validate import now_iso, today_iso
from . import events as events_repo
from . import roster as roster_repo


def get_player(conn, player_id: str) -> dict:
    row = conn.execute("SELECT player_id, club_id, tenant_id, name, position, role FROM players WHERE player_id = %s",
                       (player_id,)).fetchone()
    if row is None:
        raise ApiError(404, "PLAYER_NOT_FOUND", "Player not found", {"player_id": player_id})
    return row


def _placements(conn, player_id: str) -> list[dict]:
    today = date.fromisoformat(today_iso())
    out = []
    for r in conn.execute("SELECT league_id FROM roster_index WHERE player_id = %s", (player_id,)).fetchall():
        state = roster_repo.load_state(conn, r["league_id"])
        if not state or player_id not in state["players"]:
            continue
        squad_id, parent = roster_domain.placement(state, player_id, today)
        squads = state["squads"]
        out.append({"league_id": r["league_id"], "squad_id": squad_id,
                    "club_id": squads.get(squad_id or "", {}).get("club_id"),
                    "parent_squad_id": parent, "parent_club_id": squads.get(parent or "", {}).get("club_id")})
    return out


def _matches(conn, clubs: set[str]) -> list[dict]:
    if not clubs:
        return []
    rows = conn.execute("SELECT match_id, league_id, scheduled_at, venue FROM matches WHERE home = ANY(%s) "
                        "OR away = ANY(%s) ORDER BY scheduled_at NULLS LAST", (list(clubs), list(clubs))).fetchall()
    out = []
    for r in rows:
        proj = events_repo.score(conn, r["match_id"])
        out.append(dict(proj, league_id=proj.get("league_id") or r["league_id"], scheduled_at=r["scheduled_at"],
                        venue=r["venue"]))
    return out


def _vods(conn, player_id: str) -> list[dict]:
    rows = conn.execute("SELECT vod_id, stream_key, recording_path, started_at, ended_at FROM vods "
                        "WHERE player_id = %s ORDER BY ended_at DESC", (player_id,)).fetchall()
    return [dict(r) for r in rows]


def follower_count(conn, athlete_id: str) -> int:
    return conn.execute("SELECT count(*) AS n FROM follows WHERE athlete_id = %s", (athlete_id,)).fetchone()["n"]


def is_following(conn, follower_id: str | None, athlete_id: str) -> bool | None:
    if not follower_id:
        return None
    return conn.execute("SELECT 1 FROM follows WHERE follower_id = %s AND athlete_id = %s",
                        (follower_id, athlete_id)).fetchone() is not None


def profile(conn, player: dict, viewer_id: str | None) -> dict:
    affs = athletes_domain.affiliations(player, _placements(conn, player["player_id"]))
    matches = _matches(conn, athletes_domain.club_ids(affs))
    return athletes_domain.profile(player, affs, matches, _vods(conn, player["player_id"]),
                                   follower_count(conn, player["player_id"]),
                                   is_following(conn, viewer_id, player["player_id"]))


def set_follow(conn, follower_id: str, follower_player_id: str | None, athlete_id: str, follow: bool) -> dict:
    """Idempotent toggle: INSERT .. ON CONFLICT DO NOTHING / DELETE. The count is read after the write, in the
    same transaction, from the table itself, so simultaneous toggles never drift it."""
    athletes_domain.check_follow(follower_id, athlete_id, follower_player_id)
    if follow:
        conn.execute("INSERT INTO follows (follower_id, athlete_id, created_at) VALUES (%s, %s, %s) "
                     "ON CONFLICT (follower_id, athlete_id) DO NOTHING", (follower_id, athlete_id, now_iso()))
    else:
        conn.execute("DELETE FROM follows WHERE follower_id = %s AND athlete_id = %s", (follower_id, athlete_id))
    return athletes_domain.follow_view(athlete_id, follower_id, follow, follower_count(conn, athlete_id))


def index_recording(conn, path: str, recording_path: str, started_at: str | None, ended_at: str | None) -> dict | None:
    """FR-3.2 VOD indexing, called by the media server when a recording segment closes. `path` is the
    MediaMTX path (live/<stream_key>); unknown keys are ignored."""
    if not path.startswith("live/"):
        return None
    key = path[len("live/"):]
    row = conn.execute("SELECT player_id FROM stream_keys WHERE stream_key = %s", (key,)).fetchone()
    if row is None:
        return None
    vod = {"stream_key": key, "player_id": row["player_id"], "recording_path": recording_path,
           "started_at": started_at, "ended_at": ended_at or now_iso()}
    got = conn.execute("INSERT INTO vods (stream_key, player_id, recording_path, started_at, ended_at) "
                       "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (recording_path) DO NOTHING RETURNING vod_id",
                       (vod["stream_key"], vod["player_id"], recording_path, started_at, vod["ended_at"])).fetchone()
    vod["vod_id"] = got["vod_id"] if got else None
    vod["playback_base"] = f"http://{config.MEDIA_PUBLIC_HOST}:8888"
    return json.loads(json.dumps(vod))
