"""Part II persistence for co-stream sessions (5.5), guest cart merge (5.7) and chat moderation + DLQ (5.8).
Rules live in domain/costream.py, domain/guest_cart.py and domain/moderation.py; this file only reads and writes."""
import json

from .. import config
from ..errors import ApiError
from ..services import bus, notifier
from ..canonical import canonical, sign_day2
from ..domain import costream as costream_domain
from ..domain import guest_cart as cart_domain
from ..domain import moderation as mod_domain
from ..domain import notify
from ..validate import now_iso

MEDIA_HLS_BASE = f"http://{config.MEDIA_PUBLIC_HOST}:8888"
DLQ_REPORT_LIMIT = 100


def _player_exists(conn, player_id: str) -> bool:
    return conn.execute("SELECT 1 FROM players WHERE player_id = %s", (player_id,)).fetchone() is not None


def _user_exists(conn, user_id: str) -> bool:
    if _player_exists(conn, user_id):
        return True
    return conn.execute("SELECT 1 FROM users WHERE user_id = %s OR player_id = %s", (user_id, user_id)).fetchone() is not None


# ------------------------------------------------------------------ co-stream (5.5)
def costream_session(conn, body) -> tuple[int, dict]:
    """201 on a new or changed session, 200 + the stored body on an identical replay."""
    resp = costream_domain.plan_session(body, lambda pid: _player_exists(conn, pid), media_base=MEDIA_HLS_BASE)
    req = costream_domain.validate_request(body)
    key = canonical(req)
    sid = req["session_id"]
    row = conn.execute("SELECT request, response FROM costream_sessions WHERE session_id = %s FOR UPDATE",
                       (sid,)).fetchone()
    if row and row["request"] == key:
        return 200, json.loads(row["response"])
    resp["signature"] = sign_day2(sid, costream_domain.sig_payload(resp))
    bus.invalidate_qr(sid)
    state = costream_domain.state_from_response(resp)
    conn.execute("INSERT INTO costream_sessions (session_id, request, response, state) VALUES (%s, %s, %s, %s) "
                 "ON CONFLICT (session_id) DO UPDATE SET request = EXCLUDED.request, response = EXCLUDED.response, "
                 "state = EXCLUDED.state", (sid, key, json.dumps(resp), json.dumps(state)))
    return 201, resp


# ------------------------------------------------------------------ live co-stream host controls (FR-3.3)
def load_session(conn, session_id: str, lock: bool = False) -> dict:
    row = conn.execute("SELECT response, state FROM costream_sessions WHERE session_id = %s"
                       + (" FOR UPDATE" if lock else ""), (session_id,)).fetchone()
    if row is None:
        raise ApiError(404, "STREAM_NOT_FOUND", "Co-stream not found", {"session_id": session_id})
    if row["state"]:
        return json.loads(row["state"])
    return costream_domain.state_from_response(json.loads(row["response"]))


def save_session(conn, state: dict) -> dict:
    conn.execute("UPDATE costream_sessions SET state = %s WHERE session_id = %s",
                 (json.dumps(state), state["session_id"]))
    view = costream_domain.view(state, media_base=MEDIA_HLS_BASE)
    bus.publish_realtime("costream_update", None, view)
    bus.invalidate_qr(state["session_id"])
    return view


def session_view(conn, session_id: str) -> dict:
    return costream_domain.view(load_session(conn, session_id), media_base=MEDIA_HLS_BASE)


def host_control(conn, session_id: str, actor: str | None, action: str, target) -> dict:
    state = load_session(conn, session_id, lock=True)
    return save_session(conn, costream_domain.apply_control(state, actor, action, target))


def host_drop(conn, session_id: str, actor: str | None) -> dict:
    """The host leaves (or their connection drops): hand off in array order, or end the session."""
    state = load_session(conn, session_id, lock=True)
    if actor != state["host"]:
        raise ApiError(403, "FORBIDDEN", "Only the host can leave as host", {"session_id": session_id})
    return save_session(conn, costream_domain.host_drop(state))


