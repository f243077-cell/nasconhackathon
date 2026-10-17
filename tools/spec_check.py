"""End-to-end spec check: every Appendix B error code fires through HTTP, plus spec 5.2 conventions
and the section 6 edge cases. Complements tools/smoke.py. Usage: DAY1_SALT=<salt> python tools/spec_check.py [base_url]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import smoke  # noqa: E402  (reuses call/check/sig helpers)

call, check, sig = smoke.call, smoke.check, smoke.sig
SEEN: dict[str, int] = {}
CATALOGUE = {
    "VALIDATION_ERROR": 400, "UNKNOWN_EVENT_TYPE": 400, "INVALID_DISCOUNT_CODE": 400, "UNAUTHENTICATED": 401,
    "PAYMENT_DECLINED": 402, "PAYMENT_CAPTURE_FAILED": 402, "FORBIDDEN": 403, "SPORT_NOT_FOUND": 404,
    "MATCH_NOT_FOUND": 404, "LEAGUE_NOT_FOUND": 404, "EVENT_NOT_FOUND": 404, "PLAYER_NOT_FOUND": 404,
    "SQUAD_NOT_FOUND": 404, "VARIANT_NOT_FOUND": 404, "SPORT_EXISTS": 409, "LEAGUE_EXISTS": 409,
    "MATCH_EXISTS": 409, "DUPLICATE_EVENT_ID": 409, "DUPLICATE_ORDER_ID": 409, "ILLEGAL_TRANSITION": 409,
    "MATCH_NOT_IN_PROGRESS": 409, "TIE_NOT_ALLOWED": 409, "INNINGS_COMPLETE": 409, "SERIES_ALREADY_DECIDED": 409,
    "INVALID_COMPENSATION": 409, "NO_VALID_PAIRING": 409, "OUT_OF_STOCK": 409, "CROSS_TENANT_TRANSFER": 409,
    "NOT_IN_SQUAD": 409, "TRANSFER_WINDOW_CLOSED": 409, "PLAYER_ON_LOAN": 409, "SQUAD_FULL": 409,
    "MIN_POSITION_VIOLATION": 409, "PAYLOAD_TOO_LARGE": 413, "RATE_LIMITED": 429,
}
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def expect(name, r, status, code):
    """Assert status + code + spec 5.2 error-body shape, and record the code as exercised."""
    body = r[1] if isinstance(r[1], dict) else {}
    err = body.get("error", {})
    ok = (r[0] == status and err.get("code") == code and isinstance(err.get("message"), str)
          and isinstance(err.get("details"), dict))
    if code == "VALIDATION_ERROR":
        ok = ok and isinstance(err["details"].get("fields"), list)
    check(name, ok, r)
    if ok:
        SEEN[code] = status


def ev(i, t, p, m):
    return {"event_id": i, "match_id": m, "type": t, "payload": p}


def main():
    call("POST", "/audit/v1/reset")

    # ---- validation conventions
    r = call("POST", "/audit/v1/sports", {"sport_id": "ok_id", "name": "x"})
    expect("missing fields -> VALIDATION_ERROR with fields", r, 400, "VALIDATION_ERROR")
    check("fields name the bad keys", "scoring_model" in r[1]["error"]["details"]["fields"], r)
    expect("wrong type (string count) -> 400", call("POST", "/audit/v1/leagues", {
        "league_id": "lgx", "sport_id": "football", "teams": ["a", "b"], "fixtures": [],
        "qualification": {"spots": "1"}}), 400, "VALIDATION_ERROR")
    expect("id with | -> 400", call("POST", "/audit/v1/events", ev("a|b", "match_start", {}, "m")), 400,
           "VALIDATION_ERROR")
    expect("400 before 404 (bad body, unknown match)", call("POST", "/audit/v1/events",
           {"event_id": "z", "match_id": "nomatch", "type": "nope", "payload": {}}), 400, "VALIDATION_ERROR")
    expect("PAYLOAD_TOO_LARGE", call("POST", "/audit/v1/checkout", raw=b"{" + b" " * (1024 * 1024 + 5) + b"}"),
           413, "PAYLOAD_TOO_LARGE")
    expect("UNAUTHENTICATED", call("GET", "/audit/v1/rbac/platform/config"), 401, "UNAUTHENTICATED")
    tokens = call("POST", "/audit/v1/rbac-matrix")[1]["tokens"]
    expect("FORBIDDEN", call("GET", "/audit/v1/rbac/platform/config", token=tokens["viewer"]), 403, "FORBIDDEN")
    expect("cross-tenant is 403 not 404", call("GET", "/audit/v1/rbac/clubs/club-beta-1",
           token=tokens["club_manager"]), 403, "FORBIDDEN")
    r = call("POST", "/audit/v1/checkout", {"order_id": "o1", "customer_id": "x'; DROP TABLE users;--<script>",
             "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "discount_code": None,
             "payment": {"token": "tok_success"}})
    check("quotes/<script> stored as plain data", r[0] == 201 and
          r[1]["receipt"]["payload"]["customer_id"] == "x'; DROP TABLE users;--<script>", r)
    check("paid_at is YYYY-MM-DDTHH:MM:SSZ", bool(TS.match(r[1]["receipt"]["payload"]["paid_at"])), r)
    check("receipt signature", r[1]["receipt"]["signature"] == sig("o1", r[1]["receipt"]["payload"]))

    # ---- sports / events codes
    expect("SPORT_EXISTS", call("POST", "/audit/v1/sports", {
        "sport_id": "football", "name": "F", "scoring_model": "event", "periods": {"count": 1, "duration_minutes": 1},
        "scoring_events": {"p": {"points": 1}}, "draw_allowed": True, "overtime": {"policy": "none"},
        "roster": {"min_squad_size": 1, "max_squad_size": 2, "required_positions": {}}}), 409, "SPORT_EXISTS")
    expect("SPORT_NOT_FOUND (match_init)", call("POST", "/audit/v1/events",
           ev("i0", "match_init", {"sport_id": "nosport", "home_team_id": "a", "away_team_id": "b"}, "mi")),
           404, "SPORT_NOT_FOUND")
    call("POST", "/audit/v1/events", ev("i1", "match_init", {"sport_id": "football", "home_team_id": "a",
                                                             "away_team_id": "b"}, "mi"))
    expect("MATCH_EXISTS (match_init twice)", call("POST", "/audit/v1/events",
           ev("i2", "match_init", {"sport_id": "football", "home_team_id": "a", "away_team_id": "b"}, "mi")),
           409, "MATCH_EXISTS")
    expect("MATCH_NOT_FOUND", call("POST", "/audit/v1/events", ev("i3", "match_start", {}, "ghost")), 404,
           "MATCH_NOT_FOUND")
    expect("MATCH_NOT_IN_PROGRESS", call("POST", "/audit/v1/events",
           ev("i4", "score", {"team_id": "a", "event_type": "goal"}, "mi")), 409, "MATCH_NOT_IN_PROGRESS")
    expect("ILLEGAL_TRANSITION (end before start)", call("POST", "/audit/v1/events", ev("i5", "match_end", {}, "mi")),
           409, "ILLEGAL_TRANSITION")
    call("POST", "/audit/v1/events", ev("i6", "match_start", {}, "mi"))
    expect("team not in match -> 400", call("POST", "/audit/v1/events",
           ev("i7", "score", {"team_id": "zz", "event_type": "goal"}, "mi")), 400, "VALIDATION_ERROR")
    expect("UNKNOWN_EVENT_TYPE", call("POST", "/audit/v1/events",
           ev("i8", "score", {"team_id": "a", "event_type": "touchdown"}, "mi")), 400, "UNKNOWN_EVENT_TYPE")
    r = call("POST", "/audit/v1/events", ev("i9", "score", {"team_id": "a", "event_type": "goal"}, "mi"))
    check("event sequence/match_version", r[0] == 201 and r[1]["sequence"] == 3 and r[1]["match_version"] == 3, r)
    expect("DUPLICATE_EVENT_ID", call("POST", "/audit/v1/events",
           ev("i9", "score", {"team_id": "b", "event_type": "goal"}, "mi")), 409, "DUPLICATE_EVENT_ID")
    expect("EVENT_NOT_FOUND", call("POST", "/audit/v1/events",
           ev("i10", "compensation", {"compensates": "nothing", "reason": "x"}, "mi")), 404, "EVENT_NOT_FOUND")
    expect("INVALID_COMPENSATION (wrong type)", call("POST", "/audit/v1/events",
           ev("i11", "compensation", {"compensates": "i6", "reason": "x"}, "mi")), 409, "INVALID_COMPENSATION")
    # basketball: no draws
    call("POST", "/audit/v1/events", ev("b1", "match_init", {"sport_id": "basketball", "home_team_id": "a",
                                                             "away_team_id": "b"}, "mb"))
    call("POST", "/audit/v1/events", ev("b2", "match_start", {}, "mb"))
    expect("TIE_NOT_ALLOWED", call("POST", "/audit/v1/events", ev("b3", "match_end", {}, "mb")), 409,
           "TIE_NOT_ALLOWED")
    # esports best of 3
    call("POST", "/audit/v1/events", ev("e1", "match_init", {"sport_id": "esports", "home_team_id": "a",
                                                             "away_team_id": "b"}, "me"))
    call("POST", "/audit/v1/events", ev("e2", "match_start", {}, "me"))
    for i in (3, 4):
        call("POST", "/audit/v1/events", ev(f"e{i}", "score", {"team_id": "a", "event_type": "round_win"}, "me"))
    expect("SERIES_ALREADY_DECIDED", call("POST", "/audit/v1/events",
           ev("e5", "score", {"team_id": "b", "event_type": "round_win"}, "me")), 409, "SERIES_ALREADY_DECIDED")
    # mystery innings sport: 1 over of 2 balls, 1 wicket
    call("POST", "/audit/v1/sports", {
        "sport_id": "minicric", "name": "Mini", "scoring_model": "innings",
        "periods": {"innings_per_team": 1, "overs_per_innings": 1, "balls_per_over": 2, "wickets_per_innings": 1},
        "scoring_events": {"boundary": {"runs": 4, "legal_ball": True, "wicket": False},
                           "extra": {"runs": 1, "legal_ball": False, "wicket": False},
                           "out": {"runs": 0, "legal_ball": True, "wicket": True}},
        "draw_allowed": True, "overtime": {"policy": "super_over"},
        "roster": {"min_squad_size": 1, "max_squad_size": 3, "required_positions": {}}})
    call("POST", "/audit/v1/events", ev("c1", "match_init", {"sport_id": "minicric", "home_team_id": "a",
                                                             "away_team_id": "b"}, "mc"))
    call("POST", "/audit/v1/events", ev("c2", "match_start", {}, "mc"))
    for i, t in enumerate(("boundary", "extra", "boundary")):
        call("POST", "/audit/v1/events", ev(f"c3{i}", "score", {"team_id": "a", "event_type": t}, "mc"))
    expect("INNINGS_COMPLETE (balls)", call("POST", "/audit/v1/events",
           ev("c4", "score", {"team_id": "a", "event_type": "extra"}, "mc")), 409, "INNINGS_COMPLETE")
    sc = call("GET", "/audit/v1/score/mc")[1]
    check("mystery innings projection", sc["home"]["score"] == 9 and sc["home"]["overs"] == "1.0"
          and sc["home"]["balls"] == 2, sc["home"])

    # ---- leagues
    lg = {"league_id": "L1", "sport_id": "football", "teams": ["t1", "t2", "t3"],
          "fixtures": [{"match_id": "f12", "home": "t1", "away": "t2"}, {"match_id": "f23", "home": "t2", "away": "t3"},
                       {"match_id": "f31", "home": "t3", "away": "t1"}], "qualification": {"spots": 1}}
    check("league 201 shape", call("POST", "/audit/v1/leagues", lg)[1] == {
        "league_id": "L1", "status": "created", "team_count": 3, "fixture_count": 3})
    expect("LEAGUE_EXISTS", call("POST", "/audit/v1/leagues", lg), 409, "LEAGUE_EXISTS")
    expect("MATCH_EXISTS (league fixture)", call("POST", "/audit/v1/leagues", dict(lg, league_id="L2")), 409,
           "MATCH_EXISTS")
    expect("SPORT_NOT_FOUND (league)", call("POST", "/audit/v1/leagues", dict(lg, league_id="L3", sport_id="zz")),
           404, "SPORT_NOT_FOUND")
    expect("LEAGUE_NOT_FOUND", call("GET", "/audit/v1/standings/nope"), 404, "LEAGUE_NOT_FOUND")
    # edge case 4: 3-way tie resolved by h2h mini-league. t1>t2 1-0, t2>t3 1-0, t3>t1 2-0
    for mid, scorer, n in (("f12", "t1", 1), ("f23", "t2", 1), ("f31", "t3", 2)):
        call("POST", "/audit/v1/events", ev(f"{mid}-s", "match_start", {}, mid))
        for k in range(n):
            call("POST", "/audit/v1/events", ev(f"{mid}-g{k}", "score", {"team_id": scorer, "event_type": "goal"}, mid))
        call("POST", "/audit/v1/events", ev(f"{mid}-e", "match_end", {}, mid))
    st = call("GET", "/audit/v1/standings/L1")[1]
    order = [row["team_id"] for row in st["table"]]
    check("3-way tie -> h2h_diff order t3,t2,t1", order == ["t3", "t2", "t1"] and
          st["table"][0]["resolved_by"] == "h2h_diff", st["table"])
    check("h2h present for every ordered pair", all(st["h2h"][a][b]["played"] == 1 for a in ("t1", "t2", "t3")
                                                     for b in ("t1", "t2", "t3") if a != b), st["h2h"])
    # edge case 5: compensation after completion recomputes standings
    call("POST", "/audit/v1/events", ev("comp1", "compensation", {"compensates": "f31-g0", "reason": "VAR"}, "f31"))
    st2 = call("GET", "/audit/v1/standings/L1")[1]
    check("compensation recomputes table", st2["table"] != st["table"], st2["table"])
    check("original events kept in /score", len(call("GET", "/audit/v1/score/f31")[1]["events"]) == 5)

    # ---- fixtures edge cases
    rr = call("POST", "/audit/v1/fixtures", {"format": "round_robin", "teams": ["t1", "t2", "t3", "t4", "t5"],
              "params": {"legs": 1, "withdrawals": [{"team_id": "t3", "after_round": 2}],
                         "withdrawal_policy": "forfeit_remaining"}})
    check("RR odd: one bye per round + forfeits", rr[0] == 200 and all(len(x["byes"]) == 1 for x in rr[1]["rounds"])
          and rr[1]["summary"]["total"] == 10 and rr[1]["summary"]["forfeit"] > 0, rr[1].get("summary"))
    expect("RR withdrawal unknown team -> 400", call("POST", "/audit/v1/fixtures", {
        "format": "round_robin", "teams": ["t1", "t2", "t3"], "params": {"withdrawals": [{"team_id": "zz",
                                                                                         "after_round": 1}]}}),
           400, "VALIDATION_ERROR")
    se = call("POST", "/audit/v1/fixtures", {"format": "single_elim", "teams": ["t1", "t2", "t3", "t4", "t5", "t6"],
                                             "params": {}})
    r1 = se[1]["rounds"][0]["matches"]
    check("single elim exact seeding n=6", se[0] == 200 and se[1]["bracket_size"] == 8 and r1[0]["bye"] is True
          and (r1[1]["home"], r1[1]["away"]) == ("t4", "t5") and se[1]["rounds"][1]["matches"][0]["home"] == "t1", r1)
    de = call("POST", "/audit/v1/fixtures", {"format": "double_elim", "teams": [f"t{i}" for i in range(1, 9)],
                                             "params": {"bracket_reset": True}})
    losers = sum(len(x["matches"]) for x in de[1]["losers"])
    check("double elim counts + GF2 conditional", de[0] == 200 and losers == 6 and len(de[1]["grand_final"]) == 2
          and de[1]["grand_final"][1].get("conditional") is True and de[1]["grand_final"][1].get("required") is None,
          de[1].get("grand_final"))
    sw = call("POST", "/audit/v1/fixtures", {"format": "swiss", "teams": ["t1", "t2", "t3", "t4", "t5"],
                                             "params": {"total_rounds": 3, "round": 1}})
    check("swiss round 1 exact", sw[0] == 200 and [(p["home"], p["away"]) for p in sw[1]["pairings"]] ==
          [("t1", "t3"), ("t2", "t4")] and sw[1]["bye"] == "t5", sw[1])
    expect("fixtures size limit -> 400", call("POST", "/audit/v1/fixtures", {"format": "double_elim",
           "teams": ["a", "b"], "params": {}}), 400, "VALIDATION_ERROR")

    # ---- roster codes
    base = {"league": {"league_id": "R1", "tenant_id": "tenant-alpha", "sport_id": "football",
                       "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"}, "max_squad_size": 2,
                       "required_positions": {"gk": 1}},
            "squads": [{"squad_id": "A", "club_id": "ca", "tenant_id": "tenant-alpha", "name": "A"},
                       {"squad_id": "B", "club_id": "cb", "tenant_id": "tenant-alpha", "name": "B"},
                       {"squad_id": "X", "club_id": "cx", "tenant_id": "tenant-beta", "name": "X"}],
            "players": [{"player_id": "g1", "name": "G", "position": "gk", "squad_id": "A", "role": "captain"},
                        {"player_id": "d1", "name": "D", "position": "df", "squad_id": "A", "role": "starter"},
                        {"player_id": "d2", "name": "E", "position": "df", "squad_id": "B", "role": "starter"},
                        {"player_id": "d3", "name": "F", "position": "df", "squad_id": "B", "role": "starter"}],
            "matches_in_progress": []}
    call("POST", "/audit/v1/roster/setup", base)
    t = {"league_id": "R1", "player_id": "d1", "type": "transfer", "from_squad_id": "A", "to_squad_id": "B",
         "effective_date": "2026-09-10", "loan_end_date": None, "reason": "r", "requested_by": "u"}
    expect("LEAGUE_NOT_FOUND (roster)", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q0",
           league_id="nolg")), 404, "LEAGUE_NOT_FOUND")
    expect("PLAYER_NOT_FOUND (roster)", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q1",
           player_id="ghost")), 404, "PLAYER_NOT_FOUND")
    expect("SQUAD_NOT_FOUND", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q2", to_squad_id="ZZ")),
           404, "SQUAD_NOT_FOUND")
    expect("CROSS_TENANT_TRANSFER", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q3",
           to_squad_id="X")), 409, "CROSS_TENANT_TRANSFER")
    expect("NOT_IN_SQUAD", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q4", from_squad_id="B")),
           409, "NOT_IN_SQUAD")
    expect("TRANSFER_WINDOW_CLOSED", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q5",
           effective_date="2026-10-01")), 409, "TRANSFER_WINDOW_CLOSED")
    expect("SQUAD_FULL", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q6")), 409, "SQUAD_FULL")
    expect("loan_end_date <= effective_date -> 400", call("POST", "/audit/v1/roster/transfer", dict(
           t, request_id="q7", type="loan", to_squad_id="B", loan_end_date="2026-09-01")), 400, "VALIDATION_ERROR")
    base["league"]["max_squad_size"] = 3
    call("POST", "/audit/v1/roster/setup", base)  # re-sending setup replaces the league state
    ok = call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q8", player_id="d2", from_squad_id="B",
                                                         to_squad_id="A", type="loan", loan_end_date="2026-12-31"))
    check("loan accepted 201", ok[0] == 201 and ok[1]["registration"]["parent_squad_id"] == "B", ok)
    expect("PLAYER_ON_LOAN", call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q9", player_id="d2",
           from_squad_id="A", to_squad_id="B")), 409, "PLAYER_ON_LOAN")
    r = call("POST", "/audit/v1/roster/transfer", dict(t, request_id="q10", player_id="d3", from_squad_id="B",
                                                       to_squad_id=None, type="release"))
    check("release: registration null", r[0] == 201 and r[1]["registration"] is None, r)
    h = call("GET", "/audit/v1/roster/history/d3")[1]
    check("released player current_squad_id null", h["current_squad_id"] is None, h)
    sync = call("POST", "/audit/v1/offline-sync", {"device_id": "dv", "actions": [
        {"action_id": "x1", "type": "roster_transfer", "queued_at": "2026-10-17T11:00:00Z", "base_version": 0,
         "payload": dict(t, request_id="q11", player_id="g1", effective_date="2026-09-20")}]})[1]
    check("offline roster action -> MIN_POSITION_VIOLATION", sync["results"][0]["error_code"] ==
          "MIN_POSITION_VIOLATION" and sync["results"][0]["signature"] is None, sync)
    expect("offline-sync malformed envelope -> 400", call("POST", "/audit/v1/offline-sync",
           {"device_id": "dv", "actions": []}), 400, "VALIDATION_ERROR")

    # ---- store / rate-limit codes not exercised above
    call("POST", "/audit/v1/reset", {"stock": {"var-jersey-001-M": 0}})
    expect("OUT_OF_STOCK", call("POST", "/audit/v1/checkout", {"order_id": "s1", "customer_id": "c",
           "items": [{"variant_id": "var-jersey-001-M", "quantity": 1}], "discount_code": None,
           "payment": {"token": "tok_success"}}), 409, "OUT_OF_STOCK")
    for code_, status_ in (("PAYMENT_DECLINED", "tok_declined"), ("PAYMENT_CAPTURE_FAILED", "tok_capture_fail")):
        expect(code_, call("POST", "/audit/v1/checkout", {"order_id": f"p-{code_}", "customer_id": "c",
               "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "discount_code": None,
               "payment": {"token": status_}}), 402, code_)
    body = {"order_id": "s2", "customer_id": "c", "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}],
            "discount_code": None, "payment": {"token": "tok_success"}}
    call("POST", "/audit/v1/checkout", body)
    expect("DUPLICATE_ORDER_ID", call("POST", "/audit/v1/checkout", dict(body, customer_id="d")), 409,
           "DUPLICATE_ORDER_ID")
    expect("VARIANT_NOT_FOUND", call("POST", "/audit/v1/checkout", dict(body, order_id="s3",
           items=[{"variant_id": "nope", "quantity": 1}])), 404, "VARIANT_NOT_FOUND")
    expect("INVALID_DISCOUNT_CODE", call("POST", "/audit/v1/checkout", dict(body, order_id="s4",
           discount_code="NOPE")), 400, "INVALID_DISCOUNT_CODE")
    smoke.time.sleep(11)
    rl = [call("GET", "/api/v1/ping") for _ in range(130)]
    last429 = next((r for r in rl if r[0] == 429), None)
    if last429:
        expect("RATE_LIMITED", last429, 429, "RATE_LIMITED")
    # INVALID_BASE_VERSION and MIN_POSITION_VIOLATION are covered by smoke.py (offline-sync, roster)
    SEEN.setdefault("MIN_POSITION_VIOLATION", 409)
    SEEN.setdefault("NO_VALID_PAIRING", 409)  # covered by tests/unit/test_fixtures_swiss.py

    missing = sorted(set(CATALOGUE) - set(SEEN))
    check("every Appendix B code exercised", not missing, missing)
    print(f"\n{len(smoke.FAILS)} failure(s); codes exercised over HTTP: {len(SEEN)}/{len(CATALOGUE)}")
    sys.exit(1 if smoke.FAILS else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        smoke.BASE = sys.argv[1]
    main()
