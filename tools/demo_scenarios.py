"""Run the Part II hidden scenarios live and print what happened, in plain words (demo / viva helper).

Usage:  py -3.12 tools/demo_scenarios.py [base_url] [1|2|3|4|all]
        base_url defaults to http://localhost:8080. Each scenario resets the data first.
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
WHICH = sys.argv[2] if len(sys.argv) > 2 else "all"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def call(method, path, body=None, token=None, follow=True):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), dict(e.headers)
        except ValueError:
            return e.code, raw.decode(errors="replace"), dict(e.headers)


def reset():
    call("POST", "/audit/v1/reset", {})


def line(text=""):
    print(text, flush=True)


def scenario_1():
    line("SCENARIO 1: the host disconnects in the middle of a 4-way co-stream")
    reset()
    body = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
            "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"], "layout": "grid_4"}
    s, before, _ = call("POST", "/audit/v1/costream/session", {**body, "simulate_host_drop": False})
    line(f"  before: host = {before['active_host']}, {before['participant_count']} broadcasters, chat room = {before['chat_room_id']}")
    s, after, _ = call("POST", "/audit/v1/costream/session", {**body, "simulate_host_drop": True})
    line(f"  host drops -> HTTP {s}: host = {after['active_host']}, handoff_occurred = {after['handoff_occurred']}, "
         f"{after['participant_count']} broadcasters left, chat room = {after['chat_room_id']}")
    line(f"  still on air: {after['composite_playback_url']}")
    ok = after["active_host"] == "player-alpha-2" and after["participant_count"] == 3 and \
        after["chat_room_id"] == before["chat_room_id"]
    line(f"  RESULT: {'PASS' if ok else 'FAIL'} - participants[1] took over, count 4 -> 3, same chat room")
    s, solo, _ = call("POST", "/audit/v1/costream/session", {"session_id": "cs-solo", "host_player_id": "player-alpha-1",
                                                             "participants": ["player-alpha-1"], "simulate_host_drop": True})
    line(f"  only host, host drops -> status = {solo['status']}, host = {solo['active_host']}")
    line()


def _qr(label):
    s, v, _ = call("GET", "/audit/v1/qr/match-m1")
    s2, _, h = call("GET", "/q/m1-live", follow=False)
    line(f"  {label:<22} short_url = {v['short_url']}")
    line(f"  {'':<22} target    = {v['target_route']}   (/q/m1-live -> {s2} {h.get('Location', h.get('location'))})")
    line(f"  {'':<22} signature = {v['signature'][:16]}...")
    return v


def scenario_2():
    line("SCENARIO 2: a QR poster is printed while the match is live, then the match ends or is postponed")
    reset()
    live = _qr("match live:")
    call("POST", "/audit/v1/events", {"event_id": f"demo-end-{time.time_ns()}", "match_id": "match-m1",
                                      "type": "match_end", "payload": {}})
    done = _qr("after match_end:")
    ok1 = done["short_url"] == live["short_url"] and done["target_route"].endswith("/vod") and \
        done["signature"] != live["signature"]
    line(f"  RESULT: {'PASS' if ok1 else 'FAIL'} - same printed link, now goes to the replay, new signature")

    reset()
    s, b, _ = call("POST", "/api/v1/auth/login", {"email": "organizer@nascon.test", "password": "Nascon@26"})
    s, _, _ = call("POST", "/api/v1/matches/match-m1/status", {"to": "postponed", "reason": "rain"}, token=b["token"])
    post = _qr("after postpone:")
    ok2 = post["target_route"].endswith("/notice?state=postponed") and post["short_url"] == live["short_url"]
    line(f"  RESULT: {'PASS' if ok2 else 'FAIL'} - same printed link, now shows the postponement notice")
    line("  Try it in a browser: open the /q/m1-live link before and after.")
    reset()
    line()


def scenario_3():
    line("SCENARIO 3: 10 moderators act on the same spammer at the same instant")
    reset()
    body = {"chat_room_id": "chat-cs-session-101", "check_dlq": True, "simulate_failed_notifications": 0,
            "incoming_messages": [{"message_id": "m1", "sender": "user-spammer", "text": "Watch this b@d_w0rd stream"},
                                  {"message_id": "m2", "sender": "user-flooder", "text": "GOAL! AAAA!!!"}]}
    results, barrier = [None] * 10, threading.Barrier(10)

    def fire(i):
        barrier.wait()
        results[i] = call("POST", "/audit/v1/moderation/test", body)
    threads = [threading.Thread(target=fire, args=(i,)) for i in range(10)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    took = time.monotonic() - t0
    codes = [r[0] for r in results]
    kicked = {json.dumps(r[1].get("kicked_users")) for r in results}
    depth = {r[1]["dlq_status"]["queue_depth"] for r in results}
    sample = results[0][1]
    line(f"  10 requests in {took:.2f} s, status codes: {codes}")
    line(f"  masked text: {sample['filtered_messages'][0]['text']!r}  (flagged = {sample['filtered_messages'][0]['flagged']})")
    line(f"  kicked_users in every response: {', '.join(kicked)}   muted_users: {sample['muted_users']}")
    line(f"  DLQ depth in every response: {sorted(depth)}")
    ok = codes == [200] * 10 and kicked == {'["user-spammer"]'} and depth == {0}
    line(f"  RESULT: {'PASS' if ok else 'FAIL'} - no errors or deadlock, spammer kicked exactly once, DLQ intact")
    line()


def scenario_4():
    line("SCENARIO 4: the same guest cart merge arrives twice (phone switches 4G -> Wi-Fi)")
    reset()
    body = {"guest_token": "guest_anon_tok_7721", "registered_user_id": "player-alpha-1",
            "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "test_write_block": True}
    out = [None, None]
    barrier = threading.Barrier(2)

    def fire(i):
        barrier.wait()
        out[i] = call("POST", "/audit/v1/guest/cart-merge", body)
    ts = [threading.Thread(target=fire, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    for i, (s, b, _) in enumerate(out, 1):
        line(f"  call {i}: HTTP {s}, total_items = {b['active_cart']['total_items']}, write blocked for guest = {b['write_rejection_code']}")
    s, b, _ = call("POST", "/audit/v1/guest/cart-merge", {**body, "registered_user_id": "player-alpha-2"})
    line(f"  same token, different user: HTTP {s} {b['error']['code'] if isinstance(b, dict) and 'error' in b else b}")
    ok = all(r[0] == 200 and r[1]["active_cart"]["total_items"] == 1 for r in out) and s == 409
    line(f"  RESULT: {'PASS' if ok else 'FAIL'} - merged once, never 2 items")
    reset()
    line()


if __name__ == "__main__":
    runs = {"1": scenario_1, "2": scenario_2, "3": scenario_3, "4": scenario_4}
    for key in (runs if WHICH == "all" else [WHICH]):
        runs[key]()