def invite(conn, session_id: str, actor: str | None, player_id, simulate_dlq: bool, now: int) -> dict:
    state = load_session(conn, session_id)
    if state["status"] != "active":
        raise ApiError(404, "STREAM_NOT_FOUND", "This co-stream has ended", {"session_id": session_id})
    if actor != state["host"]:
        raise ApiError(403, "FORBIDDEN", "Only the host can invite", {"session_id": session_id})
    if not isinstance(player_id, str) or not player_id:
        raise ApiError(400, "VALIDATION_ERROR", "player_id is required", {"fields": ["player_id"]})
    if not _player_exists(conn, player_id):
        raise ApiError(404, "PLAYER_NOT_FOUND", "Player not found", {"player_id": player_id})
    payload = costream_domain.invite_payload(session_id, player_id, now)
    token = costream_domain.make_invite(payload, sign_day2)
    sent = notifier.dispatch(conn, "costream_invite", player_id,
                             {"session_id": session_id, "invite_token": token, "from": actor},
                             simulate_dlq=simulate_dlq)
    return {"session_id": session_id, "player_id": player_id, "invite_token": token, "expires_at": payload["exp"],
            "notification": sent}


def join(conn, session_id: str, player_id: str | None, token, now: int) -> dict:
    payload = costream_domain.read_invite(token, sign_day2, now)
    state = load_session(conn, session_id, lock=True)
    return save_session(conn, costream_domain.join(state, player_id, payload))


# ------------------------------------------------------------------ guest cart merge (5.7)
def _guard_as_middleware(token: str) -> None:
    """Run the real request guard (main.py) against a simulated guest write."""
    from ..main import _guest_write_blocked  # late import: main imports the routers
    scope = {"method": "POST", "path": "/api/v1/chat", "headers": [(b"authorization", f"Bearer {token}".encode("latin-1"))]}
    if _guest_write_blocked(scope):
        raise cart_domain.guest_write_forbidden(token)


def _catalogue(conn, variant_ids: list[str]) -> tuple[dict, dict]:
    """(stock, unit price) per variant; price = latest price_schedule entry in effect, else the list price."""
    stock, prices, now = {}, {}, now_iso()
    for vid in variant_ids:
        row = conn.execute("SELECT v.price_minor, i.stock FROM variants v JOIN inventory i ON i.variant_id = v.variant_id "
                           "WHERE v.variant_id = %s", (vid,)).fetchone()
        sched = conn.execute("SELECT price_minor FROM price_schedule WHERE variant_id = %s AND effective_at <= %s "
                             "ORDER BY effective_at DESC LIMIT 1", (vid, now)).fetchone()
        stock[vid] = row["stock"] if row else 0
        prices[vid] = (sched or row)["price_minor"] if row else 0
    return stock, prices


def cart_merge(conn, body) -> tuple[int, dict]:
    req = cart_domain.validate_request(body)
    cart_domain.check_existence(
        req, lambda uid: _user_exists(conn, uid),
        lambda vid: conn.execute("SELECT 1 FROM variants WHERE variant_id = %s", (vid,)).fetchone() is not None)
    tok = req["guest_token"]
    conn.execute("INSERT INTO guest_tokens (guest_token, status, created_at) VALUES (%s, 'active', %s) "
                 "ON CONFLICT (guest_token) DO NOTHING", (tok, now_iso()))
    row = conn.execute("SELECT merge_request, merge_response FROM guest_tokens WHERE guest_token = %s FOR UPDATE",
                       (tok,)).fetchone()
    if cart_domain.replay_decision(req, row["merge_request"]) == "replay":
        return 200, json.loads(row["merge_response"])

    user = req["registered_user_id"]
    existing = [{"variant_id": r["variant_id"], "quantity": r["quantity"]} for r in conn.execute(
        "SELECT variant_id, quantity FROM carts WHERE user_id = %s ORDER BY variant_id FOR UPDATE", (user,)).fetchall()]
    ids = list(dict.fromkeys([*(i["variant_id"] for i in existing), *(i["variant_id"] for i in req["guest_cart"])]))
    stock, prices = _catalogue(conn, ids)
    items = cart_domain.merge_items(existing, req["guest_cart"], stock, prices)   # 409 OUT_OF_STOCK, nothing written
    if req["test_write_block"]:
        cart_domain.verify_write_block(tok, _guard_as_middleware)

    for it in items:
        conn.execute("INSERT INTO carts (user_id, variant_id, quantity) VALUES (%s, %s, %s) "
                     "ON CONFLICT (user_id, variant_id) DO UPDATE SET quantity = EXCLUDED.quantity",
                     (user, it["variant_id"], it["quantity"]))
    conn.execute("DELETE FROM guest_carts WHERE guest_token = %s", (tok,))
    resp = cart_domain.build_response(req, items)
    resp["signature"] = sign_day2(tok, cart_domain.sig_payload(resp))
    conn.execute("UPDATE guest_tokens SET status = 'merged', user_id = %s, merge_request = %s, merge_response = %s "
                 "WHERE guest_token = %s", (user, cart_domain.request_key(req), json.dumps(resp), tok))
    return 200, resp


