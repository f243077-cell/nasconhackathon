"""Grader-style smoke checks against a running stack (stdlib only).

Usage: DAY1_SALT=<salt> python tools/smoke.py [base_url]
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
SALT = os.environ.get("DAY1_SALT", "demo-salt")
FAILS: list[str] = []


def call(method, path, body=None, token=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null"), dict(r.headers)
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            return e.code, json.loads(txt), dict(e.headers)
        except ValueError:
            return e.code, txt, dict(e.headers)


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))
    if not cond:
        FAILS.append(name)


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sig(id_, payload):
    return hmac.new(SALT.encode(), (id_ + "|" + canon(payload)).encode(), hashlib.sha256).hexdigest()


def code(r):
    return r[1].get("error", {}).get("code") if isinstance(r[1], dict) else None


def main():
    s, b, _ = call("POST", "/audit/v1/reset", {})
    check("reset 200", s == 200 and b["status"] == "reset_complete", b)
    first = b
    s, b2, _ = call("POST", "/audit/v1/reset")
    check("reset idempotent body", b2 == first, b2)
    check("health ok", call("GET", "/health")[1] == {"status": "ok"})

    # ---- sports
    kab = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
           "periods": {"count": 2, "duration_minutes": 20},
           "scoring_events": {"raid_point": {"points": 1}, "all_out": {"points": 2}},
           "draw_allowed": False, "overtime": {"policy": "golden_score", "duration_minutes": 5},
           "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2}}}
    r = call("POST", "/audit/v1/sports", kab)
    check("sport create 201", r[0] == 201 and r[1]["status"] == "created", r)
    check("sport dup 409", code(call("POST", "/audit/v1/sports", kab)) == "SPORT_EXISTS")
    r = call("POST", "/audit/v1/sports", dict(kab, sport_id="x'; DROP TABLE sports;--"))
    check("sql-ish sport id 400", r[0] == 400 and code(r) == "VALIDATION_ERROR", r)
    r = call("POST", "/audit/v1/sports", raw=b"{not json")
    check("malformed json 400", r[0] == 400, r)

    # ---- events / score
    ev = lambda i, t, p, m="mk1": {"event_id": i, "match_id": m, "type": t, "payload": p}
    r = call("POST", "/audit/v1/events", ev("k1", "match_init", {"sport_id": "kabaddi", "home_team_id": "A", "away_team_id": "B"}))
    check("match_init 201", r[0] == 201 and r[1]["sequence"] == 1, r)
    check("score before start 409", code(call("POST", "/audit/v1/events", ev("k2", "score", {"team_id": "A", "event_type": "raid_point"}))) == "MATCH_NOT_IN_PROGRESS")
    call("POST", "/audit/v1/events", ev("k3", "match_start", {}))
    r = call("POST", "/audit/v1/events", ev("k4", "score", {"team_id": "A", "event_type": "all_out"}))
    check("score signature", r[0] == 201 and r[1]["signature"] == sig("k4", {"team_id": "A", "event_type": "all_out"}), r)
    check("event replay 200", call("POST", "/audit/v1/events", ev("k4", "score", {"team_id": "A", "event_type": "all_out"}))[0] == 200)
    check("event dup 409", code(call("POST", "/audit/v1/events", ev("k4", "score", {"team_id": "B", "event_type": "all_out"}))) == "DUPLICATE_EVENT_ID")
    check("unknown event type 400", code(call("POST", "/audit/v1/events", ev("k5", "score", {"team_id": "A", "event_type": "goal"}))) == "UNKNOWN_EVENT_TYPE")
    check("compensation 201", code(call("POST", "/audit/v1/events", ev("k6", "compensation", {"compensates": "k4", "reason": "x"}))) is None)
    check("end level 409", code(call("POST", "/audit/v1/events", ev("k7", "match_end", {}))) == "TIE_NOT_ALLOWED")
    check("double comp 409", code(call("POST", "/audit/v1/events", ev("k8", "compensation", {"compensates": "k4", "reason": "x"}))) == "INVALID_COMPENSATION")
    check("comp unknown 404", code(call("POST", "/audit/v1/events", ev("k9", "compensation", {"compensates": "nope", "reason": "x"}))) == "EVENT_NOT_FOUND")
    call("POST", "/audit/v1/events", ev("k10", "tiebreak_winner", {"team_id": "B"}))
    r = call("POST", "/audit/v1/events", ev("k11", "match_end", {}))
    check("end with tiebreak 201", r[0] == 201, r)
    s, sc, _ = call("GET", "/audit/v1/score/mk1")
    check("score projection", sc["outcome"] == "away_win" and sc["winner_team_id"] == "B" and sc["home"]["score"] == 0
          and sc["events"][2]["compensated"] is True and sc["version"] == 6, sc)
    check("match 404", code(call("POST", "/audit/v1/events", ev("z1", "match_start", {}, "nomatch"))) == "MATCH_NOT_FOUND")

    # cricket limits
    call("POST", "/audit/v1/events", ev("c1", "match_init", {"sport_id": "cricket", "home_team_id": "H", "away_team_id": "W"}, "mc"))
    call("POST", "/audit/v1/events", ev("c2", "match_start", {}, "mc"))
    for i, et in enumerate(["six", "wide", "wicket", "four"]):
        call("POST", "/audit/v1/events", ev(f"c3{i}", "score", {"team_id": "H", "event_type": et}, "mc"))
    sc = call("GET", "/audit/v1/score/mc")[1]
    check("cricket projection", sc["home"]["score"] == 11 and sc["home"]["balls"] == 3 and sc["home"]["overs"] == "0.3"
          and sc["home"]["wickets"] == 1, sc["home"])

    # ---- leagues
    lg = {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2", "t3"],
          "fixtures": [{"match_id": "m1", "home": "t1", "away": "t2"}], "qualification": {"spots": 2}}
    check("league 201", call("POST", "/audit/v1/leagues", lg)[0] == 201)
    check("league dup 409", code(call("POST", "/audit/v1/leagues", lg)) == "LEAGUE_EXISTS")
    check("league sport 404", code(call("POST", "/audit/v1/leagues", dict(lg, league_id="lg-2", sport_id="zzz"))) == "SPORT_NOT_FOUND")
    check("league match exists 409", code(call("POST", "/audit/v1/leagues", dict(lg, league_id="lg-3"))) == "MATCH_EXISTS")

    # ---- checkout burst
    call("POST", "/audit/v1/reset", {"stock": {"var-jersey-001-M": 1}})
    results = []
    barrier = threading.Barrier(20)

    def buy(i):
        barrier.wait()
        results.append(call("POST", "/audit/v1/checkout", {
            "order_id": f"ord-{i}", "customer_id": "cust-<script>\"x", "items": [{"variant_id": "var-jersey-001-M", "quantity": 1}],
            "discount_code": None, "payment": {"token": "tok_success"}}))
    ts = [threading.Thread(target=buy, args=(i,)) for i in range(20)]
    t0 = time.time()
    [t.start() for t in ts]
    [t.join() for t in ts]
    codes = sorted(r[0] for r in results)
    check("burst 1x201 19x409", codes.count(201) == 1 and codes.count(409) == 19, codes)
    check("burst under 10s", time.time() - t0 < 10)
    inv = call("GET", "/audit/v1/inventory/var-jersey-001-M")[1]
    check("inventory 0/0", inv == {"variant_id": "var-jersey-001-M", "stock": 0, "reserved": 0}, inv)
    ok = [r for r in results if r[0] == 201][0][1]
    check("receipt signature", ok["receipt"]["signature"] == sig(ok["order_id"], ok["receipt"]["payload"]))
    pdf = base64.b64decode(ok["receipt"]["pdf_base64"])
    check("receipt pdf", pdf.startswith(b"%PDF"))
    r = call("POST", "/audit/v1/checkout", {"order_id": "ord-L", "customer_id": "c", "items": [{"variant_id": "var-jersey-001-L", "quantity": 2}],
                                          "discount_code": "WELCOME10", "payment": {"token": "tok_capture_fail"}})
    check("capture fail 402", r[0] == 402 and code(r) == "PAYMENT_CAPTURE_FAILED", r)
    check("stock released", call("GET", "/audit/v1/inventory/var-jersey-001-L")[1]["stock"] == 5)
    body = {"order_id": "ord-L2", "customer_id": "c", "items": [{"variant_id": "var-jersey-001-L", "quantity": 2}],
            "discount_code": "WELCOME10", "payment": {"token": "tok_success"}}
    r = call("POST", "/audit/v1/checkout", body)
    check("discount totals", r[0] == 201 and r[1]["discount_minor"] == 90000 and r[1]["total_minor"] == 810000, r)
    check("checkout replay 200", call("POST", "/audit/v1/checkout", body)[0] == 200)
    check("order dup 409", code(call("POST", "/audit/v1/checkout", dict(body, customer_id="other"))) == "DUPLICATE_ORDER_ID")
    check("bad discount 400", code(call("POST", "/audit/v1/checkout", dict(body, order_id="o3", discount_code="NOPE"))) == "INVALID_DISCOUNT_CODE")
    check("variant 404", code(call("POST", "/audit/v1/checkout", dict(body, order_id="o4", items=[{"variant_id": "nope", "quantity": 1}]))) == "VARIANT_NOT_FOUND")
    check("declined 402", code(call("POST", "/audit/v1/checkout", dict(body, order_id="o5", payment={"token": "tok_declined"}))) == "PAYMENT_DECLINED")

    # ---- RBAC
    m = call("POST", "/audit/v1/rbac-matrix")[1]
    T, C = m["tokens"], m["context"]
    A, D = 200, 403
    matrix = [
        ("POST", "/audit/v1/rbac/tenants", [A, D, D, D, D]),
        ("POST", f"/audit/v1/rbac/leagues/{C['own_league_id']}/fixtures", [A, A, D, D, D]),
        ("POST", f"/audit/v1/rbac/leagues/{C['other_league_id']}/fixtures", [A, D, D, D, D]),
        ("POST", f"/audit/v1/rbac/leagues/{C['foreign_league_id']}/fixtures", [A, D, D, D, D]),
        ("POST", f"/audit/v1/rbac/clubs/{C['own_club_id']}/roster", [A, D, A, D, D]),
        ("POST", f"/audit/v1/rbac/clubs/{C['other_club_id']}/products", [A, D, D, D, D]),
        ("POST", f"/audit/v1/rbac/clubs/{C['foreign_club_id']}/roster", [A, D, D, D, D]),
        ("PATCH", f"/audit/v1/rbac/players/{C['own_player_id']}", [A, D, A, A, D]),
        ("PATCH", f"/audit/v1/rbac/players/{C['other_player_id']}", [A, D, D, D, D]),
        ("PATCH", f"/audit/v1/rbac/players/{C['foreign_player_id']}", [A, D, D, D, D]),
        ("GET", f"/audit/v1/rbac/clubs/{C['other_club_id']}", [A, A, A, A, A]),
        ("GET", f"/audit/v1/rbac/clubs/{C['foreign_club_id']}", [A, D, D, D, D]),
        ("GET", "/audit/v1/rbac/platform/config", [A, D, D, D, D]),
    ]
    roles = ["super_admin", "league_organizer", "club_manager", "player", "viewer"]
    bad = []
    for method, path, exp in matrix:
        for role, e in zip(roles, exp):
            got = call(method, path, {} if method != "GET" else None, T[role])[0]
            if got != e:
                bad.append(f"{method} {path} {role}: {got}!={e}")
    check("rbac matrix", not bad, bad)
    check("no token 401", call("GET", "/audit/v1/rbac/platform/config")[0] == 401)
    t = T["super_admin"]
    tampered = t[:-2] + ("AA" if not t.endswith("AA") else "BB")
    check("tampered 401", call("GET", "/audit/v1/rbac/platform/config", token=tampered)[0] == 401)
    hdr = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    none_tok = hdr + "." + t.split(".")[1] + "."
    check("alg none 401", call("GET", "/audit/v1/rbac/platform/config", token=none_tok)[0] == 401)

    # ---- body size + rate limit
    check("413", call("POST", "/audit/v1/sports", raw=b"{" + b" " * (1024 * 1024 + 10) + b"}")[0] == 413)
    rl = [call("GET", "/api/v1/ping") for _ in range(150)]
    n429 = sum(1 for r in rl if r[0] == 429)
    check("rate limit first 200", rl[0][0] == 200 and rl[0][1] == {"pong": True})
    check("rate limit >=40 429 + Retry-After", n429 >= 40 and any("retry-after" in {k.lower() for k in r[2]} for r in rl if r[0] == 429), n429)

    time.sleep(11)
    check("rate limit recovers after 11s", call("GET", "/api/v1/ping")[0] == 200)

    # ---- offline sync
    call("POST", "/audit/v1/reset")
    call("POST", "/audit/v1/leagues", {"league_id": "lgs", "sport_id": "football", "teams": ["t1", "t2"],
                                       "fixtures": [{"match_id": "ms", "home": "t1", "away": "t2"}], "qualification": {"spots": 1}})
    call("POST", "/audit/v1/events", ev("s1", "match_start", {}, "ms"))
    sync = {"device_id": "dev-1", "actions": [
        {"action_id": "a2", "type": "score_event", "queued_at": "2026-10-17T11:01:00Z", "base_version": 1,
         "payload": ev("s3", "score", {"team_id": "t2", "event_type": "goal"}, "ms")},
        {"action_id": "a1", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 1,
         "payload": ev("s2", "score", {"team_id": "t1", "event_type": "goal"}, "ms")},
        {"action_id": "a3", "type": "score_event", "queued_at": "2026-10-17T11:02:00Z", "base_version": 99,
         "payload": ev("s4", "score", {"team_id": "t1", "event_type": "goal"}, "ms")},
        {"action_id": "a4", "type": "score_event", "queued_at": "2026-10-17T11:03:00Z", "base_version": 0,
         "payload": ev("s5", "score", {"team_id": "t1", "event_type": "goal"}, "nomatch")}]}
    r = call("POST", "/audit/v1/offline-sync", sync)[1]
    res = r["results"]
    check("sync a2 rebased (processed 2nd)", res[0]["resolution"] == "rebased_append" and res[0]["processed_order"] == 2, res[0])
    check("sync a1 appended (processed 1st)", res[1]["resolution"] == "appended" and res[1]["server_version"] == 2, res[1])
    check("sync a3 invalid base", res[2]["error_code"] == "INVALID_BASE_VERSION", res[2])
    check("sync a4 not found", res[3]["error_code"] == "MATCH_NOT_FOUND", res[3])
    r2 = call("POST", "/audit/v1/offline-sync", sync)[1]
    check("sync resend all duplicate", r2["summary"] == {"applied": 0, "rejected": 0, "duplicate": 4}, r2["summary"])

    # ---- mobile API
    s, lg, _ = call("POST", "/api/v1/auth/login", {"email": "manager@nascon.test", "password": "Nascon@26"})
    check("login", s == 200 and lg["role"] == "club_manager", lg)

    print(f"\n{len(FAILS)} failure(s)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
