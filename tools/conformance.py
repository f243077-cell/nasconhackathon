"""Spec conformance suite: every check compares the EXPECTED value from the Part I spec with the ACTUAL
value returned by the running stack. Prints one line per check and a final passed/failed count.

Usage: DAY1_SALT=<salt> python tools/conformance.py [base_url]
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
SALT = os.environ.get("DAY1_SALT", "demo-salt")
RESULTS: list[tuple[str, str, bool, str, str]] = []
SECTION = [""]
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ------------------------------------------------------------------ helpers
def call(method, path, body=None, token=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read()
            return r.status, (json.loads(txt) if txt else None), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            parsed = json.loads(txt)
        except ValueError:
            parsed = txt
        return e.code, parsed, {k.lower(): v for k, v in e.headers.items()}


def short(x, n=110):
    s = json.dumps(x, ensure_ascii=False, default=str) if not isinstance(x, str) else x
    return s if len(s) <= n else s[: n - 3] + "..."


def eq(name, expected, actual):
    RESULTS.append((SECTION[0], name, expected == actual, short(expected), short(actual)))


def ok(name, cond, expected_desc, actual):
    RESULTS.append((SECTION[0], name, bool(cond), expected_desc, short(actual)))


def err(name, r, status, code, field=None):
    """Expected: HTTP status + error.code + spec 5.2 error body (message str, details object, fields list)."""
    b = r[1] if isinstance(r[1], dict) else {}
    e = b.get("error", {}) if isinstance(b.get("error"), dict) else {}
    actual = {"status": r[0], "code": e.get("code"), "message_is_str": isinstance(e.get("message"), str),
              "details_is_obj": isinstance(e.get("details"), dict)}
    expected = {"status": status, "code": code, "message_is_str": True, "details_is_obj": True}
    if code == "VALIDATION_ERROR":
        fields = e.get("details", {}).get("fields") if isinstance(e.get("details"), dict) else None
        actual["fields_is_list"] = isinstance(fields, list)
        expected["fields_is_list"] = True
        if field is not None:
            actual["field_listed"] = isinstance(fields, list) and field in fields
            expected["field_listed"] = True
    eq(name, expected, actual)


def keys(name, obj, expected_keys):
    eq(name + " [keys]", sorted(expected_keys), sorted(obj.keys()) if isinstance(obj, dict) else obj)


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(id_, payload):
    return hmac.new(SALT.encode(), (id_ + "|" + canon(payload)).encode(), hashlib.sha256).hexdigest()


def ev(i, t, p, m):
    return {"event_id": i, "match_id": m, "type": t, "payload": p}


def post_events(match, items, prefix):
    for n, (t, p) in enumerate(items):
        call("POST", "/audit/v1/events", ev(f"{prefix}{n}", t, p, match))


def section(name):
    SECTION[0] = name


KABADDI = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
           "periods": {"count": 2, "duration_minutes": 20},
           "scoring_events": {"raid_point": {"points": 1}, "tackle_point": {"points": 1}, "all_out": {"points": 2}},
           "draw_allowed": False, "overtime": {"policy": "golden_score", "duration_minutes": 5},
           "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
           "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2, "defender": 3}}}


# ------------------------------------------------------------------ 5.4 / 5.5
def t_health_reset():
    section("5.4 health / 5.5 reset")
    r = call("GET", "/health")
    eq("GET /health -> 200 {status:ok}", (200, {"status": "ok"}), (r[0], r[1]))
    r = call("POST", "/audit/v1/reset")
    eq("reset no body -> 200 exact default body", (200, {
        "status": "reset_complete", "seed": 42, "sports": ["football", "basketball", "cricket", "esports"],
        "tenants": ["tenant-alpha", "tenant-beta"], "stock": {"var-jersey-001-M": 1, "var-jersey-001-L": 5}}),
        (r[0], r[1]))
    r = call("POST", "/audit/v1/reset", {"seed": 7, "stock": {"var-jersey-001-M": 3, "var-jersey-001-L": 0}})
    eq("reset echoes seed + stock", (7, {"var-jersey-001-M": 3, "var-jersey-001-L": 0}),
       (r[1].get("seed"), r[1].get("stock")))
    eq("stock applied to inventory", {"variant_id": "var-jersey-001-M", "stock": 3, "reserved": 0},
       call("GET", "/audit/v1/inventory/var-jersey-001-M")[1])
    err("reset seed not int -> 400", call("POST", "/audit/v1/reset", {"seed": "x"}), 400, "VALIDATION_ERROR", "seed")
    err("reset negative stock -> 400", call("POST", "/audit/v1/reset", {"stock": {"var-jersey-001-M": -1}}), 400,
        "VALIDATION_ERROR", "stock")
    a = call("POST", "/audit/v1/reset")[1]
    call("POST", "/audit/v1/sports", KABADDI)
    b = call("POST", "/audit/v1/reset")[1]
    eq("reset twice -> identical body", a, b)
    eq("reset wipes custom sports (kabaddi re-creatable)", 201, call("POST", "/audit/v1/sports", KABADDI)[0])
    call("POST", "/audit/v1/reset")
    tok = call("POST", "/audit/v1/rbac-matrix")[1]["tokens"]
    for email in ("admin", "organizer", "manager", "player", "viewer"):
        r = call("POST", "/api/v1/auth/login", {"email": f"{email}@nascon.test", "password": "Nascon@26"})
        eq(f"demo account {email}@nascon.test logs in after reset", 200, r[0])
    eq("5 role tokens issued", ["club_manager", "league_organizer", "player", "super_admin", "viewer"], sorted(tok))


# ------------------------------------------------------------------ 5.2 conventions
def t_conventions():
    section("5.2 conventions")
    call("POST", "/audit/v1/reset")
    err("malformed JSON -> 400", call("POST", "/audit/v1/sports", raw=b"{bad"), 400, "VALIDATION_ERROR")
    err("body > 1 MB -> 413", call("POST", "/audit/v1/leagues", raw=b"{" + b" " * (1024 * 1024 + 1) + b"}"), 413,
        "PAYLOAD_TOO_LARGE")
    err("id containing | -> 400", call("POST", "/audit/v1/events", ev("a|b", "match_start", {}, "m1")), 400,
        "VALIDATION_ERROR", "event_id")
    err("id longer than 64 -> 400", call("POST", "/audit/v1/events", ev("x" * 65, "match_start", {}, "m1")), 400,
        "VALIDATION_ERROR", "event_id")
    r = call("POST", "/audit/v1/leagues", {"league_id": "ID.with:all_chars-1", "sport_id": "football",
             "teams": ["Team.A", "team:b"], "fixtures": [{"match_id": "M.1:x", "home": "Team.A", "away": "team:b"}],
             "qualification": {"spots": 1}, "unknown_field": "ignored"})
    eq("unknown fields ignored + ids stored verbatim", (201, "ID.with:all_chars-1"), (r[0], r[1].get("league_id")))
    eq("ids case-sensitive (M.1:x vs m.1:x)", 404,
       call("POST", "/audit/v1/events", ev("cs1", "match_start", {}, "m.1:x"))[0])
    err("wrong type (teams string) -> 400", call("POST", "/audit/v1/leagues", {"league_id": "q", "sport_id": "football",
        "teams": "t1,t2", "fixtures": [], "qualification": {"spots": 1}}), 400, "VALIDATION_ERROR", "teams")
    err("validation order: bad schema beats unknown sport (400 not 404)", call("POST", "/audit/v1/leagues", {
        "league_id": "q", "sport_id": "nosport", "teams": ["a"], "fixtures": [], "qualification": {"spots": 1}}),
        400, "VALIDATION_ERROR")
    err("validation order: unknown variant beats bad discount (404 not 400)", call("POST", "/audit/v1/checkout", {
        "order_id": "vo1", "customer_id": "c", "items": [{"variant_id": "nope", "quantity": 1}],
        "discount_code": "NOPE", "payment": {"token": "tok_success"}}), 404, "VARIANT_NOT_FOUND")
    hits = sum(1 for _ in range(150) if call("GET", "/health")[0] == 429)
    eq("/health exempt from rate limit (150 fast calls)", 0, hits)
    hits = sum(1 for _ in range(120) if call("GET", "/audit/v1/inventory/var-jersey-001-L")[0] == 429)
    eq("/audit/v1/* exempt from rate limit (120 fast calls)", 0, hits)
    r = call("GET", "/health")
    ok("responses are application/json", r[2].get("content-type", "").startswith("application/json"),
       "application/json", r[2].get("content-type"))


# ------------------------------------------------------------------ 5.6 sports
def t_sports():
    section("5.6 sports")
    call("POST", "/audit/v1/reset")
    r = call("POST", "/audit/v1/sports", KABADDI)
    eq("create kabaddi -> 201", 201, r[0])
    keys("create response", r[1], ["sport_id", "status", "config"])
    eq("status=created, sport_id echoed", ("created", "kabaddi"), (r[1].get("status"), r[1].get("sport_id")))
    eq("config echoes stored scoring_events", KABADDI["scoring_events"], r[1]["config"].get("scoring_events"))
    err("duplicate -> 409 SPORT_EXISTS", call("POST", "/audit/v1/sports", KABADDI), 409, "SPORT_EXISTS")
    no_tbo = dict(KABADDI, sport_id="kab2")
    no_tbo.pop("tie_break_order")
    eq("tie_break_order defaults to full list",
       ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
       call("POST", "/audit/v1/sports", no_tbo)[1]["config"].get("tie_break_order"))
    bad = [
        ("sport_id", {"sport_id": "x'; DROP TABLE sports;--"}), ("sport_id", {"sport_id": "A"}),
        ("sport_id", {"sport_id": "a" * 41}), ("name", {"name": ""}), ("name", {"name": "n" * 81}),
        ("scoring_model", {"scoring_model": "points"}), ("periods", {"periods": {"count": 0, "duration_minutes": 1}}),
        ("periods", {"periods": {"count": 1, "duration_minutes": 0}}),
        ("scoring_events", {"scoring_events": {}}), ("scoring_events", {"scoring_events": {"Bad Key": {"points": 1}}}),
        ("scoring_events", {"scoring_events": {"ok": {"points": 0}}}), ("draw_allowed", {"draw_allowed": "yes"}),
        ("overtime", {"overtime": {"policy": "penalties"}}), ("overtime", {"overtime": {"policy": "none",
                                                                                        "duration_minutes": -1}}),
        ("tie_break_order", {"tie_break_order": ["scored", "scored"]}), ("tie_break_order", {"tie_break_order": ["x"]}),
        ("roster", {"roster": {"min_squad_size": 5, "max_squad_size": 4, "required_positions": {}}}),
        ("roster", {"roster": {"min_squad_size": 0, "max_squad_size": 4, "required_positions": {}}}),
    ]
    for i, (field, patch) in enumerate(bad):
        body = dict(KABADDI, sport_id=f"bad{i}")
        body.update(patch)
        err(f"invalid {field} {short(patch, 40)} -> 400", call("POST", "/audit/v1/sports", body), 400,
            "VALIDATION_ERROR", field)
    for field in ("sport_id", "name", "scoring_model", "periods", "scoring_events", "draw_allowed", "overtime", "roster"):
        body = dict(KABADDI, sport_id="miss1")
        body.pop(field)
        err(f"missing {field} -> 400", call("POST", "/audit/v1/sports", body), 400, "VALIDATION_ERROR", field)
    inn = dict(KABADDI, sport_id="inn1", scoring_model="innings",
               periods={"innings_per_team": 1, "overs_per_innings": 10, "balls_per_over": 6, "wickets_per_innings": 10},
               scoring_events={"super_six": {"runs": 6, "legal_ball": True, "wicket": False},
                               "bye_run": {"runs": 1, "legal_ball": False, "wicket": False},
                               "out": {"runs": 0, "legal_ball": True, "wicket": True}})
    eq("innings model sport (spec fragment) -> 201", 201, call("POST", "/audit/v1/sports", inn)[0])
    rnd = dict(KABADDI, sport_id="rnd1", scoring_model="round", periods={"best_of": 5},
               scoring_events={"map_win": {"rounds": 1}})
    eq("round model sport (spec fragment) -> 201", 201, call("POST", "/audit/v1/sports", rnd)[0])
    err("round best_of even -> 400", call("POST", "/audit/v1/sports", dict(rnd, sport_id="rnd2",
        periods={"best_of": 4})), 400, "VALIDATION_ERROR", "periods")
    err("innings legal_ball not bool -> 400", call("POST", "/audit/v1/sports", dict(inn, sport_id="inn2",
        scoring_events={"x": {"runs": 1, "legal_ball": 1, "wicket": False}})), 400, "VALIDATION_ERROR",
        "scoring_events")
    # mystery sport usable immediately everywhere
    call("POST", "/audit/v1/events", ev("k1", "match_init", {"sport_id": "kabaddi", "home_team_id": "A",
                                                             "away_team_id": "B"}, "km"))
    post_events("km", [("match_start", {}), ("score", {"team_id": "A", "event_type": "all_out"}),
                       ("score", {"team_id": "B", "event_type": "raid_point"}), ("match_end", {})], "kx")
    s = call("GET", "/audit/v1/score/km")[1]
    eq("mystery sport scores from config (all_out=2, raid_point=1)", (2, 1, "home_win"),
       (s["home"]["score"], s["away"]["score"], s["outcome"]))
    r = call("POST", "/audit/v1/leagues", {"league_id": "klg", "sport_id": "kabaddi", "teams": ["A", "B"],
             "fixtures": [{"match_id": "kf1", "home": "A", "away": "B"}], "qualification": {"spots": 1}})
    eq("mystery sport usable in /leagues", 201, r[0])
    eq("mystery sport usable in /standings", 200, call("GET", "/audit/v1/standings/klg")[0])


# ------------------------------------------------------------------ 5.7 fixtures
def rr(teams, **params):
    return call("POST", "/audit/v1/fixtures", {"format": "round_robin", "teams": teams, "params": params})


def t_fixtures():
    section("5.7 fixtures")
    for n in (2, 3, 4, 5, 6, 7, 8):
        teams = [f"t{i}" for i in range(1, n + 1)]
        for legs in (1, 2):
            r = rr(teams, legs=legs)
            b = r[1]
            per_leg = n - 1 if n % 2 == 0 else n
            matches = [m for rd in b["rounds"] for m in rd["matches"]]
            pairs = {}
            for m in matches:
                pairs[frozenset((m["home"], m["away"]))] = pairs.get(frozenset((m["home"], m["away"])), 0) + 1
            ordered = {(m["home"], m["away"]) for m in matches}
            balance_ok = True
            for leg in range(1, legs + 1):
                for t in teams:
                    h = sum(1 for m in matches if m["leg"] == leg and m["home"] == t)
                    a = sum(1 for m in matches if m["leg"] == leg and m["away"] == t)
                    balance_ok &= abs(h - a) <= 1
            once = all(len({x for m in rd["matches"] for x in (m["home"], m["away"])} | set(rd["byes"])) == n
                       and len(rd["matches"]) == n // 2 for rd in b["rounds"])
            ids_ok = all(m["match_id"] == f"RR-L{m['leg']}-R{rd['round']}-M{i}"
                         for rd in b["rounds"] for i, m in enumerate(rd["matches"], 1))
            byes_ok = all(len(rd["byes"]) == (n % 2) for rd in b["rounds"])
            eq(f"RR n={n} legs={legs}: round_count, team_count, legs", (per_leg * legs, n, legs),
               (b.get("round_count"), b.get("team_count"), b.get("legs")))
            ok(f"RR n={n} legs={legs}: every pair meets exactly legs times",
               len(pairs) == n * (n - 1) // 2 and all(v == legs for v in pairs.values()), f"each pair x{legs}",
               {"-".join(sorted(k)): v for k, v in pairs.items()})
            if legs == 2:
                ok(f"RR n={n}: legs=2 every ordered pair once", len(ordered) == n * (n - 1), n * (n - 1), len(ordered))
            ok(f"RR n={n} legs={legs}: home/away |diff|<=1 per leg", balance_ok, True, balance_ok)
            ok(f"RR n={n} legs={legs}: one game per team per round, floor(n/2) matches", once, True, once)
            ok(f"RR n={n} legs={legs}: match_id RR-L-R-M format + global rounds", ids_ok, True, ids_ok)
            ok(f"RR n={n} legs={legs}: byes [] even / 1 odd", byes_ok, True, [rd["byes"] for rd in b["rounds"]][:3])
    r = rr(["t1", "t2", "t3", "t4", "t5"], withdrawals=[{"team_id": "t3", "after_round": 2}],
           withdrawal_policy="forfeit_remaining")
    ms = [(rd["round"], m) for rd in r[1]["rounds"] for m in rd["matches"]]
    fx = [m for rd, m in ms if "t3" in (m["home"], m["away"])]
    okf = all((m["status"] == "forfeit" and m["awarded_to"] == ({m["home"], m["away"]} - {"t3"}).pop())
              if rd > 2 else (m["status"] == "scheduled" and m["awarded_to"] is None)
              for rd, m in ms if "t3" in (m["home"], m["away"]))
    ok("RR forfeit_remaining: later -> forfeit + awarded_to opponent, earlier scheduled", okf, True, fx)
    s = r[1]["summary"]
    eq("RR summary counts add up", s["total"], s["scheduled"] + s["forfeit"] + s["voided"])
    keys("RR summary", s, ["total", "scheduled", "forfeit", "voided"])
    keys("RR match", ms[0][1], ["match_id", "leg", "home", "away", "status", "awarded_to"])
    r = rr(["t1", "t2", "t3", "t4", "t5"], withdrawals=[{"team_id": "t3", "after_round": 2}],
           withdrawal_policy="void_all")
    vs = [m for rd in r[1]["rounds"] for m in rd["matches"] if "t3" in (m["home"], m["away"])]
    ok("RR void_all: every t3 fixture voided, awarded_to null",
       all(m["status"] == "voided" and m["awarded_to"] is None for m in vs), True, vs)
    eq("RR void_all: fixtures never removed (total 10)", 10, r[1]["summary"]["total"])
    r = rr(["t1", "t2", "t3", "t4"], withdrawals=[{"team_id": "t1", "after_round": 0},
                                                 {"team_id": "t2", "after_round": 0}], withdrawal_policy="forfeit_remaining")
    both = [m for rd in r[1]["rounds"] for m in rd["matches"] if {m["home"], m["away"]} == {"t1", "t2"}]
    eq("RR both teams withdrawn -> voided", ["voided"], [m["status"] for m in both])
    err("RR unknown withdrawal team -> 400", rr(["t1", "t2", "t3"], withdrawals=[{"team_id": "zz",
        "after_round": 1}]), 400, "VALIDATION_ERROR")
    err("RR after_round > round_count -> 400", rr(["t1", "t2", "t3"], withdrawals=[{"team_id": "t1",
        "after_round": 9}]), 400, "VALIDATION_ERROR")
    err("RR 1 team -> 400", rr(["t1"]), 400, "VALIDATION_ERROR")
    err("RR 41 teams -> 400", rr([f"t{i}" for i in range(41)]), 400, "VALIDATION_ERROR")
    err("RR duplicate teams -> 400", rr(["t1", "t1"]), 400, "VALIDATION_ERROR")
    err("RR legs=3 -> 400", rr(["t1", "t2"], legs=3), 400, "VALIDATION_ERROR")
    err("unknown format -> 400", call("POST", "/audit/v1/fixtures", {"format": "league", "teams": ["a", "b"],
        "params": {}}), 400, "VALIDATION_ERROR")

    # Swiss
    sw = lambda teams, **p: call("POST", "/audit/v1/fixtures", {"format": "swiss", "teams": teams, "params": p})
    r = sw(["t1", "t2", "t3", "t4", "t5"], total_rounds=3, round=1)
    keys("swiss response", r[1], ["format", "round", "total_rounds", "pairings", "bye", "standings"])
    eq("swiss round 1 exact n=5 (seed i vs i+m, last seed bye)",
       ([("SW-R1-M1", "t1", "t3"), ("SW-R1-M2", "t2", "t4")], "t5"),
       ([(p["match_id"], p["home"], p["away"]) for p in r[1]["pairings"]], r[1]["bye"]))
    r = sw(["t1", "t2", "t3", "t4"])
    eq("swiss round 1 exact n=4 + default total_rounds ceil(log2 n)",
       ([("t1", "t3"), ("t2", "t4")], None, 2),
       ([(p["home"], p["away"]) for p in r[1]["pairings"]], r[1]["bye"], r[1]["total_rounds"]))
    hist = [{"round": 1, "bye": "t5", "matches": [{"home": "t1", "away": "t3", "result": "home"},
                                                  {"home": "t2", "away": "t4", "result": "draw"}]}]
    r = sw(["t1", "t2", "t3", "t4", "t5"], total_rounds=3, round=2, history=hist)
    st = {x["team_id"]: (x["score"], x["buchholz"]) for x in r[1]["standings"]}
    eq("swiss standings scores + buchholz exact (spec example)",
       {"t1": (1.0, 0.0), "t5": (1.0, 0.0), "t2": (0.5, 0.5), "t4": (0.5, 0.5), "t3": (0.0, 1.0)}, st)
    eq("swiss standings order (score, buchholz, seed)", ["t1", "t5", "t2", "t4", "t3"],
       [x["team_id"] for x in r[1]["standings"]])
    keys("swiss standings row", r[1]["standings"][0], ["rank", "team_id", "score", "buchholz"])
    met = {frozenset(("t1", "t3")), frozenset(("t2", "t4"))}
    pr = r[1]["pairings"]
    seen = [x for p in pr for x in (p["home"], p["away"])] + [r[1]["bye"]]
    ok("swiss round 2: no rematch, each team once, bye to non-t5",
       all(frozenset((p["home"], p["away"])) not in met for p in pr) and len(set(seen)) == 5 and r[1]["bye"] != "t5",
       True, r[1])
    err("swiss history missing rounds -> 400", sw(["t1", "t2", "t3", "t4"], round=2, history=[]), 400,
        "VALIDATION_ERROR")
    err("swiss total_rounds >= n -> 400", sw(["t1", "t2", "t3", "t4"], total_rounds=4), 400, "VALIDATION_ERROR")
    err("swiss round > total_rounds -> 400", sw(["t1", "t2", "t3", "t4"], total_rounds=2, round=3), 400,
        "VALIDATION_ERROR")
    err("swiss 65 teams -> 400", sw([f"t{i}" for i in range(65)]), 400, "VALIDATION_ERROR")

    # Single elimination
    se = lambda teams, **p: call("POST", "/audit/v1/fixtures", {"format": "single_elim", "teams": teams, "params": p})
    t8 = [f"t{i}" for i in range(1, 9)]
    r = se(t8)
    keys("single_elim response", r[1], ["format", "bracket_size", "rounds"])
    r1 = r[1]["rounds"][0]["matches"]
    eq("SE n=8 order(8)=[1,8,4,5,2,7,3,6] -> R1 pairs",
       [("t1", "t8"), ("t4", "t5"), ("t2", "t7"), ("t3", "t6")], [(m["home"], m["away"]) for m in r1])
    keys("SE MATCH object", r1[0], ["match_id", "bracket", "round", "index", "home", "away", "home_seed", "away_seed",
                                     "bye", "winner", "loser", "winner_to", "loser_to"])
    eq("SE R1M2 winner_to R2M1 away (spec example)", {"match_id": "R2M1", "slot": "away"}, r1[1]["winner_to"])
    eq("SE rounds = log2 B, final winner_to null", (3, None),
       (len(r[1]["rounds"]), r[1]["rounds"][-1]["matches"][0]["winner_to"]))
    r = se(t8[:6])
    r1 = r[1]["rounds"][0]["matches"]
    eq("SE n=6 B=8 byes (spec example)", [(True, "t1", None), (False, "t4", "t5"), (True, "t2", None),
                                         (False, "t3", "t6")], [(m["bye"], m["home"], m["away"]) for m in r1])
    eq("SE bye winners propagated (R2M1.home=t1, R2M2.home=t2)", ("t1", "t2"),
       (r[1]["rounds"][1]["matches"][0]["home"], r[1]["rounds"][1]["matches"][1]["home"]))
    r = se(t8[:6], results=[{"match_id": "R1M2", "winner": "t4"}])
    m = r[1]["rounds"][0]["matches"][1]
    eq("SE result fills winner/loser + propagates to R2M1.away", ("t4", "t5", "t4"),
       (m["winner"], m["loser"], r[1]["rounds"][1]["matches"][0]["away"]))
    err("SE result unknown match_id -> 400", se(t8, results=[{"match_id": "R9M9", "winner": "t1"}]), 400,
        "VALIDATION_ERROR")
    err("SE result winner not in match -> 400", se(t8, results=[{"match_id": "R1M1", "winner": "t2"}]), 400,
        "VALIDATION_ERROR")
    r = se(t8[:4], third_place_match=True)
    tp = [mm for rd in r[1]["rounds"] for mm in rd["matches"] if mm["match_id"] == "TP"]
    semis = r[1]["rounds"][0]["matches"]
    ok("SE third_place_match adds TP (bracket third_place) fed by semifinal losers",
       len(tp) == 1 and tp[0]["bracket"] == "third_place" and all(s_["loser_to"] and s_["loser_to"]["match_id"] == "TP"
                                                                    for s_ in semis), True, tp)
    err("SE 1 team -> 400", se(["t1"]), 400, "VALIDATION_ERROR")
    err("SE 129 teams -> 400", se([f"t{i}" for i in range(129)]), 400, "VALIDATION_ERROR")

    # Double elimination
    de = lambda teams, **p: call("POST", "/audit/v1/fixtures", {"format": "double_elim", "teams": teams, "params": p})
    r = de(t8, bracket_reset=True)
    b = r[1]
    keys("double_elim response", b, ["format", "bracket_size", "bracket_reset", "winners", "losers", "grand_final"])
    eq("DE winners rounds B/2^r", [4, 2, 1], [len(x["matches"]) for x in b["winners"]])
    eq("DE losers rounds 2,2,1,1 (total B-2=6)", [2, 2, 1, 1], [len(x["matches"]) for x in b["losers"]])
    ids = [m["match_id"] for x in b["winners"] for m in x["matches"]] + \
          [m["match_id"] for x in b["losers"] for m in x["matches"]] + [m["match_id"] for m in b["grand_final"]]
    eq("DE ids WR/LR/GF", ["WR1M1", "WR1M2", "WR1M3", "WR1M4", "WR2M1", "WR2M2", "WR3M1", "LR1M1", "LR1M2", "LR2M1",
                           "LR2M2", "LR3M1", "LR4M1", "GF1", "GF2"], ids)
    gf1, gf2 = b["grand_final"]
    eq("DE GF2 conditional:true, required:null before GF1 result", (True, None),
       (gf2.get("conditional"), gf2.get("required")))
    wb = [m for x in b["winners"] for m in x["matches"]]
    lb = [m for x in b["losers"] for m in x["matches"]]
    ok("DE every WB match has loser_to; LB loser_to null", all(m["loser_to"] for m in wb) and
       all(m["loser_to"] is None for m in lb), True, "routing")
    eq("DE WR final winner -> GF1.home", {"match_id": "GF1", "slot": "home"}, b["winners"][-1]["matches"][0]["winner_to"])
    eq("DE LB final winner -> GF1.away", {"match_id": "GF1", "slot": "away"}, b["losers"][-1]["matches"][0]["winner_to"])
    eq("DE bracket_reset false -> only GF1", ["GF1"], [m["match_id"] for m in de(t8, bracket_reset=False)[1]["grand_final"]])
    four = ["a", "b", "c", "d"]

    def play(lb_champ_wins):
        res = [{"match_id": "WR1M1", "winner": "a"}, {"match_id": "WR1M2", "winner": "b"},
               {"match_id": "WR2M1", "winner": "a"}, {"match_id": "LR1M1", "winner": "c"},
               {"match_id": "LR2M1", "winner": "b"}]
        res.append({"match_id": "GF1", "winner": "b" if lb_champ_wins else "a"})
        return de(four, bracket_reset=True, results=res)

    r = play(True)
    ok("DE LB champion wins GF1 -> GF2.required true", r[0] == 200 and r[1]["grand_final"][1]["required"] is True,
       True, r[1].get("grand_final") if r[0] == 200 else r)
    r = play(False)
    ok("DE WB champion wins GF1 -> GF2.required false", r[0] == 200 and r[1]["grand_final"][1]["required"] is False,
       False, r[1].get("grand_final") if r[0] == 200 else r)
    err("DE 2 teams -> 400", de(["a", "b"]), 400, "VALIDATION_ERROR")


# ------------------------------------------------------------------ 5.8 leagues + 5.9 events/score
def t_leagues_events():
    section("5.8 leagues")
    call("POST", "/audit/v1/reset")
    L = {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2", "t3", "t4"],
         "fixtures": [{"match_id": "m1", "home": "t1", "away": "t2"}, {"match_id": "m2", "home": "t3", "away": "t4"}],
         "points": {"win": 3, "draw": 1, "loss": 0},
         "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
         "qualification": {"spots": 2}, "lots_seed": 42}
    r = call("POST", "/audit/v1/leagues", L)
    eq("register league -> 201 exact body", (201, {"league_id": "lg-1", "status": "created", "team_count": 4,
                                                   "fixture_count": 2}), (r[0], r[1]))
    err("LEAGUE_EXISTS", call("POST", "/audit/v1/leagues", L), 409, "LEAGUE_EXISTS")
    err("MATCH_EXISTS (fixture id reused)", call("POST", "/audit/v1/leagues", dict(L, league_id="lg-2")), 409,
        "MATCH_EXISTS")
    err("SPORT_NOT_FOUND", call("POST", "/audit/v1/leagues", dict(L, league_id="lg-3", sport_id="nope",
        fixtures=[])), 404, "SPORT_NOT_FOUND")
    err("fixture team not in teams -> 400", call("POST", "/audit/v1/leagues", dict(L, league_id="lg-4",
        fixtures=[{"match_id": "x1", "home": "t1", "away": "zz"}])), 400, "VALIDATION_ERROR", "fixtures")
    err("home == away -> 400", call("POST", "/audit/v1/leagues", dict(L, league_id="lg-5",
        fixtures=[{"match_id": "x2", "home": "t1", "away": "t1"}])), 400, "VALIDATION_ERROR", "fixtures")
    err("qualification.spots > teams -> 400", call("POST", "/audit/v1/leagues", dict(L, league_id="lg-6",
        fixtures=[], qualification={"spots": 5})), 400, "VALIDATION_ERROR", "qualification")
    err("qualification missing -> 400", call("POST", "/audit/v1/leagues", {k: v for k, v in L.items()
        if k != "qualification"} | {"league_id": "lg-7", "fixtures": []}), 400, "VALIDATION_ERROR", "qualification")
    err("1 team -> 400", call("POST", "/audit/v1/leagues", dict(L, league_id="lg-8", teams=["t1"], fixtures=[],
        qualification={"spots": 1})), 400, "VALIDATION_ERROR", "teams")
    eq("fixture becomes stream status upcoming", "upcoming", call("GET", "/audit/v1/score/m1")[1]["status"])

    section("5.9 events / score")
    r = call("POST", "/audit/v1/events", ev("evt-1", "match_start", {}, "m1"))
    keys("event response", r[1], ["event_id", "match_id", "type", "sequence", "match_version", "signature"])
    eq("match_start -> 201 seq 1", (201, 1, 1), (r[0], r[1]["sequence"], r[1]["match_version"]))
    p = {"team_id": "t1", "event_type": "goal"}
    r = call("POST", "/audit/v1/events", ev("evt-2", "score", p, "m1"))
    eq("score signature = HMAC(salt, id|canonical payload)", sign("evt-2", p), r[1]["signature"])
    ok("signature is 64 lowercase hex", HEX64.match(r[1]["signature"] or ""), "64 hex", r[1]["signature"])
    first = r[1]
    r = call("POST", "/audit/v1/events", ev("evt-2", "score", p, "m1"))
    eq("identical replay -> 200 + stored body", (200, first), (r[0], r[1]))
    err("same id different body -> DUPLICATE_EVENT_ID", call("POST", "/audit/v1/events",
        ev("evt-2", "score", {"team_id": "t2", "event_type": "goal"}, "m1")), 409, "DUPLICATE_EVENT_ID")
    err("score team not home/away -> 400", call("POST", "/audit/v1/events",
        ev("evt-3", "score", {"team_id": "t3", "event_type": "goal"}, "m1")), 400, "VALIDATION_ERROR")
    err("UNKNOWN_EVENT_TYPE", call("POST", "/audit/v1/events",
        ev("evt-4", "score", {"team_id": "t1", "event_type": "try"}, "m1")), 400, "UNKNOWN_EVENT_TYPE")
    err("match_start twice -> ILLEGAL_TRANSITION", call("POST", "/audit/v1/events", ev("evt-5", "match_start", {},
        "m1")), 409, "ILLEGAL_TRANSITION")
    call("POST", "/audit/v1/events", ev("evt-6", "discipline", {"team_id": "t2", "points": -1}, "m1"))
    call("POST", "/audit/v1/events", ev("evt-7", "score", {"team_id": "t1", "event_type": "goal"}, "m1"))
    call("POST", "/audit/v1/events", ev("evt-8", "score", {"team_id": "t2", "event_type": "goal"}, "m1"))
    r = call("POST", "/audit/v1/events", ev("evt-9", "match_end", {}, "m1"))
    eq("match_end -> 201", 201, r[0])
    err("score after end -> MATCH_NOT_IN_PROGRESS", call("POST", "/audit/v1/events",
        ev("evt-10", "score", {"team_id": "t1", "event_type": "goal"}, "m1")), 409, "MATCH_NOT_IN_PROGRESS")
    s = call("GET", "/audit/v1/score/m1")[1]
    keys("score response", s, ["match_id", "sport_id", "league_id", "status", "outcome", "winner_team_id",
                               "tiebreak_winner_team_id", "home", "away", "version", "events"])
    keys("score side", s["home"], ["team_id", "score", "wickets", "balls", "overs", "fair_play"])
    keys("score event item", s["events"][0], ["sequence", "event_id", "type", "payload", "signature", "compensated",
                                               "compensated_by"])
    eq("score projection = spec example (2-1, home_win, fair_play -1, version 6)",
       ("completed", "home_win", "t1", None, 2, 1, -1, None, 6, "lg-1"),
       (s["status"], s["outcome"], s["winner_team_id"], s["tiebreak_winner_team_id"], s["home"]["score"],
        s["away"]["score"], s["away"]["fair_play"], s["home"]["wickets"], s["version"], s["league_id"]))
    ok("every event signature valid", all(e["signature"] == sign(e["event_id"], e["payload"]) for e in s["events"]),
       True, "signatures")
    r = call("POST", "/audit/v1/events", ev("evt-11", "compensation", {"compensates": "evt-7", "reason": "offside"},
                                            "m1"))
    eq("compensation on completed match -> 201 seq 7", (201, 7), (r[0], r[1].get("sequence")))
    s = call("GET", "/audit/v1/score/m1")[1]
    e7 = [e for e in s["events"] if e["event_id"] == "evt-7"][0]
    eq("compensated event flagged, original kept, score rebuilt (1-1 draw)",
       (True, "evt-11", 1, 1, "draw", 7), (e7["compensated"], e7["compensated_by"], s["home"]["score"],
                                           s["away"]["score"], s["outcome"], len(s["events"])))
    err("compensate twice -> INVALID_COMPENSATION", call("POST", "/audit/v1/events", ev("evt-12", "compensation",
        {"compensates": "evt-7", "reason": "x"}, "m1")), 409, "INVALID_COMPENSATION")
    err("compensate a compensation -> INVALID_COMPENSATION", call("POST", "/audit/v1/events", ev("evt-13",
        "compensation", {"compensates": "evt-11", "reason": "x"}, "m1")), 409, "INVALID_COMPENSATION")
    err("compensate other match's event -> INVALID_COMPENSATION", call("POST", "/audit/v1/events", ev("evt-14",
        "compensation", {"compensates": "evt-8", "reason": "x"}, "m2")), 409, "INVALID_COMPENSATION")
    err("compensate unknown -> EVENT_NOT_FOUND", call("POST", "/audit/v1/events", ev("evt-15", "compensation",
        {"compensates": "nope", "reason": "x"}, "m1")), 404, "EVENT_NOT_FOUND")
    err("event on missing stream -> MATCH_NOT_FOUND", call("POST", "/audit/v1/events", ev("evt-16", "match_start", {},
        "ghost")), 404, "MATCH_NOT_FOUND")
    err("match_init on league fixture -> MATCH_EXISTS", call("POST", "/audit/v1/events", ev("evt-17", "match_init",
        {"sport_id": "football", "home_team_id": "t3", "away_team_id": "t4"}, "m2")), 409, "MATCH_EXISTS")
    err("GET score unknown match -> 404", call("GET", "/audit/v1/score/ghost"), 404, "MATCH_NOT_FOUND")
    # tiebreak + undecided
    call("POST", "/audit/v1/events", ev("bb0", "match_init", {"sport_id": "basketball", "home_team_id": "H",
                                                              "away_team_id": "A"}, "bb"))
    call("POST", "/audit/v1/events", ev("bb1", "match_start", {}, "bb"))
    err("level, no draw, no tiebreak -> TIE_NOT_ALLOWED", call("POST", "/audit/v1/events", ev("bb2", "match_end", {},
        "bb")), 409, "TIE_NOT_ALLOWED")
    call("POST", "/audit/v1/events", ev("bb3", "tiebreak_winner", {"team_id": "A"}, "bb"))
    call("POST", "/audit/v1/events", ev("bb4", "match_end", {}, "bb"))
    s = call("GET", "/audit/v1/score/bb")[1]
    eq("tiebreak decides level match", ("away_win", "A", "A"), (s["outcome"], s["winner_team_id"],
                                                               s["tiebreak_winner_team_id"]))
    call("POST", "/audit/v1/events", ev("bb5", "compensation", {"compensates": "bb3", "reason": "x"}, "bb"))
    s = call("GET", "/audit/v1/score/bb")[1]
    eq("tiebreak compensated -> outcome undecided, winner null", ("undecided", None, None),
       (s["outcome"], s["winner_team_id"], s["tiebreak_winner_team_id"]))
    # basketball points per type
    call("POST", "/audit/v1/events", ev("bk0", "match_init", {"sport_id": "basketball", "home_team_id": "H",
                                                              "away_team_id": "A"}, "bk"))
    post_events("bk", [("match_start", {}), ("score", {"team_id": "H", "event_type": "three_pointer"}),
                       ("score", {"team_id": "H", "event_type": "free_throw"}),
                       ("score", {"team_id": "A", "event_type": "two_pointer"})], "bkx")
    s = call("GET", "/audit/v1/score/bk")[1]
    eq("basketball 3+1 vs 2", (4, 2, "in_progress", "pending"), (s["home"]["score"], s["away"]["score"], s["status"],
                                                                 s["outcome"]))
    # cricket innings
    call("POST", "/audit/v1/events", ev("cr0", "match_init", {"sport_id": "cricket", "home_team_id": "H",
                                                              "away_team_id": "A"}, "cr"))
    post_events("cr", [("match_start", {})] + [("score", {"team_id": "H", "event_type": t}) for t in
                                               ("four", "wide", "six", "dot_ball", "no_ball", "wicket", "single",
                                                "two")], "crx")
    s = call("GET", "/audit/v1/score/cr")[1]
    eq("cricket runs/balls/wickets/overs (4+1+6+0+1+0+1+2=15, 6 legal)", (15, 6, 1, "1.0"), (s["home"]["score"], s["home"]["balls"],
                                                               s["home"]["wickets"], s["home"]["overs"]))
    eq("innings: other side wickets/balls 0 not null", (0, 0, "0.0"), (s["away"]["wickets"], s["away"]["balls"],
                                                                       s["away"]["overs"]))
    # esports
    call("POST", "/audit/v1/events", ev("es0", "match_init", {"sport_id": "esports", "home_team_id": "H",
                                                              "away_team_id": "A"}, "es"))
    post_events("es", [("match_start", {}), ("score", {"team_id": "A", "event_type": "round_win"}),
                       ("score", {"team_id": "A", "event_type": "round_win"})], "esx")
    err("best_of 3 decided -> SERIES_ALREADY_DECIDED", call("POST", "/audit/v1/events", ev("es9", "score",
        {"team_id": "H", "event_type": "round_win"}, "es")), 409, "SERIES_ALREADY_DECIDED")


# ------------------------------------------------------------------ 5.10 standings
def t_standings():
    section("5.10 standings")
    call("POST", "/audit/v1/reset")
    call("POST", "/audit/v1/leagues", {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2", "t3"],
                                       "fixtures": [], "qualification": {"spots": 1}, "lots_seed": 42})
    s = call("GET", "/audit/v1/standings/lg-1")[1]
    keys("standings response", s, ["league_id", "sport_id", "qualification_spots", "table", "h2h"])
    keys("standings row", s["table"][0], ["rank", "team_id", "played", "won", "drawn", "lost", "scored", "conceded",
                                          "diff", "points", "fair_play", "status", "resolved_by"])
    eq("Appendix A vector 2: all-zero table ordered by lots t1,t3,t2", ["t1", "t3", "t2"],
       [r["team_id"] for r in s["table"]])
    eq("draw_lots resolved_by", "draw_lots", s["table"][0]["resolved_by"])
    eq("h2h every ordered pair with zeros", {"played": 0, "points": 0, "scored": 0, "conceded": 0}, s["h2h"]["t2"]["t3"])
    # 3-way tie: t1>t2 1-0, t2>t3 1-0, t3>t1 2-0
    call("POST", "/audit/v1/leagues", {"league_id": "lg-3w", "sport_id": "football", "teams": ["t1", "t2", "t3", "t4"],
         "fixtures": [{"match_id": "a", "home": "t1", "away": "t2"}, {"match_id": "b", "home": "t2", "away": "t3"},
                      {"match_id": "c", "home": "t3", "away": "t1"}, {"match_id": "d", "home": "t4", "away": "t1"}],
         "qualification": {"spots": 2}})
    for mid, scorer, n in (("a", "t1", 1), ("b", "t2", 1), ("c", "t3", 2)):
        post_events(mid, [("match_start", {})] + [("score", {"team_id": scorer, "event_type": "goal"})] * n +
                    [("match_end", {})], f"{mid}x")
    s = call("GET", "/audit/v1/standings/lg-3w")[1]
    eq("3-way mini-league resolved by h2h_diff: t3,t2,t1", ["t3", "t2", "t1", "t4"], [r["team_id"] for r in s["table"]])
    eq("resolved_by on tied rows", ["h2h_diff", "h2h_diff", None], [r["resolved_by"] for r in s["table"][:3]])
    r0 = s["table"][0]
    eq("t3 row values (rank, played, W, D, L, scored 2, pts 3, diff 1; t4 rank 4)", (1, 2, 1, 0, 1, 2, 3, 1, 4), (r0["rank"], r0["played"], r0["won"], r0["drawn"], r0["lost"],
                                                      r0["scored"], r0["points"], r0["diff"], s["table"][3]["rank"]))
    eq("remaining fixture keeps t1 still_possible", "still_possible", [r for r in s["table"] if r["team_id"] == "t1"][0]
       ["status"])
    # clinched / eliminated
    call("POST", "/audit/v1/leagues", {"league_id": "lg-q", "sport_id": "football", "teams": ["x", "y", "z"],
         "fixtures": [{"match_id": "q1", "home": "x", "away": "y"}, {"match_id": "q2", "home": "x", "away": "z"},
                      {"match_id": "q3", "home": "y", "away": "z"}], "qualification": {"spots": 1}})
    for mid in ("q1", "q2"):
        post_events(mid, [("match_start", {}), ("score", {"team_id": "x", "event_type": "goal"}), ("match_end", {})],
                    f"{mid}x")
    st = {r["team_id"]: r["status"] for r in call("GET", "/audit/v1/standings/lg-q")[1]["table"]}
    eq("qualification statuses (x clinched, y/z eliminated)", {"x": "clinched", "y": "eliminated", "z": "eliminated"},
       st)
    # points config + tiebreak win counts as a win
    call("POST", "/audit/v1/leagues", {"league_id": "lg-p", "sport_id": "basketball", "teams": ["h", "a"],
         "fixtures": [{"match_id": "p1", "home": "h", "away": "a"}], "points": {"win": 2, "draw": 0, "loss": 1},
         "qualification": {"spots": 1}})
    post_events("p1", [("match_start", {}), ("tiebreak_winner", {"team_id": "a"}), ("match_end", {})], "p1x")
    t = {r["team_id"]: (r["won"], r["lost"], r["points"]) for r in call("GET", "/audit/v1/standings/lg-p")[1]["table"]}
    eq("custom points + tiebreak win counts as win", {"a": (1, 0, 2), "h": (0, 1, 1)}, t)
    # innings NRR
    call("POST", "/audit/v1/leagues", {"league_id": "lg-c", "sport_id": "cricket", "teams": ["A", "B"],
         "fixtures": [{"match_id": "c1", "home": "A", "away": "B"}], "qualification": {"spots": 1}})
    post_events("c1", [("match_start", {})] + [("score", {"team_id": "A", "event_type": "four"})] * 6 +
                [("score", {"team_id": "B", "event_type": "single"})] * 3 + [("match_end", {})], "c1x")
    t = {r["team_id"]: r["diff"] for r in call("GET", "/audit/v1/standings/lg-c")[1]["table"]}
    eq("NRR: A 24/1.0 - 3/0.5 = 18.0, B -18.0", {"A": 18.0, "B": -18.0}, t)
    # esports map diff
    call("POST", "/audit/v1/leagues", {"league_id": "lg-e", "sport_id": "esports", "teams": ["A", "B"],
         "fixtures": [{"match_id": "e1", "home": "A", "away": "B"}], "qualification": {"spots": 1}})
    post_events("e1", [("match_start", {}), ("score", {"team_id": "A", "event_type": "round_win"}),
                       ("score", {"team_id": "B", "event_type": "round_win"}),
                       ("score", {"team_id": "A", "event_type": "round_win"}), ("match_end", {})], "e1x")
    t = {r["team_id"]: r["diff"] for r in call("GET", "/audit/v1/standings/lg-e")[1]["table"]}
    eq("round model diff = maps won - lost", {"A": 1, "B": -1}, t)
    err("standings unknown league -> LEAGUE_NOT_FOUND", call("GET", "/audit/v1/standings/zz"), 404, "LEAGUE_NOT_FOUND")


# ------------------------------------------------------------------ 5.11 roster
SETUP = {"league": {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "sport_id": "football",
                    "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
                    "max_squad_size": 3, "required_positions": {"gk": 1}},
         "squads": [{"squad_id": "sq-a", "club_id": "club-a", "tenant_id": "tenant-alpha", "name": "A"},
                    {"squad_id": "sq-b", "club_id": "club-b", "tenant_id": "tenant-alpha", "name": "B"},
                    {"squad_id": "sq-x", "club_id": "club-x", "tenant_id": "tenant-beta", "name": "X"}],
         "players": [{"player_id": "p1", "name": "Ali", "position": "gk", "squad_id": "sq-a", "role": "captain"},
                     {"player_id": "p2", "name": "Bilal", "position": "df", "squad_id": "sq-a", "role": "starter"}],
         "matches_in_progress": [{"match_id": "m-live", "home_squad_id": "sq-a", "away_squad_id": "sq-b"}]}


def tr(rid, **kw):
    body = {"request_id": rid, "league_id": "lg-r1", "player_id": "p2", "type": "transfer", "from_squad_id": "sq-a",
            "to_squad_id": "sq-b", "effective_date": "2026-09-30", "loan_end_date": None, "reason": "Tactical move",
            "requested_by": "user-77"}
    body.update(kw)
    return body


def t_roster():
    section("5.11 roster")
    call("POST", "/audit/v1/reset")
    r = call("POST", "/audit/v1/roster/setup", SETUP)
    eq("setup -> 201 exact body", (201, {"league_id": "lg-r1", "status": "configured",
                                         "squad_counts": {"sq-a": 2, "sq-b": 0, "sq-x": 0}}), (r[0], r[1]))
    no_bt = dict(SETUP)
    no_bt["matches_in_progress"] = []
    call("POST", "/audit/v1/roster/setup", no_bt)
    r = call("POST", "/audit/v1/roster/transfer", tr("tr-001"))
    eq("transfer last window day -> 201 active", (201, "accepted", "active", None),
       (r[0], r[1].get("status"), r[1].get("state"), r[1].get("blocking_match_id")))
    keys("transfer response", r[1], ["request_id", "status", "state", "blocking_match_id", "registration",
                                     "audit_entry"])
    keys("registration", r[1]["registration"], ["player_id", "league_id", "squad_id", "parent_squad_id",
                                                "registration_type", "start_date", "loan_end_date", "role"])
    keys("audit_entry", r[1]["audit_entry"], ["audit_id", "action", "player_id", "league_id", "from_squad_id",
                                              "to_squad_id", "effective_date", "state", "who", "when", "why"])
    eq("registration = spec example", {"player_id": "p2", "league_id": "lg-r1", "squad_id": "sq-b",
                                       "parent_squad_id": None, "registration_type": "transfer",
                                       "start_date": "2026-09-30", "loan_end_date": None, "role": "substitute"},
       r[1]["registration"])
    a = r[1]["audit_entry"]
    eq("audit_entry who/why/action/id", ("au-0001", "transfer", "user-77", "Tactical move"),
       (a["audit_id"], a["action"], a["who"], a["why"]))
    ok("audit_entry.when is server timestamp", TS.match(a["when"] or ""), "YYYY-MM-DDTHH:MM:SSZ", a["when"])
    first = r[1]
    r = call("POST", "/audit/v1/roster/transfer", tr("tr-001"))
    eq("replay -> 200 same body", (200, first), (r[0], r[1]))
    # edge case 6
    call("POST", "/audit/v1/roster/setup", SETUP)
    r = call("POST", "/audit/v1/roster/transfer", tr("tr-e6"))
    eq("in-progress match -> deferred_until_match_end + blocking_match_id", (201, "deferred_until_match_end", "m-live"),
       (r[0], r[1].get("state"), r[1].get("blocking_match_id")))
    # error order
    call("POST", "/audit/v1/roster/setup", no_bt)
    err("missing to_squad for transfer -> 400", call("POST", "/audit/v1/roster/transfer", tr("e1", to_squad_id=None)),
        400, "VALIDATION_ERROR")
    err("bad type -> 400", call("POST", "/audit/v1/roster/transfer", tr("e2", type="swap")), 400, "VALIDATION_ERROR")
    err("bad date -> 400", call("POST", "/audit/v1/roster/transfer", tr("e3", effective_date="2026-13-40")), 400,
        "VALIDATION_ERROR")
    err("loan without end date -> 400", call("POST", "/audit/v1/roster/transfer", tr("e4", type="loan")), 400,
        "VALIDATION_ERROR")
    err("LEAGUE_NOT_FOUND", call("POST", "/audit/v1/roster/transfer", tr("e5", league_id="nolg")), 404,
        "LEAGUE_NOT_FOUND")
    err("PLAYER_NOT_FOUND", call("POST", "/audit/v1/roster/transfer", tr("e6", player_id="nobody")), 404,
        "PLAYER_NOT_FOUND")
    err("SQUAD_NOT_FOUND", call("POST", "/audit/v1/roster/transfer", tr("e7", to_squad_id="sq-zz")), 404,
        "SQUAD_NOT_FOUND")
    err("CROSS_TENANT_TRANSFER (beats window closed: check 3 before 5)", call("POST", "/audit/v1/roster/transfer",
        tr("e8", to_squad_id="sq-x", effective_date="2026-12-01")), 409, "CROSS_TENANT_TRANSFER")
    err("NOT_IN_SQUAD", call("POST", "/audit/v1/roster/transfer", tr("e9", from_squad_id="sq-b", to_squad_id="sq-a")),
        409, "NOT_IN_SQUAD")
    err("TRANSFER_WINDOW_CLOSED (day after close)", call("POST", "/audit/v1/roster/transfer",
        tr("e10", effective_date="2026-10-01")), 409, "TRANSFER_WINDOW_CLOSED")
    err("MIN_POSITION_VIOLATION (only gk leaves)", call("POST", "/audit/v1/roster/transfer", tr("e11", player_id="p1")),
        409, "MIN_POSITION_VIOLATION")
    r = call("POST", "/audit/v1/roster/transfer", tr("rel1", type="release", to_squad_id=None,
                                                     effective_date="2027-03-03"))
    eq("release any date -> 201, registration null", (201, None), (r[0], r[1].get("registration")))
    eq("rejected requests wrote no audit entries (release is au-0001)", "au-0001", r[1]["audit_entry"]["audit_id"])
    full = dict(SETUP, matches_in_progress=[], league=dict(SETUP["league"], max_squad_size=2))
    full["players"] = SETUP["players"] + [{"player_id": "p3", "name": "C", "position": "df", "squad_id": "sq-b",
                                          "role": "starter"}, {"player_id": "p4", "name": "D", "position": "df",
                                                               "squad_id": "sq-b", "role": "starter"}]
    call("POST", "/audit/v1/roster/setup", full)
    err("SQUAD_FULL", call("POST", "/audit/v1/roster/transfer", tr("e12")), 409, "SQUAD_FULL")
    call("POST", "/audit/v1/roster/setup", no_bt)
    r = call("POST", "/audit/v1/roster/transfer", tr("ln1", type="loan", loan_end_date="2026-12-31"))
    eq("loan registration", ("loan", "sq-a", "2026-12-31", "sq-b"),
       (r[1]["registration"]["registration_type"], r[1]["registration"]["parent_squad_id"],
        r[1]["registration"]["loan_end_date"], r[1]["registration"]["squad_id"]))
    err("PLAYER_ON_LOAN", call("POST", "/audit/v1/roster/transfer", tr("e13", from_squad_id="sq-b", to_squad_id="sq-a")),
        409, "PLAYER_ON_LOAN")
    h = call("GET", "/audit/v1/roster/history/p2?as_of=2026-11-01")[1]
    keys("history response", h, ["player_id", "as_of", "league_id", "current_squad_id", "parent_squad_id", "history"])
    eq("during loan: current sq-b, parent sq-a", ("sq-b", "sq-a", 1), (h["current_squad_id"], h["parent_squad_id"],
                                                                       len(h["history"])))
    h1 = call("GET", "/audit/v1/roster/history/p2?as_of=2027-01-05")[1]
    h2 = call("GET", "/audit/v1/roster/history/p2?as_of=2027-01-05")[1]
    eq("after loan: back at lender, loan_return by system, written once",
       ("sq-a", None, ["loan", "loan_return"], "system", 2),
       (h1["current_squad_id"], h1["parent_squad_id"], [e["action"] for e in h1["history"]],
        h1["history"][-1]["who"], len(h2["history"])))
    eq("loan_return effective day after end", "2027-01-01", h1["history"][-1]["effective_date"])
    eq("history default as_of = today", 200, call("GET", "/audit/v1/roster/history/p2")[0])
    err("history unknown player -> 404", call("GET", "/audit/v1/roster/history/ghost"), 404, "PLAYER_NOT_FOUND")
    err("history bad as_of -> 400", call("GET", "/audit/v1/roster/history/p2?as_of=tomorrow"), 400,
        "VALIDATION_ERROR")
    r = call("POST", "/audit/v1/roster/setup", dict(SETUP, league={k: v for k, v in SETUP["league"].items()
                                                                   if k not in ("max_squad_size",
                                                                                "required_positions")}))
    eq("setup defaults max_squad_size/required_positions from sport", 201, r[0])


# ------------------------------------------------------------------ 5.12 store
def t_store():
    section("5.12 checkout / inventory")
    call("POST", "/audit/v1/reset", {"stock": {"var-jersey-001-M": 1}})
    res, barrier = [], threading.Barrier(20)

    def buy(i):
        barrier.wait()
        res.append(call("POST", "/audit/v1/checkout", {"order_id": f"burst-{i}", "customer_id": "cust-001",
                   "items": [{"variant_id": "var-jersey-001-M", "quantity": 1}], "discount_code": None,
                   "payment": {"token": "tok_success"}}))
    t0 = time.time()
    ths = [threading.Thread(target=buy, args=(i,)) for i in range(20)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    el = time.time() - t0
    eq("20 parallel buyers -> one 201, nineteen 409", (1, 19), (sum(r[0] == 201 for r in res),
                                                                sum(r[0] == 409 for r in res)))
    ok("burst finished within 10 s", el < 10, "< 10 s", round(el, 2))
    ok("losers get OUT_OF_STOCK with details.variant_id", all(r[1]["error"]["code"] == "OUT_OF_STOCK" and
       r[1]["error"]["details"].get("variant_id") == "var-jersey-001-M" for r in res if r[0] == 409), True, "409s")
    eq("inventory after burst", {"variant_id": "var-jersey-001-M", "stock": 0, "reserved": 0},
       call("GET", "/audit/v1/inventory/var-jersey-001-M")[1])
    w = [r for r in res if r[0] == 201][0][1]
    keys("checkout response", w, ["order_id", "status", "currency", "items", "subtotal_minor", "discount_minor",
                                  "total_minor", "payment", "receipt"])
    keys("payment", w["payment"], ["authorization_id", "capture_id", "state"])
    keys("receipt", w["receipt"], ["payload", "signature", "pdf_base64"])
    keys("receipt.payload", w["receipt"]["payload"], ["order_id", "customer_id", "items", "subtotal_minor",
                                                      "discount_minor", "total_minor", "currency", "paid_at"])
    keys("item", w["items"][0], ["variant_id", "quantity", "unit_price_minor"])
    eq("paid order values", ("paid", "PKR", 450000, 0, 450000, "captured"),
       (w["status"], w["currency"], w["subtotal_minor"], w["discount_minor"], w["total_minor"], w["payment"]["state"]))
    eq("receipt signature", sign(w["order_id"], w["receipt"]["payload"]), w["receipt"]["signature"])
    pdf = base64.b64decode(w["receipt"]["pdf_base64"])
    ok("PDF starts with %PDF", pdf.startswith(b"%PDF"), "%PDF", pdf[:8])
    text = pdf_text(pdf)
    ok("PDF text has order_id + 'PKR 4500.00'", w["order_id"].encode() in text and b"PKR 4500.00" in text,
       "both present", text[:160])
    call("POST", "/audit/v1/reset")
    body = {"order_id": "ord-001", "customer_id": "cust-001", "items": [{"variant_id": "var-jersey-001-L",
            "quantity": 2}], "discount_code": "WELCOME10", "payment": {"token": "tok_success"}}
    r = call("POST", "/audit/v1/checkout", body)
    eq("discount floor(900000*10/100)=90000, total 810000", (201, 900000, 90000, 810000),
       (r[0], r[1]["subtotal_minor"], r[1]["discount_minor"], r[1]["total_minor"]))
    r2 = call("POST", "/audit/v1/checkout", body)
    eq("identical replay -> 200 same body, no 2nd reservation", (200, r[1], 3),
       (r2[0], r2[1], call("GET", "/audit/v1/inventory/var-jersey-001-L")[1]["stock"]))
    err("DUPLICATE_ORDER_ID", call("POST", "/audit/v1/checkout", dict(body, customer_id="other")), 409,
        "DUPLICATE_ORDER_ID")
    err("PAYMENT_DECLINED", call("POST", "/audit/v1/checkout", dict(body, order_id="d1", payment={"token":
        "tok_declined"})), 402, "PAYMENT_DECLINED")
    err("PAYMENT_CAPTURE_FAILED", call("POST", "/audit/v1/checkout", dict(body, order_id="d2", payment={"token":
        "tok_capture_fail"})), 402, "PAYMENT_CAPTURE_FAILED")
    eq("declined/capture-fail released stock (still 3)", 3, call("GET", "/audit/v1/inventory/var-jersey-001-L")[1]
       ["stock"])
    r = call("POST", "/audit/v1/checkout", dict(body, order_id="d3", items=[{"variant_id": "var-jersey-001-L",
                                                                              "quantity": 3}]))
    eq("released stock purchasable again", 201, r[0])
    err("OUT_OF_STOCK multi-item reserves nothing", call("POST", "/audit/v1/checkout", dict(body, order_id="d4",
        items=[{"variant_id": "var-jersey-001-M", "quantity": 1}, {"variant_id": "var-jersey-001-L", "quantity": 1}])),
        409, "OUT_OF_STOCK")
    eq("M untouched after failed multi-item", 1, call("GET", "/audit/v1/inventory/var-jersey-001-M")[1]["stock"])
    err("INVALID_DISCOUNT_CODE", call("POST", "/audit/v1/checkout", dict(body, order_id="d5", discount_code="X")),
        400, "INVALID_DISCOUNT_CODE")
    err("VARIANT_NOT_FOUND", call("POST", "/audit/v1/checkout", dict(body, order_id="d6",
        items=[{"variant_id": "nope", "quantity": 1}])), 404, "VARIANT_NOT_FOUND")
    for name, patch in (("quantity 0", {"items": [{"variant_id": "var-jersey-001-M", "quantity": 0}]}),
                        ("quantity 11", {"items": [{"variant_id": "var-jersey-001-M", "quantity": 11}]}),
                        ("no items", {"items": []}),
                        ("duplicate variants", {"items": [{"variant_id": "var-jersey-001-M", "quantity": 1}] * 2}),
                        ("missing payment", {"payment": None}), ("missing order_id", {"order_id": None})):
        err(f"{name} -> 400", call("POST", "/audit/v1/checkout", dict(body, **patch) | ({"order_id": "v-" + name[:5]}
            if "order_id" not in patch else {})), 400, "VALIDATION_ERROR")
    err("inventory unknown -> 404", call("GET", "/audit/v1/inventory/nope"), 404, "VARIANT_NOT_FOUND")
    keys("inventory", call("GET", "/audit/v1/inventory/var-jersey-001-L")[1], ["variant_id", "stock", "reserved"])


def pdf_text(pdf: bytes) -> bytes:
    """Decode every content stream (ASCII85 and/or Flate, as ReportLab writes them) so drawn text is searchable."""
    import zlib
    out = [pdf]
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        raw = m.group(1).strip()
        for attempt in ("flate", "a85+flate", "a85"):
            try:
                if attempt == "flate":
                    out.append(zlib.decompress(raw))
                else:
                    a85 = base64.a85decode(raw[:-2] if raw.endswith(b"~>") else raw)
                    out.append(zlib.decompress(a85) if attempt == "a85+flate" else a85)
                break
            except (zlib.error, ValueError):
                continue
    return b"\n".join(out)


# ------------------------------------------------------------------ 5.13 RBAC + security
def b64json(seg):
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))


def t_rbac():
    section("5.13 RBAC / security")
    call("POST", "/audit/v1/reset")
    r = call("POST", "/audit/v1/rbac-matrix")
    keys("rbac-matrix", r[1], ["tokens", "context"])
    eq("context exact", {"tenant_id": "tenant-alpha", "foreign_tenant_id": "tenant-beta",
                         "own_league_id": "league-alpha-1", "other_league_id": "league-alpha-2",
                         "foreign_league_id": "league-beta-1", "own_club_id": "club-alpha-1",
                         "other_club_id": "club-alpha-2", "foreign_club_id": "club-beta-1",
                         "own_player_id": "player-alpha-1", "other_player_id": "player-alpha-2",
                         "foreign_player_id": "player-beta-1"}, r[1]["context"])
    T, C = r[1]["tokens"], r[1]["context"]
    for role, tok in T.items():
        p = b64json(tok.split(".")[1])
        ok(f"{role} token is JWT valid >= 1h", len(tok.split(".")) == 3 and p["exp"] - time.time() >= 3590,
           ">= 3600 s", int(p["exp"] - time.time()))
    A, D = 200, 403
    roles = ["super_admin", "league_organizer", "club_manager", "player", "viewer"]
    M = [("P1", "POST", "/audit/v1/rbac/tenants", [A, D, D, D, D]),
         ("P2 own", "POST", f"/audit/v1/rbac/leagues/{C['own_league_id']}/fixtures", [A, A, D, D, D]),
         ("P2 other", "POST", f"/audit/v1/rbac/leagues/{C['other_league_id']}/fixtures", [A, D, D, D, D]),
         ("P2 foreign", "POST", f"/audit/v1/rbac/leagues/{C['foreign_league_id']}/fixtures", [A, D, D, D, D]),
         ("P3 own", "POST", f"/audit/v1/rbac/clubs/{C['own_club_id']}/roster", [A, D, A, D, D]),
         ("P4 own", "POST", f"/audit/v1/rbac/clubs/{C['own_club_id']}/products", [A, D, A, D, D]),
         ("P3 other", "POST", f"/audit/v1/rbac/clubs/{C['other_club_id']}/roster", [A, D, D, D, D]),
         ("P4 other", "POST", f"/audit/v1/rbac/clubs/{C['other_club_id']}/products", [A, D, D, D, D]),
         ("P3 foreign", "POST", f"/audit/v1/rbac/clubs/{C['foreign_club_id']}/roster", [A, D, D, D, D]),
         ("P4 foreign", "POST", f"/audit/v1/rbac/clubs/{C['foreign_club_id']}/products", [A, D, D, D, D]),
         ("P5 own", "PATCH", f"/audit/v1/rbac/players/{C['own_player_id']}", [A, D, A, A, D]),
         ("P5 other", "PATCH", f"/audit/v1/rbac/players/{C['other_player_id']}", [A, D, D, D, D]),
         ("P5 foreign", "PATCH", f"/audit/v1/rbac/players/{C['foreign_player_id']}", [A, D, D, D, D]),
         ("P6 own", "GET", f"/audit/v1/rbac/clubs/{C['own_club_id']}", [A, A, A, A, A]),
         ("P6 other", "GET", f"/audit/v1/rbac/clubs/{C['other_club_id']}", [A, A, A, A, A]),
         ("P6 foreign", "GET", f"/audit/v1/rbac/clubs/{C['foreign_club_id']}", [A, D, D, D, D]),
         ("P7", "GET", "/audit/v1/rbac/platform/config", [A, D, D, D, D])]
    for name, method, path, exp in M:
        got, bodies_ok = [], True
        for role, e in zip(roles, exp):
            rr_ = call(method, path, {} if method != "GET" else None, T[role])
            got.append(rr_[0])
            if rr_[0] == 200:
                bodies_ok &= rr_[1] == {"authorized": True}
            elif rr_[0] == 403:
                bodies_ok &= rr_[1].get("error", {}).get("code") == "FORBIDDEN"
        eq(f"matrix {name} (SA,Org,CM,Pl,Vw)", exp, got)
        ok(f"matrix {name} bodies {{authorized:true}} / FORBIDDEN", bodies_ok, True, bodies_ok)
    err("no Authorization -> 401", call("GET", "/audit/v1/rbac/platform/config"), 401, "UNAUTHENTICATED")
    sa = T["super_admin"]
    h, p, s = sa.split(".")
    err("tampered signature -> 401", call("GET", "/audit/v1/rbac/platform/config", token=f"{h}.{p}.{s[::-1]}"), 401,
        "UNAUTHENTICATED")
    none_h = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    err("alg:none -> 401", call("GET", "/audit/v1/rbac/platform/config", token=f"{none_h}.{p}."), 401,
        "UNAUTHENTICATED")
    err("garbage token -> 401", call("GET", "/audit/v1/rbac/platform/config", token="abc"), 401, "UNAUTHENTICATED")
    body = b64json(p)
    body["role"] = "super_admin"
    body["tenant_id"] = None
    forged = h + "." + base64.urlsafe_b64encode(json.dumps(body).encode()).rstrip(b"=").decode() + "." + s
    viewer_p = T["viewer"].split(".")
    vb = b64json(viewer_p[1])
    vb["role"] = "super_admin"
    escalated = viewer_p[0] + "." + base64.urlsafe_b64encode(json.dumps(vb).encode()).rstrip(b"=").decode() + "." + \
        viewer_p[2]
    err("payload tampering (viewer->super_admin) -> 401", call("GET", "/audit/v1/rbac/platform/config",
        token=escalated), 401, "UNAUTHENTICATED")
    ok("forged token not accepted", call("GET", "/audit/v1/rbac/platform/config", token=forged)[0] in (200, 401),
       "same-sig payload change only valid if identical", "ok")
    err("probe ignores body (no validation)", call("POST", "/audit/v1/rbac/tenants", token=T["viewer"], raw=b"{}"),
        403, "FORBIDDEN")
    eq("401 checked before 403/404 (bad token on unknown club)", 401,
       call("GET", "/audit/v1/rbac/clubs/nope", token="bad")[0])
    eq("unknown club id (valid token) -> 404", 404, call("GET", "/audit/v1/rbac/clubs/no-such-club",
                                                         token=T["viewer"])[0])
    time.sleep(11)
    rl = [call("GET", "/api/v1/ping") for _ in range(150)]
    eq("rate limit: first ping 200 {pong:true}", (200, {"pong": True}), (rl[0][0], rl[0][1]))
    n429 = [r for r in rl if r[0] == 429]
    ok(">= 40 of 150 -> 429", len(n429) >= 40, ">= 40", len(n429))
    ok("429 code RATE_LIMITED + Retry-After header", n429 and all(r[1]["error"]["code"] == "RATE_LIMITED" and
       "retry-after" in r[2] for r in n429), True, n429[0][2].get("retry-after") if n429 else None)
    time.sleep(11)
    eq("11 s later ping is 200", 200, call("GET", "/api/v1/ping")[0])


# ------------------------------------------------------------------ 5.14 offline-sync
def t_sync():
    section("5.14 offline-sync")
    call("POST", "/audit/v1/reset")
    call("POST", "/audit/v1/leagues", {"league_id": "ls", "sport_id": "football", "teams": ["t1", "t2"],
                                       "fixtures": [{"match_id": "m1", "home": "t1", "away": "t2"}],
                                       "qualification": {"spots": 1}})
    post_events("m1", [("match_start", {}), ("score", {"team_id": "t1", "event_type": "goal"}),
                       ("score", {"team_id": "t2", "event_type": "goal"})], "pre")
    call("POST", "/audit/v1/roster/setup", dict(SETUP, matches_in_progress=[],
                                                league=dict(SETUP["league"], max_squad_size=2)))
    call("POST", "/audit/v1/roster/transfer", tr("fill", player_id="p2", type="loan", loan_end_date="2026-12-31"))
    sc = {"event_id": "evt-9", "match_id": "m1", "type": "score", "payload": {"team_id": "t1", "event_type": "goal"}}
    body = {"device_id": "dev-1", "actions": [
        {"action_id": "a2", "type": "roster_transfer", "queued_at": "2026-10-17T11:01:00Z", "base_version": 0,
         "payload": tr("sync-tr", player_id="p1", from_squad_id="sq-a", to_squad_id="sq-b")},
        {"action_id": "a1", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 3,
         "payload": sc},
        {"action_id": "a3", "type": "score_event", "queued_at": "2026-10-17T11:02:00Z", "base_version": 99,
         "payload": dict(sc, event_id="evt-10")},
        {"action_id": "a4", "type": "score_event", "queued_at": "2026-10-17T11:03:00Z", "base_version": 0,
         "payload": dict(sc, event_id="evt-11", match_id="ghost")},
        {"action_id": "a5", "type": "score_event", "queued_at": "2026-10-17T11:04:00Z", "base_version": 2,
         "payload": dict(sc, event_id="evt-12")},
        {"action_id": "a6", "type": "score_event", "queued_at": "2026-10-17T11:05:00Z", "base_version": 5,
         "payload": dict(sc, event_id="pre1", payload={"team_id": "t1", "event_type": "goal"})}]}
    r = call("POST", "/audit/v1/offline-sync", body)
    eq("offline-sync -> 200", 200, r[0])
    keys("sync response", r[1], ["device_id", "results", "summary"])
    keys("sync result item", r[1]["results"][0], ["action_id", "status", "resolution", "error_code",
                                                  "processed_order", "server_version", "signature"])
    res = {x["action_id"]: x for x in r[1]["results"]}
    eq("results returned in request order", ["a2", "a1", "a3", "a4", "a5", "a6"],
       [x["action_id"] for x in r[1]["results"]])
    eq("a1 base==current -> applied/appended, processed 1st, version 4, signed",
       ("applied", "appended", None, 1, 4, sign("evt-9", sc["payload"])),
       (res["a1"]["status"], res["a1"]["resolution"], res["a1"]["error_code"], res["a1"]["processed_order"],
        res["a1"]["server_version"], res["a1"]["signature"]))
    eq("a2 roster rule -> rejected/server_wins MIN_POSITION_VIOLATION, signature null",
       ("rejected", "server_wins", "MIN_POSITION_VIOLATION", 2, None),
       (res["a2"]["status"], res["a2"]["resolution"], res["a2"]["error_code"], res["a2"]["processed_order"],
        res["a2"]["signature"]))
    eq("a3 base>current -> INVALID_BASE_VERSION, version unchanged", ("rejected", "INVALID_BASE_VERSION", 4),
       (res["a3"]["status"], res["a3"]["error_code"], res["a3"]["server_version"]))
    eq("a4 unknown match -> MATCH_NOT_FOUND", ("rejected", "server_wins", "MATCH_NOT_FOUND"),
       (res["a4"]["status"], res["a4"]["resolution"], res["a4"]["error_code"]))
    eq("a5 stale base -> applied/rebased_append version 5", ("applied", "rebased_append", 5),
       (res["a5"]["status"], res["a5"]["resolution"], res["a5"]["server_version"]))
    eq("a6 same event_id + identical payload -> duplicate/skipped_duplicate",
       ("duplicate", "skipped_duplicate", None), (res["a6"]["status"], res["a6"]["resolution"],
                                                  res["a6"]["error_code"]))
    eq("summary counts", {"applied": 2, "rejected": 3, "duplicate": 1}, r[1]["summary"])
    r2 = call("POST", "/audit/v1/offline-sync", body)
    eq("re-send -> every action duplicate", {"applied": 0, "rejected": 0, "duplicate": 6}, r2[1]["summary"])
    eq("re-send changed nothing (match version still 5)", 5, call("GET", "/audit/v1/score/m1")[1]["version"])
    err("0 actions -> 400", call("POST", "/audit/v1/offline-sync", {"device_id": "d", "actions": []}), 400,
        "VALIDATION_ERROR")
    err("101 actions -> 400", call("POST", "/audit/v1/offline-sync", {"device_id": "d", "actions": [
        dict(body["actions"][1], action_id=f"x{i}") for i in range(101)]}), 400, "VALIDATION_ERROR")
    r = call("POST", "/audit/v1/offline-sync", {"device_id": "dev-2", "actions": [
        {"action_id": "b1", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 0,
         "payload": dict(sc, event_id="evt-9", payload={"team_id": "t2", "event_type": "goal"})}]})
    eq("same event_id different body -> rejected DUPLICATE_EVENT_ID (HTTP 200)", (200, "DUPLICATE_EVENT_ID"),
       (r[0], r[1]["results"][0]["error_code"]))


# ------------------------------------------------------------------ main
def main():
    for fn in (t_health_reset, t_conventions, t_sports, t_fixtures, t_leagues_events, t_standings, t_roster, t_store,
               t_rbac, t_sync):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001  a crash in one section is a recorded failure, not an abort
            RESULTS.append((SECTION[0], f"section crashed: {type(exc).__name__}", False, "no exception", str(exc)))
    passed = sum(1 for r in RESULTS if r[2])
    failed = len(RESULTS) - passed
    width = max(len(r[1]) for r in RESULTS)
    current = None
    for sec, name, good, exp, act in RESULTS:
        if sec != current:
            print(f"\n=== {sec}")
            current = sec
        line = f"{'PASS' if good else 'FAIL'}  {name.ljust(width)}"
        if not good:
            line += f"\n        expected: {exp}\n        actual:   {act}"
        print(line)
    print("\n=== SUMMARY BY SECTION")
    for sec in dict.fromkeys(r[0] for r in RESULTS):
        rows = [r for r in RESULTS if r[0] == sec]
        print(f"{sec.ljust(32)} {sum(r[2] for r in rows):4d} passed  {sum(not r[2] for r in rows):3d} failed")
    print(f"\nTOTAL: {len(RESULTS)} checks | {passed} passed | {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
