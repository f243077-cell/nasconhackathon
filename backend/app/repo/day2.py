"""Part II persistence: stream keys (5.4), dynamic QR (5.6), privacy erasure (5.9) and metric inputs (NFR-6)."""
import json
from datetime import datetime, timezone

from .. import config
from ..canonical import sign_day2
from ..domain import moderation as moderation_domain
from ..domain import qr as qr_domain
from ..domain import streaming
from ..errors import ApiError
from ..services import bus, media
from ..validate import now_iso
from . import events as events_repo


# ------------------------------------------------------------------ stream keys
def _player_exists(conn, player_id: str) -> bool:
    return conn.execute("SELECT 1 FROM players WHERE player_id = %s", (player_id,)).fetchone() is not None


def _active_key(conn, player_id: str) -> dict | None:
    return conn.execute("SELECT stream_key, label FROM stream_keys WHERE player_id = %s AND status = 'active' "
                        "ORDER BY seq DESC LIMIT 1", (player_id,)).fetchone()


def stream_key(conn, body) -> tuple[int, dict]:
    streaming.validate_request(body)
    action, player_id = body["action"], body["player_id"]
    if not _player_exists(conn, player_id):
        raise ApiError(404, "PLAYER_NOT_FOUND", "Player not found", {"player_id": player_id})
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("stream:" + player_id,))
    current = _active_key(conn, player_id)
    kicked = []
    if action == "revoke":
        if current is None:
            raise ApiError(404, "STREAM_NOT_FOUND", "No stream key for this player", {"player_id": player_id})
        conn.execute("UPDATE stream_keys SET status = 'revoked' WHERE stream_key = %s", (current["stream_key"],))
        key, label, status, http = current["stream_key"], current["label"], "revoked", 200
        kicked.append(key)
    else:
        label = body.get("label") or "default"
        if current is not None:
            conn.execute("UPDATE stream_keys SET status = 'revoked' WHERE stream_key = %s", (current["stream_key"],))
            kicked.append(current["stream_key"])
        key = streaming.new_key(body.get("stream_key_override"))
        conn.execute(
            "INSERT INTO stream_keys (stream_key, player_id, label, status, created_at) VALUES (%s,%s,%s,'active',%s) "
            "ON CONFLICT (stream_key) DO UPDATE SET player_id = EXCLUDED.player_id, label = EXCLUDED.label, "
            "status = 'active', created_at = EXCLUDED.created_at, seq = nextval('stream_keys_seq_seq')",
            (key, player_id, label, now_iso()))
        status, http = "active", (201 if action == "generate" else 200)
    resp = streaming.response(player_id, label, key, status, config.MEDIA_PUBLIC_HOST)
    resp["signature"] = sign_day2(key, streaming.sig_payload(action, player_id, status, key))
    to_kick = kicked if action == "revoke" else [k for k in kicked if k != key]
    return http, dict(resp, _kick=to_kick)


def key_status(conn, key: str) -> str | None:
    row = conn.execute("SELECT status FROM stream_keys WHERE stream_key = %s", (key,)).fetchone()
    return row["status"] if row else None


def publish_check(conn, key: str) -> dict:
    status = key_status(conn, key)
    if status is None:
        raise ApiError(404, "STREAM_NOT_FOUND", "Unknown stream key", {"stream_key": key})
    if status != "active":
        raise ApiError(409, "KEY_REVOKED", "This stream key has been revoked", {"stream_key": key})
    return {"stream_key": key, "status": "active", "publish_allowed": True}


# ------------------------------------------------------------------ dynamic QR
def _entity(conn, entity_id: str) -> tuple[str, str | None] | None:
    """(entity_type, live status) or None when the entity does not exist."""
    kind = qr_domain.entity_type(entity_id)
    if kind == "match" and events_repo.get_match(conn, entity_id):
        return "match", events_repo.score(conn, entity_id)["status"]
    if kind == "player" and _player_exists(conn, entity_id):
        return "player", "active"
    if kind == "club" and conn.execute("SELECT 1 FROM clubs WHERE club_id = %s", (entity_id,)).fetchone():
        return "club", "active"
    if kind == "costream":
        row = conn.execute("SELECT response FROM costream_sessions WHERE session_id = %s", (entity_id,)).fetchone()
        if row:
            return "costream", json.loads(row["response"]).get("status", "active")
    return None


def short_url(code: str) -> str:
    return qr_domain.short_url(config.PUBLIC_BASE_URL, code)


