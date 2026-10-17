"""POST /audit/v1/offline-sync and /api/v1/sync (NFR-4, spec 5.14). One shared code path."""
import json

from ..canonical import canonical
from ..errors import ApiError, validation_error
from ..validate import is_id, is_int, is_ts
from . import events as events_repo
from . import roster as roster_repo

TYPES = ("score_event", "roster_transfer")


def validate_envelope(body) -> None:
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    if not is_id(body.get("device_id")):
        bad.append("device_id")
    actions = body.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 100:
        bad.append("actions")
    else:
        for a in actions:
            if (not isinstance(a, dict) or not is_id(a.get("action_id")) or a.get("type") not in TYPES
                    or not is_ts(a.get("queued_at")) or not is_int(a.get("base_version")) or a["base_version"] < 0
                    or not isinstance(a.get("payload"), dict)):
                bad.append("actions")
                break
    if bad:
        raise validation_error(bad, "Invalid offline-sync envelope")


def _result(action, status, resolution, code, order, version, signature=None) -> dict:
    return {"action_id": action["action_id"], "status": status, "resolution": resolution, "error_code": code,
            "processed_order": order, "server_version": version, "signature": signature}


def _process_score(conn, action, order) -> dict:
    payload = action["payload"]
    match_id = payload.get("match_id") if isinstance(payload, dict) else None
    current = events_repo.match_version(conn, match_id) if is_id(match_id) else 0
    if is_id(payload.get("event_id")):
        existing = events_repo.find_event(conn, payload["event_id"])
        if existing and existing["request"] == canonical(payload):
            return _result(action, "duplicate", "skipped_duplicate", None, order, current)
    if is_id(match_id) and payload.get("type") != "match_init" and events_repo.get_match(conn, match_id) is None:
        return _result(action, "rejected", "server_wins", "MATCH_NOT_FOUND", order, 0)
    if action["base_version"] > current:
        return _result(action, "rejected", "server_wins", "INVALID_BASE_VERSION", order, current)
    try:
        with conn.transaction():
            _, resp = events_repo.append_event(conn, payload)
    except ApiError as exc:
        return _result(action, "rejected", "server_wins", exc.code, order, current)
    resolution = "appended" if action["base_version"] == current else "rebased_append"
    return _result(action, "applied", resolution, None, order, resp["match_version"], resp["signature"])


def _process_roster(conn, action, order) -> dict:
    payload = action["payload"]
    player_id = payload.get("player_id")
    current = roster_repo.player_audit_count(conn, player_id) if is_id(player_id) else None
    if is_id(payload.get("request_id")):
        prev = conn.execute("SELECT request FROM roster_requests WHERE request_id = %s",
                            (payload["request_id"],)).fetchone()
        if prev and prev["request"] == canonical(payload):
            return _result(action, "duplicate", "skipped_duplicate", None, order, current or 0)
    if current is not None and action["base_version"] > current:
        return _result(action, "rejected", "server_wins", "INVALID_BASE_VERSION", order, current)
    try:
        with conn.transaction():
            roster_repo.transfer(conn, payload)
    except ApiError as exc:
        return _result(action, "rejected", "server_wins", exc.code, order, current or 0)
    after = roster_repo.player_audit_count(conn, player_id) or 0
    resolution = "appended" if action["base_version"] == (current or 0) else "rebased_append"
    return _result(action, "applied", resolution, None, order, after)


def offline_sync(conn, body) -> dict:
    validate_envelope(body)
    device_id = body["device_id"]
    actions = body["actions"]
    order_idx = sorted(range(len(actions)), key=lambda i: (actions[i]["queued_at"], i))
    results: dict[int, dict] = {}
    for n, i in enumerate(order_idx, start=1):
        action = actions[i]
        prev = conn.execute("SELECT result FROM sync_actions WHERE device_id = %s AND action_id = %s",
                            (device_id, action["action_id"])).fetchone()
        if prev:
            stored = json.loads(prev["result"])
            res = _result(action, "duplicate", "skipped_duplicate", None, n, stored.get("server_version", 0))
        elif action["type"] == "score_event":
            res = _process_score(conn, action, n)
        else:
            res = _process_roster(conn, action, n)
        if not prev:
            conn.execute("INSERT INTO sync_actions (device_id, action_id, result) VALUES (%s, %s, %s) "
                         "ON CONFLICT DO NOTHING", (device_id, action["action_id"], json.dumps(res)))
        results[i] = res
    ordered = [results[i] for i in range(len(actions))]
    summary = {"applied": 0, "rejected": 0, "duplicate": 0}
    for r in ordered:
        summary[r["status"]] += 1
    return {"device_id": device_id, "results": ordered, "summary": summary}
