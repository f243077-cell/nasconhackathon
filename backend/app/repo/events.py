"""Append-only match event store (FR-1.1, spec 5.8 / 5.9)."""
import json

from ..canonical import canonical, sign
from ..domain import scoring
from ..errors import ApiError
from ..services import bus
from ..validate import now_iso


def get_sport(conn, sport_id: str) -> dict | None:
    row = conn.execute("SELECT config FROM sports WHERE sport_id = %s", (sport_id,)).fetchone()
    return json.loads(row["config"]) if row else None


def get_match(conn, match_id: str, lock: bool = False) -> dict | None:
    sql = "SELECT match_id, league_id, sport_id, home, away, scheduled_at, venue, pinned_product_id FROM matches WHERE match_id = %s"
    if lock:
        sql += " FOR UPDATE"
    return conn.execute(sql, (match_id,)).fetchone()


def load_events(conn, match_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT match_id, sequence, event_id, type, payload, signature FROM events WHERE match_id = %s ORDER BY sequence",
        (match_id,),
    ).fetchall()
    for r in rows:
        r["payload"] = json.loads(r["payload"])
    return rows


def match_version(conn, match_id: str) -> int:
    return conn.execute("SELECT count(*) AS n FROM events WHERE match_id = %s", (match_id,)).fetchone()["n"]


def _event_response(row: dict) -> dict:
    return {
        "event_id": row["event_id"],
        "match_id": row["match_id"],
        "type": row["type"],
        "sequence": row["sequence"],
        "match_version": row["sequence"],
        "signature": row["signature"],
    }


def find_event(conn, event_id: str) -> dict | None:
    row = conn.execute(
        "SELECT match_id, sequence, event_id, type, payload, request, signature FROM events WHERE event_id = %s",
        (event_id,),
    ).fetchone()
    if row:
        row["payload"] = json.loads(row["payload"])
    return row


def append_event(conn, body, allow_internal: bool = False) -> tuple[int, dict]:
    """POST /audit/v1/events. Returns (http_status, response). Raises ApiError."""
    scoring.validate_event_request(body, allow_internal)
    req_canon = canonical(body)

    existing = find_event(conn, body["event_id"])
    if existing:
        if existing["request"] == req_canon:
            return 200, _event_response(existing)
        raise ApiError(409, "DUPLICATE_EVENT_ID", "event_id already used with a different body",
                       {"event_id": body["event_id"]})

    etype, payload, match_id = body["type"], body["payload"], body["match_id"]

    if etype == "match_init":
        sport = get_sport(conn, payload["sport_id"])
        if sport is None:
            raise ApiError(404, "SPORT_NOT_FOUND", "Sport not found", {"sport_id": payload["sport_id"]})
        inserted = conn.execute(
            "INSERT INTO matches (match_id, league_id, sport_id, home, away) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (match_id) DO NOTHING RETURNING match_id",
            (match_id, payload.get("league_id"), payload["sport_id"], payload["home_team_id"], payload["away_team_id"]),
        ).fetchone()
        if not inserted:
            raise ApiError(409, "MATCH_EXISTS", "Match stream already exists", {"match_id": match_id})
        match = get_match(conn, match_id, lock=True)
        events: list[dict] = []
    else:
        match = get_match(conn, match_id, lock=True)
        if match is None:
            raise ApiError(404, "MATCH_NOT_FOUND", "Match not found", {"match_id": match_id})
        sport = get_sport(conn, match["sport_id"])
        events = load_events(conn, match_id)
        target = None
        if etype == "compensation":
            target = find_event(conn, payload["compensates"])
        scoring.check_append(match, sport, events, etype, payload, target)

    sequence = len(events) + 1
    signature = sign(body["event_id"], payload)
    conn.execute(
        "INSERT INTO events (match_id, sequence, event_id, type, payload, request, signature, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (match_id, sequence, body["event_id"], etype, canonical(payload), req_canon, signature, now_iso()),
    )
    resp = {
        "event_id": body["event_id"], "match_id": match_id, "type": etype,
        "sequence": sequence, "match_version": sequence, "signature": signature,
    }
    msg_type = "match_status" if etype in ("match_start", "match_end", scoring.STATUS_CHANGE) else "match_update"
    bus.publish_realtime(msg_type, match_id, {"event_id": body["event_id"], "type": etype, "version": sequence})
    return 201, resp


def score(conn, match_id: str) -> dict:
    match = get_match(conn, match_id)
    if match is None:
        raise ApiError(404, "MATCH_NOT_FOUND", "Match not found", {"match_id": match_id})
    sport = get_sport(conn, match["sport_id"])
    return scoring.project(match, sport, load_events(conn, match_id))
