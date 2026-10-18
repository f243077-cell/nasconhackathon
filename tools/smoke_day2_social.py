"""Grader-style checks for co-stream (5.5), guest cart merge (5.7) and moderation + DLQ (5.8) against a running
stack (stdlib only). Resets the database first.

Usage: DAY2_SALT=<salt> python tools/smoke_day2_social.py [base_url]
"""
import hashlib
import hmac
import json
import os
import sys
import threading
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
SALT = os.environ.get("DAY2_SALT", "")
FAILS: list[str] = []


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, txt


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))
    if not cond:
        FAILS.append(name)


def sign(entity_id, payload):
    msg = entity_id + "|" + json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(SALT.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def err(r):
    return r[1].get("error", {}).get("code") if isinstance(r[1], dict) else None


def concurrently(n, fn):
    out, threads = [None] * n, []
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        out[i] = fn()
    for i in range(n):
        threads.append(threading.Thread(target=run, args=(i,)))
        threads[-1].start()
    for t in threads:
        t.join()
    return out


def costream():
    body = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
            "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"],
            "layout": "grid_4", "simulate_host_drop": True}
    s, b = call("POST", "/audit/v1/costream/session", body)
    want = {"session_id": "cs-session-101", "status": "active", "active_host": "player-alpha-2", "handoff_occurred": True,
            "participant_count": 3, "active_participants": ["player-alpha-2", "player-beta-1", "player-beta-2"],
            "layout": "grid_4", "composite_playback_url": "http://localhost:8888/costream/cs-session-101/index.m3u8",
            "chat_room_id": "chat-cs-session-101"}
    check("costream: 201", s == 201, (s, b))
    check("costream: body", isinstance(b, dict) and {k: b.get(k) for k in want} == want, b)
    if isinstance(b, dict):
        payload = {k: b[k] for k in ("active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status")}
        check("costream: signature", b.get("signature") == sign("cs-session-101", payload), b.get("signature"))
    s2, b2 = call("POST", "/audit/v1/costream/session", body)
    check("costream: identical replay 200, same body", s2 == 200 and b2 == b, (s2, b2))
    r = call("POST", "/audit/v1/costream/session", {**body, "participants": [*body["participants"], "player-alpha-3"]})
    check("costream: 5 participants 409 COSTREAM_SESSION_FULL or 404", err(r) in ("COSTREAM_SESSION_FULL", "PLAYER_NOT_FOUND"), r)
    r = call("POST", "/audit/v1/costream/session", {**body, "participants": ["player-alpha-1", "ghost-9"]})
    check("costream: unknown participant 404", r[0] == 404 and err(r) == "PLAYER_NOT_FOUND", r)
    r = call("POST", "/audit/v1/costream/session", {**body, "session_id": "cs-x", "host_player_id": "player-beta-2",
                                                    "participants": ["player-alpha-1"]})
    check("costream: host not in participants 400", r[0] == 400 and err(r) == "VALIDATION_ERROR", r)
    r = call("POST", "/audit/v1/costream/session", {**body, "session_id": "cs-y", "layout": "grid_2"})
    check("costream: grid_2 with 3 after drop 400 UNSUPPORTED_LAYOUT", r[0] == 400 and err(r) == "UNSUPPORTED_LAYOUT", r)
    s, b = call("POST", "/audit/v1/costream/session", {"session_id": "cs-z", "host_player_id": "player-alpha-1",
                                                       "participants": ["player-alpha-1"], "simulate_host_drop": True})
    check("costream: last host drops -> terminated", s == 201 and b.get("status") == "terminated"
          and b.get("active_host") is None and b.get("participant_count") == 0, b)


