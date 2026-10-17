"""Roster persistence (spec 5.11). Rule logic lives in domain/roster.py (Gunee).

State shape passed to / returned from domain.roster (one JSON blob per league, row-locked):
{
  "league": {"league_id", "tenant_id", "sport_id", "transfer_window": {"open", "close"},
             "max_squad_size": int, "required_positions": {pos: min}},
  "squads": {squad_id: {"squad_id", "club_id", "tenant_id", "name"}},
  "players": {player_id: {"player_id", "name", "position", "squad_id": str|None,
              "parent_squad_id": str|None, "role", "registration_type": "initial"|"transfer"|"loan"|"release",
              "start_date": str|None, "loan_end_date": str|None}},
  "matches_in_progress": [{"match_id", "home_squad_id", "away_squad_id"}],
  "audit": [audit_entry, ...]   # oldest first, append-only
  "next_audit_seq": int         # audit_id = f"au-{seq:04d}"
}
"""
import json

from ..canonical import canonical
from ..errors import ApiError, validation_error
from ..validate import is_date, is_id, is_int, is_str, now_iso, today_iso
from .events import get_sport

ROLES = ("captain", "vice_captain", "starter", "substitute")

try:  # Gunee's pure module; routes answer 501 until it lands.
    from ..domain import roster as roster_domain
except ImportError:  # pragma: no cover
    roster_domain = None


def _require_domain():
    if roster_domain is None:
        raise ApiError(501, "NOT_IMPLEMENTED", "Roster rules module not available yet")


def build_state(conn, body) -> dict:
    """Validate a /roster/setup body and build the league state (400 / 404)."""
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    league = body.get("league")
    if not isinstance(league, dict):
        raise validation_error(["league"], "league is required")
    for k in ("league_id", "tenant_id", "sport_id"):
        if not is_id(league.get(k)):
            bad.append(f"league.{k}")
    tw = league.get("transfer_window")
    if not (isinstance(tw, dict) and is_date(tw.get("open")) and is_date(tw.get("close")) and tw["open"] <= tw["close"]):
        bad.append("league.transfer_window")
    if "max_squad_size" in league and league["max_squad_size"] is not None and not (
        is_int(league["max_squad_size"]) and league["max_squad_size"] >= 1
    ):
        bad.append("league.max_squad_size")
    rp = league.get("required_positions")
    if rp is not None and (not isinstance(rp, dict) or any(not is_int(v) or v < 0 for v in rp.values())):
        bad.append("league.required_positions")

    squads = body.get("squads")
    squad_map = {}
    if not isinstance(squads, list):
        bad.append("squads")
    else:
        for s in squads:
            if (not isinstance(s, dict) or not is_id(s.get("squad_id")) or not is_id(s.get("club_id"))
                    or not is_id(s.get("tenant_id")) or not isinstance(s.get("name", ""), str)
                    or s.get("squad_id") in squad_map):
                bad.append("squads")
                break
            squad_map[s["squad_id"]] = {"squad_id": s["squad_id"], "club_id": s["club_id"],
                                        "tenant_id": s["tenant_id"], "name": s.get("name", "")}
    players = body.get("players", [])
    player_map = {}
    if not isinstance(players, list):
        bad.append("players")
    else:
        for p in players:
            if (not isinstance(p, dict) or not is_id(p.get("player_id")) or not is_str(p.get("name"), 1, 200)
                    or not is_str(p.get("position"), 1, 64) or not is_id(p.get("squad_id"))
                    or p.get("role") not in ROLES or p.get("player_id") in player_map):
                bad.append("players")
                break
            player_map[p["player_id"]] = {
                "player_id": p["player_id"], "name": p["name"], "position": p["position"],
                "squad_id": p["squad_id"], "parent_squad_id": None, "role": p["role"],
                "registration_type": "initial", "start_date": None, "loan_end_date": None,
            }
    mip = body.get("matches_in_progress", [])
    if not isinstance(mip, list) or any(
        not isinstance(m, dict) or not is_id(m.get("match_id")) or not is_id(m.get("home_squad_id"))
        or not is_id(m.get("away_squad_id")) for m in mip
    ):
        bad.append("matches_in_progress")
    if bad:
        raise validation_error(bad, "Invalid roster setup")

    for p in player_map.values():
        if p["squad_id"] not in squad_map:
            raise ApiError(404, "SQUAD_NOT_FOUND", "Squad not found", {"squad_id": p["squad_id"]})
    sport = get_sport(conn, league["sport_id"])
    if sport is None:
        raise ApiError(404, "SPORT_NOT_FOUND", "Sport not found", {"sport_id": league["sport_id"]})

    return {
        "league": {
            "league_id": league["league_id"], "tenant_id": league["tenant_id"], "sport_id": league["sport_id"],
            "transfer_window": {"open": tw["open"], "close": tw["close"]},
            "max_squad_size": league.get("max_squad_size") or sport["roster"]["max_squad_size"],
            "required_positions": rp if rp is not None else sport["roster"]["required_positions"],
        },
        "squads": squad_map,
        "players": player_map,
        "matches_in_progress": [{"match_id": m["match_id"], "home_squad_id": m["home_squad_id"],
                                 "away_squad_id": m["away_squad_id"]} for m in mip],
        "audit": [],
        "next_audit_seq": 1,
    }


