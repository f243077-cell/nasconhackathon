"""Part II contract + hidden-scenario checks against a running stack (expected vs actual).

Usage: DAY2_SALT=<salt> python tools/day2_check.py [base_url]
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
SALT2 = os.environ.get("DAY2_SALT", "T01D27ad7ffff12e")
RESULTS = []


def call(method, path, body=None, headers=None, follow=True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=20) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
            return r.status, (json.loads(raw) if "json" in ctype and raw else raw), {k.title(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), {k.title(): v for k, v in e.headers.items()}
        except ValueError:
            return e.code, raw, {k.title(): v for k, v in e.headers.items()}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def check(name, ok, expected, actual):
    RESULTS.append((name, bool(ok), expected, actual))


def code(r):
    return r[1].get("error", {}).get("code") if isinstance(r[1], dict) else None


def sig2(entity, payload):
    msg = (entity + "|" + json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)).encode()
    return hmac.new(SALT2.encode(), msg, hashlib.sha256).hexdigest()


def main():
    check("reset 200", call("POST", "/audit/v1/reset")[0] == 200, 200, "")
    s = call("GET", "/audit/v1/score/match-m1")[1]
    check("seed match-m1 in_progress 1-0", (s["status"], s["home"]["score"], s["away"]["score"]) ==
          ("in_progress", 1, 0), "in_progress 1-0", (s["status"], s["home"]["score"], s["away"]["score"]))

    # 5.4 stream keys
    body = {"action": "rotate", "player_id": "player-alpha-1", "label": "OBS-Main-Desk",
            "stream_key_override": "sk_live_9f83a1b2c3d4e5f6"}
    r = call("POST", "/audit/v1/stream/key", body)
    p = {"action": "rotate", "player_id": "player-alpha-1", "status": "active", "stream_key": "sk_live_9f83a1b2c3d4e5f6"}
    check("stream rotate 200 + signature", r[0] == 200 and r[1]["signature"] == sig2("sk_live_9f83a1b2c3d4e5f6", p),
          200, r[0])
    check("stream keys exact", sorted(r[1]) == sorted(["player_id", "label", "stream_key", "status", "ingest_endpoints",
                                                       "playback_url", "signature"]), "keys", sorted(r[1]))
    r = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})
    check("stream generate 201 + key format", r[0] == 201 and r[1]["stream_key"].startswith("sk_live_")
          and len(r[1]["stream_key"]) == 24, 201, r[0])
    r = call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})
    check("stream revoke 200 nulls", r[0] == 200 and r[1]["status"] == "revoked" and r[1]["ingest_endpoints"] is None
          and r[1]["playback_url"] is None, "revoked", r[1])
    check("revoke without key 404 STREAM_NOT_FOUND",
          code(call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-beta-2"})) ==
          "STREAM_NOT_FOUND", "STREAM_NOT_FOUND", "")
    check("bad action 400", code(call("POST", "/audit/v1/stream/key", {"action": "x", "player_id": "player-alpha-1"}))
          == "VALIDATION_ERROR", "VALIDATION_ERROR", "")
    check("unknown player 404", code(call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "nope"}))
          == "PLAYER_NOT_FOUND", "PLAYER_NOT_FOUND", "")

    # 5.5 co-stream
    cs = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
          "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"], "layout": "grid_4",
          "simulate_host_drop": True}
    r = call("POST", "/audit/v1/costream/session", cs)
    exp = {"session_id": "cs-session-101", "status": "active", "active_host": "player-alpha-2", "handoff_occurred": True,
           "participant_count": 3, "active_participants": ["player-alpha-2", "player-beta-1", "player-beta-2"],
           "layout": "grid_4", "composite_playback_url": "http://localhost:8888/costream/cs-session-101/index.m3u8",
           "chat_room_id": "chat-cs-session-101"}
    check("costream host drop (scenario 1)", r[0] == 201 and {k: r[1][k] for k in exp} == exp, exp, r[1])
    check("costream replay 200", call("POST", "/audit/v1/costream/session", cs)[0] == 200, 200, "")
    check("costream 5 -> 409 COSTREAM_SESSION_FULL", code(call("POST", "/audit/v1/costream/session", dict(
        cs, session_id="cs-session-5", participants=cs["participants"] + ["player-alpha-1b"]))) ==
        "COSTREAM_SESSION_FULL", "COSTREAM_SESSION_FULL", "")
    check("grid_2 with 3 -> 400 UNSUPPORTED_LAYOUT", code(call("POST", "/audit/v1/costream/session", dict(
        cs, session_id="cs-session-6", layout="grid_2", participants=cs["participants"][:3], simulate_host_drop=False)))
        == "UNSUPPORTED_LAYOUT", "UNSUPPORTED_LAYOUT", "")
    r = call("POST", "/audit/v1/costream/session", dict(cs, session_id="cs-session-7",
                                                        participants=["player-alpha-1"], layout="solo"))
    check("sole host drop -> terminated", r[1].get("status") == "terminated" and r[1].get("active_host") is None
          and r[1].get("participant_count") == 0, "terminated", r[1])

    # 5.6 QR + scenario 2
    r = call("GET", "/audit/v1/qr/match-m1")
    view = r[1]
    check("qr live route + signature", view["target_route"] == "/web/matches/match-m1/live" and view["signature"] ==
          sig2("match-m1", {"entity_id": "match-m1", "short_url": view["short_url"],
                            "target_route": view["target_route"]}), "live", view["target_route"])
    n = view["scan_count"]
    check("inspect does not count", call("GET", "/audit/v1/qr/match-m1?inspect=true")[1]["scan_count"] == n, n, "")
    r = call("GET", "/q/m1-live", follow=False)
    check("/q 302 -> live", r[0] == 302 and r[2].get("Location", "").endswith("/web/matches/match-m1/live"), 302, r[0])
    call("POST", "/audit/v1/events", {"event_id": "d2-end", "match_id": "match-m1", "type": "match_end", "payload": {}})
    v2 = call("GET", "/audit/v1/qr/match-m1?inspect=true")[1]
    check("scenario 2: same short_url, vod route, new signature", v2["short_url"] == view["short_url"] and
          v2["target_route"] == "/web/matches/match-m1/vod" and v2["signature"] != view["signature"], "vod",
          v2["target_route"])
    for fmt, ctype, magic in (("svg", "image/svg+xml", b"<"), ("png", "image/png", b"\x89PNG\r\n\x1a\n"),
                              ("pdf", "application/pdf", b"%PDF-")):
        r = call("GET", f"/audit/v1/qr/match-m1/export.{fmt}")
        check(f"export {fmt}", r[0] == 200 and r[2].get("Content-Type", "").startswith(ctype)
              and r[1][:len(magic)] == magic, ctype, r[2].get("Content-Type"))
    check("unknown entity 404 QR_NOT_FOUND", code(call("GET", "/audit/v1/qr/match-nope")) == "QR_NOT_FOUND",
          "QR_NOT_FOUND", "")

    # 5.7 guest guard + cart merge + scenario 4
    for path in ("/api/v1/chat", "/audit/v1/checkout", "/audit/v1/events"):
        r = call("POST", path, {}, {"Authorization": "Bearer guest_anon_tok_7721"})
        check(f"guest write {path} -> 403", r[0] == 403 and code(r) == "GUEST_WRITE_FORBIDDEN", 403, r[0])
    m = {"guest_token": "guest_anon_tok_7721", "registered_user_id": "player-alpha-1",
         "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "test_write_block": True}
    res = []
    ts = [threading.Thread(target=lambda: res.append(call("POST", "/audit/v1/guest/cart-merge", m))) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    check("scenario 4: two merges -> both 200, total_items 1",
          [x[0] for x in res] == [200, 200] and all(x[1]["active_cart"]["total_items"] == 1 for x in res),
          "200,200 / 1", [(x[0], x[1].get("active_cart", {}).get("total_items")) for x in res])
    check("merge write block verified", res[0][1]["write_block_verified"] is True and
          res[0][1]["write_rejection_code"] == 403, True, "")
    check("token reused for other user -> 409", code(call("POST", "/audit/v1/guest/cart-merge", dict(
        m, registered_user_id="player-alpha-2"))) == "GUEST_TOKEN_ALREADY_MERGED", "GUEST_TOKEN_ALREADY_MERGED", "")
    check("merge over stock -> 409 OUT_OF_STOCK", code(call("POST", "/audit/v1/guest/cart-merge", dict(
        m, guest_token="guest_x", guest_cart=[{"variant_id": "var-jersey-001-M", "quantity": 9}]))) == "OUT_OF_STOCK",
        "OUT_OF_STOCK", "")
    check("bad guest token -> 400", code(call("POST", "/audit/v1/guest/cart-merge", dict(m, guest_token="tok")))
          == "VALIDATION_ERROR", "VALIDATION_ERROR", "")

    # 5.8 moderation + scenario 3
    mod = {"chat_room_id": "chat-cs-session-101", "incoming_messages": [
        {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary"},
        {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream b@d_w0rd now!"},
        {"message_id": "msg-3", "sender": "user-flooder", "text": "GOAL! AAAA!!!"}], "check_dlq": True}
    res = []
    ts = [threading.Thread(target=lambda: res.append(call("POST", "/audit/v1/moderation/test", mod))) for _ in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    check("scenario 3: 10 parallel -> all 200, kicked exactly [user-spammer]",
          all(x[0] == 200 and x[1]["kicked_users"] == ["user-spammer"] for x in res), "200 x10", [x[0] for x in res])
    r = res[0][1]
    check("masked text", r["filtered_messages"][1]["text"] == "Watch this illegal stream *** now!", "***", r)
    check("flooder muted + dropped", r["muted_users"] == ["user-flooder"] and len(r["filtered_messages"]) == 2,
          "muted", r["muted_users"])
    r = call("POST", "/audit/v1/moderation/test", dict(mod, simulate_failed_notifications=2))[1]
    check("DLQ depth grows by 2", r["dlq_status"]["queue_depth"] == 2 and len(r["dlq_status"]["undelivered_events"])
          == 2, 2, r["dlq_status"]["queue_depth"])

    # FR-3.2 recording hook is internal: no token -> 403 (or 404 when disabled)
    r = call("POST", "/internal/media/recorded", {"path": "live/sk_live_0000000000000000", "segment_path": "/etc/passwd"})
    check("media hook rejects unauthenticated calls", r[0] in (403, 404), "403/404", r[0])

    # 5.9 metrics + privacy
    r = call("GET", "/metrics")
    text = r[1].decode() if isinstance(r[1], bytes) else str(r[1])
    check("metrics content-type + 5 names", r[2].get("Content-Type") == "text/plain; version=0.0.4" and all(
        n in text for n in ("nascon_active_ws_connections", "nascon_active_streams_total", "nascon_stream_bitrate_kbps",
                            "nascon_dlq_depth", "nascon_qr_scans_total")), "ok", r[2].get("Content-Type"))
    r = call("DELETE", "/audit/v1/privacy/user/player-alpha-1")
    check("privacy erase", r[0] == 200 and r[1] == {"user_id": "player-alpha-1", "status": "anonymized",
                                                    "pii_retained": False, "tokens_wiped": True}, 200, r)

    fails = [x for x in RESULTS if not x[1]]
    for name, ok, exp, act in RESULTS:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n   expected: {exp}\n   actual:   {str(act)[:300]}"))
    print(f"\nTOTAL: {len(RESULTS)} checks | {len(RESULTS) - len(fails)} passed | {len(fails)} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