def cart():
    body = {"guest_token": "guest_anon_tok_7721", "registered_user_id": "player-alpha-1",
            "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "test_write_block": True}
    for path, payload in (("/api/v1/chat", {"room_id": "chat-cs-session-101", "text": "hi"}),
                          ("/audit/v1/checkout", {}), ("/audit/v1/events", {})):
        r = call("POST", path, payload, token="guest_anon_tok_7721")
        check(f"guest write {path} -> 403 GUEST_WRITE_FORBIDDEN", r[0] == 403 and err(r) == "GUEST_WRITE_FORBIDDEN"
              and r[1]["error"]["details"].get("guest_token") == "guest_anon_tok_7721", r)
    r = call("POST", "/audit/v1/guest/cart-merge", {**body, "guest_cart": [{"variant_id": "var-nope", "quantity": 1}]})
    check("cart: unknown variant 404", r[0] == 404 and err(r) == "VARIANT_NOT_FOUND", r)
    r = call("POST", "/audit/v1/guest/cart-merge", {**body, "registered_user_id": "ghost-9"})
    check("cart: unknown user 404", r[0] == 404 and err(r) == "PLAYER_NOT_FOUND", r)
    r = call("POST", "/audit/v1/guest/cart-merge", {**body, "guest_token": "anon_7721"})
    check("cart: bad token 400", r[0] == 400 and err(r) == "VALIDATION_ERROR", r)

    # Edge case 4: the same merge sent twice at once -> both 200, total_items 1, never 2.
    results = concurrently(2, lambda: call("POST", "/audit/v1/guest/cart-merge", body))
    check("cart: concurrent identical merges both 200", all(r[0] == 200 for r in results), results)
    b = results[0][1]
    want_cart = {"user_id": "player-alpha-1", "currency": "PKR", "total_items": 1, "subtotal_minor": 450000,
                 "items": [{"variant_id": "var-jersey-001-L", "quantity": 1, "unit_price_minor": 450000}]}
    check("cart: body", isinstance(b, dict) and b.get("write_block_verified") is True and b.get("write_rejection_code") == 403
          and b.get("cart_merged") is True and b.get("active_cart") == want_cart, b)
    check("cart: both responses identical", results[0][1] == results[1][1], results)
    if isinstance(b, dict):
        payload = {"cart_merged": True, "guest_token": "guest_anon_tok_7721", "registered_user_id": "player-alpha-1",
                   "total_items": 1, "write_rejection_code": 403}
        check("cart: signature", b.get("signature") == sign("guest_anon_tok_7721", payload), b.get("signature"))
    s, b3 = call("POST", "/audit/v1/guest/cart-merge", body)
    check("cart: third identical replay still total_items 1", s == 200 and b3.get("active_cart", {}).get("total_items") == 1, b3)
    r = call("POST", "/audit/v1/guest/cart-merge", {**body, "registered_user_id": "player-alpha-2"})
    check("cart: merged token + other user 409", r[0] == 409 and err(r) == "GUEST_TOKEN_ALREADY_MERGED", r)


def moderation():
    body = {"chat_room_id": "chat-cs-session-101", "check_dlq": True, "simulate_failed_notifications": 0,
            "incoming_messages": [
                {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary"},
                {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream p0rn now!"},
                {"message_id": "msg-3", "sender": "user-flooder", "text": "GOOOOOAL!!!"}]}
    s, b = call("POST", "/audit/v1/moderation/test", body)
    check("moderation: 200", s == 200, (s, b))
    want_msgs = [
        {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary", "flagged": False, "reason": None},
        {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream *** now!", "flagged": True,
         "reason": "profanity_leetspeak"}]
    check("moderation: filtered_messages", b.get("filtered_messages") == want_msgs, b.get("filtered_messages"))
    check("moderation: kicked/muted", b.get("kicked_users") == ["user-spammer"] and b.get("muted_users") == ["user-flooder"], b)
    check("moderation: dlq empty after reset", b.get("dlq_status") == {"queue_depth": 0, "undelivered_events": []}, b.get("dlq_status"))
    payload = {"chat_room_id": "chat-cs-session-101", "flagged_count": 1, "kicked_users": ["user-spammer"], "queue_depth": 0}
    check("moderation: signature", b.get("signature") == sign("chat-cs-session-101", payload), b.get("signature"))

    s, b = call("POST", "/audit/v1/moderation/test", {**body, "simulate_failed_notifications": 2})
    dlq = b.get("dlq_status", {})
    check("moderation: 2 failed notifications -> queue_depth 2", s == 200 and dlq.get("queue_depth") == 2
          and len(dlq.get("undelivered_events", [])) == 2 and all(e.get("attempts") == 3 for e in dlq["undelivered_events"]), dlq)

    # Edge case 3: 10 simultaneous requests on the same spammer -> no 5xx, kicked exactly once in each body.
    spam = {**body, "incoming_messages": [{"message_id": "m", "sender": "user-spammer", "text": "b@d_w0rd"}]}
    results = concurrently(10, lambda: call("POST", "/audit/v1/moderation/test", spam))
    check("moderation: 10 concurrent -> all 200", all(r[0] == 200 for r in results), [r[0] for r in results])
    check("moderation: 10 concurrent -> kicked exactly [user-spammer]",
          all(r[1].get("kicked_users") == ["user-spammer"] for r in results if isinstance(r[1], dict)), results[0])
    check("moderation: DLQ depth intact under the race",
          all(r[1].get("dlq_status", {}).get("queue_depth") == 2 for r in results if isinstance(r[1], dict)), results[0])
    r = call("POST", "/audit/v1/moderation/test", {**body, "incoming_messages": "nope"})
    check("moderation: bad body 400", r[0] == 400 and err(r) == "VALIDATION_ERROR", r)


def athletes():
    """FR-3.1: profile, idempotent follow, zero follower-count drift under concurrent toggles."""
    tokens = {}
    for who in ("viewer", "manager", "organizer", "player"):
        s, b = call("POST", "/api/v1/auth/login", {"email": f"{who}@nascon.test", "password": "Nascon@26"})
        tokens[who] = b.get("token") if s == 200 else None
    check("athletes: demo logins", all(tokens.values()), tokens)
    target = "player-alpha-2"
    s, b = call("GET", f"/api/v1/athletes/{target}", token=tokens["viewer"])
    check("athletes: profile 200", s == 200 and b.get("athlete_id") == target and "career" in b
          and "upcoming_fixtures" in b and "affiliations" in b and b.get("follower_count") == 0, (s, b))
    s, b = call("GET", f"/api/v1/athletes/{target}")
    check("athletes: guest can read a profile", s == 200 and b.get("following") is None, (s, b))
    r = call("POST", f"/api/v1/athletes/{target}/follow", token="guest_anon_tok_7721")
    check("athletes: guest follow -> 403 GUEST_WRITE_FORBIDDEN", r[0] == 403 and err(r) == "GUEST_WRITE_FORBIDDEN", r)
    r = call("GET", "/api/v1/athletes/player-ghost", token=tokens["viewer"])
    check("athletes: unknown -> 404", r[0] == 404 and err(r) == "PLAYER_NOT_FOUND", r)
    r = call("POST", "/api/v1/athletes/player-alpha-1/follow", token=tokens["player"])
    check("athletes: self-follow -> 400", r[0] == 400 and err(r) == "VALIDATION_ERROR", r)

    # 10 simultaneous follows by one user -> exactly 1 follower; 10 unfollows -> 0.
    res = concurrently(10, lambda: call("POST", f"/api/v1/athletes/{target}/follow", token=tokens["viewer"]))
    check("athletes: 10 concurrent follows -> all 200", all(r[0] == 200 for r in res), [r[0] for r in res])
    s, b = call("GET", f"/api/v1/athletes/{target}", token=tokens["viewer"])
    check("athletes: count 1 after duplicate follows", b.get("follower_count") == 1 and b.get("following") is True, b)
    # 4 users toggling at once: everyone follows, then everyone unfollows.
    who = list(tokens)
    concurrently(4, lambda i=iter(who): call("POST", f"/api/v1/athletes/{target}/follow", token=tokens[next(i)]))
    s, b = call("GET", f"/api/v1/athletes/{target}", token=tokens["viewer"])
    check("athletes: 4 users -> count 4", b.get("follower_count") == 4, b.get("follower_count"))
    concurrently(10, lambda: call("DELETE", f"/api/v1/athletes/{target}/follow", token=tokens["viewer"]))
    concurrently(3, lambda i=iter(who[1:]): call("DELETE", f"/api/v1/athletes/{target}/follow", token=tokens[next(i)]))
    s, b = call("GET", f"/api/v1/athletes/{target}", token=tokens["viewer"])
    check("athletes: all unfollowed -> count 0, no drift", b.get("follower_count") == 0 and b.get("following") is False, b)


def main():
    if not SALT:
        print("Set DAY2_SALT to the stack's salt to check signatures.")
    s, b = call("POST", "/audit/v1/reset", {})
    check("reset 200", s == 200, (s, b))
    costream()
    cart()
    moderation()
    athletes()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nALL PASS")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