def _mapping(conn, entity_id: str, create: bool) -> dict | None:
    row = conn.execute("SELECT entity_id, short_code, scan_count FROM qr_codes WHERE entity_id = %s",
                       (entity_id,)).fetchone()
    if row or not create:
        return row
    code = qr_domain.short_code_for(entity_id, config.DAY2_SALT)
    conn.execute("INSERT INTO qr_codes (entity_id, short_code, scan_count) VALUES (%s,%s,0) ON CONFLICT DO NOTHING",
                 (entity_id, code))
    return conn.execute("SELECT entity_id, short_code, scan_count FROM qr_codes WHERE entity_id = %s",
                        (entity_id,)).fetchone()


def _record_scan(conn, entity_id: str, user_agent: str | None) -> int:
    count = conn.execute("UPDATE qr_codes SET scan_count = scan_count + 1 WHERE entity_id = %s RETURNING scan_count",
                         (entity_id,)).fetchone()["scan_count"]
    conn.execute("INSERT INTO qr_scans (entity_id, device_family, hour_bucket, scans) VALUES (%s,%s,%s,1) "
                 "ON CONFLICT (entity_id, device_family, hour_bucket) DO UPDATE SET scans = qr_scans.scans + 1",
                 (entity_id, qr_domain.device_family(user_agent), qr_domain.hour_bucket(datetime.now(timezone.utc))))
    return count


def qr_resolve(conn, entity_id: str, inspect: bool, user_agent: str | None) -> dict:
    ent = _entity(conn, entity_id)
    if ent is None:
        raise ApiError(404, "QR_NOT_FOUND", "No QR code for this entity", {"entity_id": entity_id})
    kind, status = ent
    mapping = _mapping(conn, entity_id, create=True)
    count = mapping["scan_count"] if inspect else _record_scan(conn, entity_id, user_agent)
    view = qr_domain.build_view(entity_id, status, mapping["short_code"], count, base=config.PUBLIC_BASE_URL)
    view["signature"] = sign_day2(entity_id, qr_domain.sig_payload(view))
    return view


def qr_redirect(conn, code: str, user_agent: str | None) -> str:
    row = conn.execute("SELECT entity_id FROM qr_codes WHERE short_code = %s", (code,)).fetchone()
    if not row:
        raise ApiError(404, "QR_NOT_FOUND", "Unknown short link", {"short_code": code})
    ent = _entity(conn, row["entity_id"])
    if ent is None:
        raise ApiError(404, "QR_NOT_FOUND", "Entity no longer exists", {"short_code": code})
    _record_scan(conn, row["entity_id"], user_agent)
    return qr_domain.target_route(row["entity_id"], ent[1])


def qr_export_info(conn, entity_id: str) -> tuple[str, str]:
    """(short_url, title) without counting a scan."""
    ent = _entity(conn, entity_id)
    if ent is None:
        raise ApiError(404, "QR_NOT_FOUND", "No QR code for this entity", {"entity_id": entity_id})
    mapping = _mapping(conn, entity_id, create=True)
    return short_url(mapping["short_code"]), f"NaSCon {ent[0].title()}: {entity_id}"


