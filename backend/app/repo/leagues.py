"""Sports (5.6) and league registration (5.8)."""
import json

from ..canonical import canonical
from ..domain import scoring
from ..errors import ApiError, validation_error
from ..validate import is_id, is_int
from .events import get_sport


def create_sport(conn, body) -> dict:
    config = scoring.validate_sport(body)
    row = conn.execute(
        "INSERT INTO sports (sport_id, config) VALUES (%s, %s) ON CONFLICT (sport_id) DO NOTHING RETURNING sport_id",
        (config["sport_id"], canonical(config)),
    ).fetchone()
    if not row:
        raise ApiError(409, "SPORT_EXISTS", "Sport already exists", {"sport_id": config["sport_id"]})
    return {"sport_id": config["sport_id"], "status": "created", "config": config}


def validate_league(body) -> None:
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    if not is_id(body.get("league_id")):
        bad.append("league_id")
    if not is_id(body.get("sport_id")):
        bad.append("sport_id")
    teams = body.get("teams")
    if (not isinstance(teams, list) or not 2 <= len(teams) <= 40 or not all(is_id(t) for t in teams)
            or len(set(teams)) != len(teams)):
        bad.append("teams")
        teams = None
    fixtures = body.get("fixtures")
    if not isinstance(fixtures, list):
        bad.append("fixtures")
    else:
        seen = set()
        for f in fixtures:
            if (not isinstance(f, dict) or not is_id(f.get("match_id")) or not is_id(f.get("home"))
                    or not is_id(f.get("away")) or f.get("home") == f.get("away")
                    or (teams is not None and (f["home"] not in teams or f["away"] not in teams))
                    or f.get("match_id") in seen):
                bad.append("fixtures")
                break
            seen.add(f["match_id"])
    points = body.get("points")
    if points is not None:
        if not isinstance(points, dict) or any(
            k in points and not is_int(points[k]) for k in ("win", "draw", "loss")
        ):
            bad.append("points")
    tbo = body.get("tie_break_order")
    if tbo is not None and (
        not isinstance(tbo, list) or any(t not in scoring.TIE_TOKENS for t in tbo) or len(set(tbo)) != len(tbo)
    ):
        bad.append("tie_break_order")
    qual = body.get("qualification")
    n = len(teams) if teams else 40
    if not isinstance(qual, dict) or not is_int(qual.get("spots")) or not 1 <= qual["spots"] <= n:
        bad.append("qualification")
    if "lots_seed" in body and body["lots_seed"] is not None and not is_int(body["lots_seed"]):
        bad.append("lots_seed")
    if bad:
        raise validation_error(bad, "Invalid league")


def register_league(conn, body, *, tenant_id=None, name=None, season=None, fixture_meta=None) -> dict:
    validate_league(body)
    sport = get_sport(conn, body["sport_id"])
    if sport is None:
        raise ApiError(404, "SPORT_NOT_FOUND", "Sport not found", {"sport_id": body["sport_id"]})
    if conn.execute("SELECT 1 FROM leagues WHERE league_id = %s", (body["league_id"],)).fetchone():
        raise ApiError(409, "LEAGUE_EXISTS", "League already exists", {"league_id": body["league_id"]})
    ids = [f["match_id"] for f in body["fixtures"]]
    if ids:
        clash = conn.execute("SELECT match_id FROM matches WHERE match_id = ANY(%s) LIMIT 1", (ids,)).fetchone()
        if clash:
            raise ApiError(409, "MATCH_EXISTS", "Match id already used", {"match_id": clash["match_id"]})

    points = {"win": 3, "draw": 1, "loss": 0}
    points.update({k: v for k, v in (body.get("points") or {}).items() if k in points})
    lots_seed = body.get("lots_seed")
    if lots_seed is None:
        row = conn.execute("SELECT value FROM meta WHERE key = 'last_seed'").fetchone()
        lots_seed = int(row["value"]) if row else 42
    cfg = {
        "league_id": body["league_id"],
        "sport_id": body["sport_id"],
        "teams": body["teams"],
        "fixtures": [{"match_id": f["match_id"], "home": f["home"], "away": f["away"]} for f in body["fixtures"]],
        "points": points,
        "tie_break_order": body.get("tie_break_order") or sport["tie_break_order"],
        "qualification_spots": body["qualification"]["spots"],
        "lots_seed": lots_seed,
    }
    conn.execute(
        "INSERT INTO leagues (league_id, tenant_id, name, season, sport_id, config) VALUES (%s, %s, %s, %s, %s, %s)",
        (body["league_id"], tenant_id, name or body["league_id"], season, body["sport_id"], json.dumps(cfg)),
    )
    meta = fixture_meta or {}
    for f in body["fixtures"]:
        m = meta.get(f["match_id"], {})
        conn.execute(
            "INSERT INTO matches (match_id, league_id, sport_id, home, away, scheduled_at, venue) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (f["match_id"], body["league_id"], body["sport_id"], f["home"], f["away"],
             m.get("scheduled_at"), m.get("venue")),
        )
    return {"league_id": body["league_id"], "status": "created", "team_count": len(body["teams"]),
            "fixture_count": len(body["fixtures"])}


def get_league(conn, league_id: str) -> dict | None:
    row = conn.execute(
        "SELECT league_id, tenant_id, name, season, sport_id, config FROM leagues WHERE league_id = %s", (league_id,)
    ).fetchone()
    if row:
        row["config"] = json.loads(row["config"])
    return row