# ------------------------------------------------------------------ moderation + DLQ (5.8)
def _enqueue_failed(conn, room: str, count: int) -> None:
    """Simulated failed notifications: each goes through the real retry policy against a disconnected
    subscriber (no real waiting), exhausts its attempts and lands in the DLQ."""
    def unreachable():
        raise ConnectionError("subscriber_unreachable")
    for i in range(count):
        result = notify.deliver(unreachable, sleep=lambda _s: None)
        event = notify.dlq_event("chat_notification", room, result, chat_room_id=room, index=i + 1)
        conn.execute("INSERT INTO dlq (event, attempts, created_at) VALUES (%s, %s, %s)",
                     (json.dumps(event), result["attempts"], now_iso()))


def _dlq_status(conn) -> dict:
    depth = conn.execute("SELECT count(*) AS n FROM dlq").fetchone()["n"]
    rows = conn.execute("SELECT id, event, attempts, created_at FROM dlq ORDER BY id LIMIT %s", (DLQ_REPORT_LIMIT,)).fetchall()
    events = [{"dlq_id": r["id"], "attempts": r["attempts"], "failed_at": r["created_at"], **json.loads(r["event"])}
              for r in rows]
    return {"queue_depth": depth, "undelivered_events": events}


def moderation_test(conn, body) -> dict:
    mod_domain.validate_request(body)
    room = body["chat_room_id"]
    if body.get("simulate_failed_notifications", 0):
        _enqueue_failed(conn, room, body["simulate_failed_notifications"])
    out = mod_domain.moderate(body["incoming_messages"])
    # Sorted inserts + ON CONFLICT DO NOTHING: 10 concurrent requests never deadlock or duplicate (edge case 3).
    actions = sorted({(u, "kick") for u in out["kicked_users"]} | {(u, "mute") for u in out["muted_users"]})
    for user, kind in actions:
        conn.execute("INSERT INTO moderation_actions (chat_room_id, user_id, kind) VALUES (%s, %s, %s) "
                     "ON CONFLICT DO NOTHING", (room, user, kind))
    dlq = _dlq_status(conn)
    resp = {"chat_room_id": room, "filtered_messages": out["filtered_messages"], "kicked_users": out["kicked_users"],
            "muted_users": out["muted_users"], "dlq_status": dlq}
    resp["signature"] = sign_day2(room, mod_domain.sig_payload(room, out["flagged_count"], out["kicked_users"],
                                                               dlq["queue_depth"]))
    return resp


# ------------------------------------------------------------------ member chat flood limit (FR-5.3, Appendix B 429)
def chat_rate_check(room: str, sender: str, now: float | None = None) -> None:
    """More than 3 messages in a 2 s sliding window from one sender in one room -> 429 RATE_LIMITED.
    The window lives in Redis (a sorted set of send times); if Redis is down the check is skipped."""
    import time as _time
    now = _time.time() if now is None else now
    key = f"chat:rate:{room}:{sender}"
    try:
        r = bus.client()
        r.zremrangebyscore(key, 0, now - mod_domain.RATE_WINDOW_S)
        recent = [float(t) for t in r.zrange(key, 0, -1)]
        if mod_domain.rate_exceeded(recent, now):
            retry = max(0.1, round(mod_domain.RATE_WINDOW_S - (now - min(recent)), 2))
            raise ApiError(429, "RATE_LIMITED", "You're sending messages too fast", {"retry_after": retry,
                                                                                     "reason": mod_domain.REASON_RATE})
        r.zadd(key, {repr(now): now})
        r.expire(key, int(mod_domain.RATE_WINDOW_S) + 1)
    except ApiError:
        raise
    except Exception:  # noqa: BLE001  the limiter must never take chat down
        return