# ------------------------------------------------------------------ member chat (FR-3.3, FR-5.3)
def dlq_status(conn, limit: int = 100) -> dict:
    depth = conn.execute("SELECT count(*) AS n FROM dlq").fetchone()["n"]
    rows = conn.execute("SELECT id, event, attempts, created_at FROM dlq ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
    events = [dict(json.loads(r["event"]), dlq_id=r["id"], attempts=r["attempts"], failed_at=r["created_at"])
              for r in reversed(rows)]
    return {"queue_depth": depth, "undelivered_events": events}


def dead_letter(conn, event: dict, attempts: int) -> None:
    conn.execute("INSERT INTO dlq (event, attempts, created_at) VALUES (%s, %s, %s)",
                 (json.dumps(event), attempts, now_iso()))


def store_chat(conn, room: str, messages: list[dict]) -> None:
    """Persist broadcast messages with one monotonically increasing sequence per room (FR-3.3) and publish them."""
    for m in messages:
        try:
            seq = int(bus.client().incr(f"chat:seq:{room}"))
        except Exception:  # noqa: BLE001  fall back to the table when Redis is unavailable
            seq = conn.execute("SELECT COALESCE(max(seq), 0) + 1 AS n FROM chat_messages WHERE chat_room_id = %s",
                               (room,)).fetchone()["n"]
        conn.execute("INSERT INTO chat_messages (chat_room_id, seq, message_id, sender, text, flagged, reason, created_at) "
                     "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                     (room, seq, m["message_id"], m["sender"], m["text"], m["flagged"], m["reason"], now_iso()))
        entity = room[len("chat-"):] if room.startswith("chat-") else None
        bus.publish_realtime("chat_message", entity, dict(m, chat_room_id=room, seq=seq))


def post_chat(conn, principal: dict, body) -> dict:
    """Member chat post (/api/v1/chat): the same moderation rules, then broadcast."""
    if isinstance(body, dict) and "chat_room_id" not in body and isinstance(body.get("room_id"), str):
        body = dict(body, chat_room_id=body["room_id"])
    if not isinstance(body, dict) or not isinstance(body.get("chat_room_id"), str) or not isinstance(body.get("text"), str):
        from ..errors import validation_error
        raise validation_error(["chat_room_id", "text"], "chat_room_id and text are required")
    msg = {"message_id": body.get("message_id") or f"m-{now_iso()}-{principal['sub']}", "sender": principal["sub"],
           "text": body["text"]}
    from . import social  # late import: social imports services that import this module's peers
    social.chat_rate_check(body["chat_room_id"], principal["sub"])  # > 3 msgs / 2 s -> 429 RATE_LIMITED
    moderation_domain.validate_request({"chat_room_id": body["chat_room_id"], "incoming_messages": [msg]})
    result = moderation_domain.moderate([msg])
    store_chat(conn, body["chat_room_id"], result["filtered_messages"])
    if not result["filtered_messages"]:
        return {"chat_room_id": body["chat_room_id"], "delivered": False,
                "reason": result["blocked"][0]["reason"] if result["blocked"] else None}
    return {"chat_room_id": body["chat_room_id"], "delivered": True, "message": result["filtered_messages"][0]}


def issue_guest_token(conn) -> dict:
    """Short-lived anonymous viewer token (FR-4.2): read-only playback, live score, guest cart staging."""
    import secrets
    from ..domain import guest_cart as guest_cart_domain
    token = "guest_anon_tok_" + secrets.token_hex(8)
    created = now_iso()
    conn.execute("INSERT INTO guest_tokens (guest_token, status, created_at) VALUES (%s, 'active', %s)",
                 (token, created))
    return {"guest_token": token, "role": "guest", "read_only": True, "expires_in": config.GUEST_TOKEN_TTL_S,
            "expires_at": guest_cart_domain.token_expires_at(created, config.GUEST_TOKEN_TTL_S)}


def chat_history(conn, room: str, limit: int = 100) -> dict:
    rows = conn.execute("SELECT seq, message_id, sender, text, flagged, reason, created_at FROM chat_messages "
                        "WHERE chat_room_id = %s ORDER BY seq DESC LIMIT %s", (room, limit)).fetchall()
    return {"chat_room_id": room, "messages": list(reversed(rows))}


# ------------------------------------------------------------------ privacy (NFR-9)
def erase_user(conn, user_id: str) -> dict:
    users = conn.execute("SELECT user_id FROM users WHERE user_id = %s OR player_id = %s", (user_id, user_id)).fetchall()
    player = _player_exists(conn, user_id)
    if not users and not player:
        raise ApiError(404, "PLAYER_NOT_FOUND", "User not found", {"user_id": user_id})
    for u in users:
        conn.execute("UPDATE users SET email = %s, display_name = 'Erased user', password_hash = '' WHERE user_id = %s",
                     (f"erased-{u['user_id']}@invalid", u["user_id"]))
    if player:
        conn.execute("UPDATE players SET name = 'Erased player' WHERE player_id = %s", (user_id,))
    ids = [user_id] + [u["user_id"] for u in users]
    conn.execute("UPDATE guest_tokens SET status = 'wiped', user_id = NULL, merge_request = NULL "
                 "WHERE user_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM carts WHERE user_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM follows WHERE follower_id = ANY(%s)", (ids,))
    return {"user_id": user_id, "status": "anonymized", "pii_retained": False, "tokens_wiped": True}


# ------------------------------------------------------------------ metrics inputs
def metric_counts(conn) -> dict:
    return {
        "dlq": conn.execute("SELECT count(*) AS n FROM dlq").fetchone()["n"],
        "qr": conn.execute("SELECT COALESCE(sum(scan_count), 0) AS n FROM qr_codes").fetchone()["n"],
    }


def kick_after_commit(resp: dict) -> dict:
    for key in resp.pop("_kick", []):
        media.kick_publisher(key)
    return resp