def save_state(conn, state: dict) -> None:
    league_id = state["league"]["league_id"]
    conn.execute(
        "INSERT INTO roster_state (league_id, state) VALUES (%s, %s) "
        "ON CONFLICT (league_id) DO UPDATE SET state = EXCLUDED.state",
        (league_id, json.dumps(state)),
    )


def load_state(conn, league_id: str, lock: bool = False) -> dict | None:
    sql = "SELECT state FROM roster_state WHERE league_id = %s" + (" FOR UPDATE" if lock else "")
    row = conn.execute(sql, (league_id,)).fetchone()
    return json.loads(row["state"]) if row else None


def setup(conn, body) -> dict:
    state = build_state(conn, body)
    league_id = state["league"]["league_id"]
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("roster:" + league_id,))
    conn.execute("DELETE FROM roster_index WHERE league_id = %s", (league_id,))
    save_state(conn, state)
    for pid in state["players"]:
        conn.execute(
            "INSERT INTO roster_index (player_id, league_id) VALUES (%s, %s) "
            "ON CONFLICT (player_id) DO UPDATE SET league_id = EXCLUDED.league_id",
            (pid, league_id),
        )
    counts = {sid: 0 for sid in state["squads"]}
    for p in state["players"].values():
        counts[p["squad_id"]] += 1
    return {"league_id": league_id, "status": "configured", "squad_counts": counts}


def seed_demo_roster(conn, roster_league: dict, players: list[dict]) -> None:
    squad_ids = {s["squad_id"] for s in roster_league["squads"]}
    body = dict(roster_league)
    body["players"] = [
        {"player_id": p["player_id"], "name": p["name"], "position": p["position"], "squad_id": p["club_id"],
         "role": p["role"]}
        for p in players if p["club_id"] in squad_ids
    ]
    setup(conn, body)


def transfer(conn, body) -> tuple[int, dict]:
    _require_domain()
    if isinstance(body, dict) and is_id(body.get("request_id")):
        prev = conn.execute("SELECT request, response FROM roster_requests WHERE request_id = %s",
                            (body["request_id"],)).fetchone()
        if prev and prev["request"] == canonical(body):
            return 200, json.loads(prev["response"])
    roster_domain.validate_request(body)
    if prev_conflict(conn, body):
        # Spec defines no code for this; a reused request_id is a bad field value (catalogue code only).
        raise validation_error(["request_id"], "request_id already used with a different body")
    state = load_state(conn, body["league_id"], lock=True)
    if state is None:
        raise ApiError(404, "LEAGUE_NOT_FOUND", "League not found", {"league_id": body["league_id"]})
    response, new_state = roster_domain.check_and_apply(state, body, now_iso())
    save_state(conn, new_state)
    conn.execute("INSERT INTO roster_requests (request_id, request, response) VALUES (%s, %s, %s)",
                 (body["request_id"], canonical(body), json.dumps(response)))
    return 201, response


def prev_conflict(conn, body) -> bool:
    row = conn.execute("SELECT request FROM roster_requests WHERE request_id = %s", (body["request_id"],)).fetchone()
    return bool(row) and row["request"] != canonical(body)


def history(conn, player_id: str, as_of: str | None) -> dict:
    _require_domain()
    if as_of is not None and not is_date(as_of):
        raise validation_error(["as_of"], "as_of must be YYYY-MM-DD")
    row = conn.execute("SELECT league_id FROM roster_index WHERE player_id = %s", (player_id,)).fetchone()
    if not row:
        raise ApiError(404, "PLAYER_NOT_FOUND", "Player not found", {"player_id": player_id})
    state = load_state(conn, row["league_id"], lock=True)
    response, new_state = roster_domain.history(state, player_id, as_of or today_iso(), now_iso())
    if new_state is not None and new_state != state:
        save_state(conn, new_state)
    return response


def player_audit_count(conn, player_id: str) -> int | None:
    row = conn.execute("SELECT league_id FROM roster_index WHERE player_id = %s", (player_id,)).fetchone()
    if not row:
        return None
    state = load_state(conn, row["league_id"])
    return sum(1 for e in state["audit"] if e.get("player_id") == player_id)
