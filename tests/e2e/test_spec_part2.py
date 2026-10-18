"""Part II specification, section by section (§1.2 ... Appendix C): every rule in the PDF as a test with its expected
result. Runs against the live stack and resets it before each test.

    DAY2_SALT=<s2> pytest tests/e2e/test_spec_part2.py -q --junitxml=tests/reports/spec-part2-report.xml
"""
import hashlib
import hmac
import json
import os
import re
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest

from test_tanzeel_platform import BASE, GUEST, REPO, TESTIDS, call, code, event, login, new_match

SALT2 = os.environ.get("DAY2_SALT", "")
REF_SALT = "T01D27ad7ffff12e"
CS = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
      "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"], "layout": "grid_4",
      "simulate_host_drop": True}
MERGE = {"guest_token": GUEST, "registered_user_id": "player-alpha-1",
         "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "test_write_block": True}
MOD = {"chat_room_id": "chat-cs-session-101", "incoming_messages": [
    {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary"},
    {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream b@d_w0rd now!"},
    {"message_id": "msg-3", "sender": "user-flooder", "text": "GOAL! AAAA!!!"}], "check_dlq": True,
    "simulate_failed_notifications": 0}


def canonical(obj):                                    # Appendix A reference, verbatim
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_day2(salt, entity_id, payload):               # Appendix A reference, verbatim
    return hmac.new(salt.encode("utf-8"), (entity_id + "|" + canonical(payload)).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def is_error(r, status, err):
    """Standard envelope (§5.2): error.code, error.message (str), error.details (object)."""
    body = r[1]
    return (r[0] == status and isinstance(body, dict) and set(body) == {"error"} and body["error"]["code"] == err
            and isinstance(body["error"]["message"], str) and isinstance(body["error"]["details"], dict))


def fields(r):
    return r[1]["error"]["details"].get("fields", [])


needs_salt = pytest.mark.skipif(not SALT2, reason="DAY2_SALT not set")


@pytest.fixture(autouse=True)
def reset():
    assert call("POST", "/audit/v1/reset")[0] == 200
    yield


# ------------------------------------------------------------------ §1.2 / §7.3 continuity and salt handling
def test_s1_2_history_descends_from_day1_base_sha():
    rc = subprocess.run(["git", "merge-base", "--is-ancestor", "d92fcbf", "HEAD"], cwd=REPO).returncode
    assert rc == 0


def test_s7_3_day2_salt_read_from_env_never_hard_coded():
    cfg = (REPO / "backend/app/config.py").read_text(encoding="utf-8")
    assert 'DAY2_SALT = os.environ.get("DAY2_SALT"' in cfg
    for f in (REPO / "backend/app").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert REF_SALT not in text, f
        if SALT2 and SALT2 != REF_SALT:
            assert SALT2 not in text, f
    assert "DAY2_SALT" in (REPO / ".env.example").read_text() and REF_SALT not in (REPO / ".env.example").read_text()


# ------------------------------------------------------------------ §1.3 repository structure
@pytest.mark.parametrize("path", ["docker-compose.yml", ".github/workflows/autograde.yml", "tests/selenium",
                                  "tests/appium", "tests/k6_load.js", "tests/reports/selenium-report.xml",
                                  "tests/reports/appium-report.xml", "tests/reports/k6-summary.json",
                                  "COVERAGE_DAY2.json", "TRACEABILITY.md"])
def test_s1_3_required_paths_exist(path):
    assert (REPO / path).exists()


def test_s1_3_autograde_runs_probes_grid_and_k6_on_push_to_main():
    wf = (REPO / ".github/workflows/autograde.yml").read_text(encoding="utf-8")
    assert re.search(r"push:\s*\n\s*branches:\s*\[main\]", wf)
    for needle in ("4444/status", "k6", "day2_check.py", "conformance.py", "tests/selenium"):
        assert needle in wf, needle


def test_s1_3_compose_has_full_stack_and_forwards_both_salts():
    import yaml
    d = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    for svc in ("postgres", "redis", "minio", "api", "mediamtx", "selenium-hub", "node-chrome-1", "node-chrome-2",
                "node-firefox"):
        assert svc in d, svc
    assert d["api"]["environment"]["DAY1_SALT"] == "${DAY1_SALT}" and d["api"]["environment"]["DAY2_SALT"] == "${DAY2_SALT}"
    assert "8080:8080" in d["api"]["ports"]
    assert {"1935:1935", "8888:8888", "8889:8889"} <= set(d["mediamtx"]["ports"])


# ------------------------------------------------------------------ §3 traceability
@pytest.mark.parametrize("rid", ["FR-3.1", "FR-3.2", "FR-3.3", "FR-4.1", "FR-4.2", "FR-4.3", "FR-4.4", "FR-5.2",
                                 "FR-5.3", "NFR-1", "NFR-2", "NFR-6", "NFR-8", "NFR-9"])
def test_s3_every_requirement_id_is_traced(rid):
    assert re.search(rf"\|\s*{re.escape(rid)}\b", (REPO / "TRACEABILITY.md").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ §5.1 endpoint index
@pytest.mark.parametrize("method,path", [
    ("GET", "/health"), ("POST", "/audit/v1/reset"), ("POST", "/audit/v1/stream/key"),
    ("POST", "/audit/v1/costream/session"), ("GET", "/audit/v1/qr/match-m1"), ("GET", "/audit/v1/qr/match-m1/export.svg"),
    ("GET", "/q/m1-live"), ("POST", "/audit/v1/guest/cart-merge"), ("POST", "/audit/v1/moderation/test"),
    ("GET", "/metrics"), ("DELETE", "/audit/v1/privacy/user/player-alpha-1")])
def test_s5_1_endpoint_registered(method, path):
    s = call(method, path, body={} if method == "POST" else None, follow=False)[0]
    assert s not in (404, 405) or path.startswith("/audit/v1/privacy"), (path, s)


# ------------------------------------------------------------------ §5.2 startup, seed, validation order, envelope
def test_s5_2_health_exact_body():
    assert call("GET", "/health")[:2] == (200, {"status": "ok"})


def test_s5_2_reset_seeds_match_m1_exactly():
    s, b, _ = call("GET", "/audit/v1/score/match-m1")
    assert s == 200 and b["sport_id"] == "football" and b["league_id"] == "league-alpha-1"
    assert b["status"] == "in_progress" and b["home"]["team_id"] == "club-alpha-1" and b["away"]["team_id"] == "club-alpha-2"
    assert (b["home"]["score"], b["away"]["score"]) == (1, 0)


def test_s5_2_reset_seeds_qr_mappings_with_zero_scans():
    for entity, short in (("match-m1", "m1-live"), ("player-alpha-1", "p-alpha-1"), ("club-alpha-1", "c-alpha-1")):
        b = call("GET", f"/audit/v1/qr/{entity}?inspect=true")[1]
        assert b["short_url"] == f"http://localhost:8080/q/{short}" and b["scan_count"] == 0


def test_s5_2_reset_seeds_player_beta_2_in_club_beta_1_and_day1_store():
    b = call("GET", "/api/v1/athletes/player-beta-2")[1]
    assert any(a["club_id"] == "club-beta-1" for a in b["affiliations"])
    for vid in ("var-jersey-001-M", "var-jersey-001-L"):
        assert call("GET", f"/audit/v1/inventory/{vid}")[0] == 200


def test_s5_2_reset_seeds_valid_unmerged_guest_token_and_empty_cart():
    r = call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, test_write_block=False))
    assert r[0] == 200 and r[1]["active_cart"]["total_items"] == 1      # unmerged + player-alpha-1 cart was empty
    assert r[1]["active_cart"]["items"] == [{"variant_id": "var-jersey-001-L", "quantity": 1, "unit_price_minor": 450000}]


def test_s5_2_validation_order_400_before_404_before_409():
    r = call("POST", "/audit/v1/costream/session", dict(CS, participants=["nobody"] * 6, layout="bad"))
    assert is_error(r, 400, "VALIDATION_ERROR")                          # schema first
    r = call("POST", "/audit/v1/costream/session", dict(CS, participants=CS["participants"] + ["nobody"]))
    assert is_error(r, 404, "PLAYER_NOT_FOUND")                          # existence before capacity
    r = call("POST", "/audit/v1/costream/session",
             dict(CS, participants=CS["participants"] + ["player-alpha-1b"]))
    assert is_error(r, 409, "COSTREAM_SESSION_FULL")


def test_s5_2_error_envelope_on_guest_write():
    r = call("POST", "/api/v1/chat", {"chat_room_id": "chat-match-m1", "text": "x"}, token=GUEST)
    assert is_error(r, 403, "GUEST_WRITE_FORBIDDEN") and r[1]["error"]["details"] == {"guest_token": GUEST}


# ------------------------------------------------------------------ §5.3 signatures on every signed route
@needs_salt
def test_s5_3_stream_key_signature():
    b = call("POST", "/audit/v1/stream/key", {"action": "rotate", "player_id": "player-alpha-1",
                                               "label": "OBS-Main-Desk", "stream_key_override": "sk_live_9f83a1b2c3d4e5f6"})[1]
    p = {"action": "rotate", "player_id": "player-alpha-1", "status": "active", "stream_key": "sk_live_9f83a1b2c3d4e5f6"}
    assert b["signature"] == sign_day2(SALT2, "sk_live_9f83a1b2c3d4e5f6", p)


@needs_salt
def test_s5_3_costream_signature():
    b = call("POST", "/audit/v1/costream/session", CS)[1]
    p = {k: b[k] for k in ("active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status")}
    assert b["signature"] == sign_day2(SALT2, "cs-session-101", p)


@needs_salt
def test_s5_3_qr_signature():
    b = call("GET", "/audit/v1/qr/match-m1")[1]
    p = {"entity_id": "match-m1", "short_url": b["short_url"], "target_route": b["target_route"]}
    assert b["signature"] == sign_day2(SALT2, "match-m1", p)


@needs_salt
def test_s5_3_cart_merge_signature():
    b = call("POST", "/audit/v1/guest/cart-merge", MERGE)[1]
    p = {"cart_merged": True, "guest_token": GUEST, "registered_user_id": "player-alpha-1", "total_items": 1,
         "write_rejection_code": 403}
    assert b["signature"] == sign_day2(SALT2, GUEST, p)


@needs_salt
def test_s5_3_moderation_signature_counts_flagged_messages():
    b = call("POST", "/audit/v1/moderation/test", MOD)[1]
    p = {"chat_room_id": "chat-cs-session-101", "flagged_count": 1, "kicked_users": ["user-spammer"], "queue_depth": 0}
    assert b["signature"] == sign_day2(SALT2, "chat-cs-session-101", p)


# ------------------------------------------------------------------ §5.4 stream keys
def test_s5_4_rotate_with_override_full_response():
    s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "rotate", "player_id": "player-alpha-1",
                                                     "label": "OBS-Main-Desk", "stream_key_override": "sk_live_9f83a1b2c3d4e5f6"})
    assert s == 200
    assert {k: b[k] for k in ("player_id", "label", "stream_key", "status", "ingest_endpoints", "playback_url")} == {
        "player_id": "player-alpha-1", "label": "OBS-Main-Desk", "stream_key": "sk_live_9f83a1b2c3d4e5f6",
        "status": "active",
        "ingest_endpoints": {"rtmp": "rtmp://localhost:1935/live/sk_live_9f83a1b2c3d4e5f6",
                             "webrtc": "http://localhost:8889/live/sk_live_9f83a1b2c3d4e5f6/whip"},
        "playback_url": "http://localhost:8888/live/sk_live_9f83a1b2c3d4e5f6/index.m3u8"}
    assert re.fullmatch(r"[0-9a-f]{64}", b["signature"])


def test_s5_4_generate_201_unique_keys_and_default_label():
    keys = set()
    for _ in range(3):
        s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})
        assert s == 201 and b["label"] == "default" and re.fullmatch(r"sk_live_[a-f0-9]{16}", b["stream_key"])
        keys.add(b["stream_key"])
    assert len(keys) == 3


def test_s5_4_generate_replaces_old_key():
    k1 = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})[1]["stream_key"]
    call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})
    assert is_error(call("POST", "/audit/v1/stream/publish", {"stream_key": k1}), 409, "KEY_REVOKED")


def test_s5_4_rotate_invalidates_prior_key():
    k1 = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})[1]["stream_key"]
    s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "rotate", "player_id": "player-alpha-2"})
    assert s == 200 and b["stream_key"] != k1 and b["status"] == "active"
    assert is_error(call("POST", "/audit/v1/stream/publish", {"stream_key": k1}), 409, "KEY_REVOKED")


def test_s5_4_revoke_nulls_and_later_use_is_key_revoked():
    k = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})[1]["stream_key"]
    s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})
    assert s == 200 and b["status"] == "revoked" and b["ingest_endpoints"] is None and b["playback_url"] is None
    assert b["stream_key"] == k
    assert is_error(call("POST", "/audit/v1/stream/publish", {"stream_key": k}), 409, "KEY_REVOKED")


def test_s5_4_revoke_without_key_404():
    assert is_error(call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-beta-2"}), 404,
                    "STREAM_NOT_FOUND")


@pytest.mark.parametrize("body,field", [
    ({"player_id": "player-alpha-1"}, "action"), ({"action": "pause", "player_id": "player-alpha-1"}, "action"),
    ({"action": "generate"}, "player_id"), ({"action": "generate", "player_id": "player-alpha-1", "label": ""}, "label"),
    ({"action": "generate", "player_id": "player-alpha-1", "label": "x" * 65}, "label")])
def test_s5_4_schema_errors(body, field):
    r = call("POST", "/audit/v1/stream/key", body)
    assert is_error(r, 400, "VALIDATION_ERROR") and field in fields(r)


def test_s5_4_unknown_player_404():
    assert is_error(call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-zzz"}), 404,
                    "PLAYER_NOT_FOUND")


# ------------------------------------------------------------------ §5.5 co-stream
def test_s5_5_example_response_exact():
    s, b, _ = call("POST", "/audit/v1/costream/session", CS)
    assert s == 201
    assert {k: v for k, v in b.items() if k != "signature"} == {
        "session_id": "cs-session-101", "status": "active", "active_host": "player-alpha-2", "handoff_occurred": True,
        "participant_count": 3, "active_participants": ["player-alpha-2", "player-beta-1", "player-beta-2"],
        "layout": "grid_4", "composite_playback_url": "http://localhost:8888/costream/cs-session-101/index.m3u8",
        "chat_room_id": "chat-cs-session-101"}


def test_s5_5_no_drop_and_default_layout():
    body = {k: v for k, v in CS.items() if k not in ("layout", "simulate_host_drop")}
    s, b, _ = call("POST", "/audit/v1/costream/session", dict(body, session_id="cs-session-nd"))
    assert s == 201 and b["layout"] == "grid_4" and b["active_host"] == "player-alpha-1"
    assert b["handoff_occurred"] is False and b["participant_count"] == 4 and b["active_participants"] == CS["participants"]


def test_s5_5_sole_host_drop_terminates():
    s, b, _ = call("POST", "/audit/v1/costream/session", dict(CS, session_id="cs-session-solo",
                                                               participants=["player-alpha-1"], layout="solo"))
    assert s == 201 and b["status"] == "terminated" and b["active_host"] is None
    assert b["handoff_occurred"] is False and b["participant_count"] == 0


def test_s5_5_identical_replay_200_same_body():
    first = call("POST", "/audit/v1/costream/session", CS)
    again = call("POST", "/audit/v1/costream/session", CS)
    assert (first[0], again[0]) == (201, 200) and first[1] == again[1]


@pytest.mark.parametrize("patch_,field", [
    ({"session_id": 5}, "session_id"), ({"host_player_id": None}, "host_player_id"), ({"participants": []}, "participants"),
    ({"participants": ["player-alpha-1", "player-alpha-1"]}, "participants"), ({"layout": "grid_9"}, "layout"),
    ({"simulate_host_drop": "yes"}, "simulate_host_drop")])
def test_s5_5_schema_errors(patch_, field):
    r = call("POST", "/audit/v1/costream/session", dict(CS, **patch_))
    assert is_error(r, 400, "VALIDATION_ERROR") and field in fields(r), r[1]


def test_s5_5_host_not_in_participants_400():
    r = call("POST", "/audit/v1/costream/session", dict(CS, host_player_id="player-alpha-1b"))
    assert is_error(r, 400, "VALIDATION_ERROR")


def test_s5_5_unknown_participant_404():
    assert is_error(call("POST", "/audit/v1/costream/session", dict(CS, participants=CS["participants"][:3] + ["ghost"])),
                    404, "PLAYER_NOT_FOUND")


@pytest.mark.parametrize("layout,parts,drop,ok", [
    ("solo", 2, False, False), ("solo", 1, False, True), ("grid_2", 3, False, False), ("grid_2", 2, False, True),
    ("grid_2", 3, True, True), ("spotlight", 4, False, True), ("grid_4", 4, False, True)])
def test_s5_5_layout_capacity(layout, parts, drop, ok):
    r = call("POST", "/audit/v1/costream/session", dict(CS, session_id=f"cs-session-{layout}-{parts}-{drop}",
                                                        participants=CS["participants"][:parts], layout=layout,
                                                        simulate_host_drop=drop))
    assert (r[0] == 201) if ok else is_error(r, 400, "UNSUPPORTED_LAYOUT"), r[1]


# ------------------------------------------------------------------ §5.6 QR
def test_s5_6_example_response_exact_and_scan_counts():
    s, b, _ = call("GET", "/audit/v1/qr/match-m1")
    assert s == 200
    assert {k: v for k, v in b.items() if k != "signature"} == {
        "entity_id": "match-m1", "entity_type": "match", "entity_status": "in_progress",
        "short_url": "http://localhost:8080/q/m1-live", "target_route": "/web/matches/match-m1/live",
        "deep_link_uri": "nascon://entity/match-m1", "scan_count": 1,
        "export_formats": {f: f"http://localhost:8080/audit/v1/qr/match-m1/export.{f}" for f in ("svg", "png", "pdf")}}
    assert call("GET", "/audit/v1/qr/match-m1?inspect=true")[1]["scan_count"] == 1
    assert call("GET", "/audit/v1/qr/match-m1")[1]["scan_count"] == 2


@pytest.mark.parametrize("entity,etype,route", [("player-alpha-1", "player", "/web/players/player-alpha-1"),
                                                ("club-alpha-1", "club", "/web/clubs/club-alpha-1")])
def test_s5_6_player_and_club_routes(entity, etype, route):
    b = call("GET", f"/audit/v1/qr/{entity}")[1]
    assert b["entity_type"] == etype and b["target_route"] == route and b["deep_link_uri"] == f"nascon://entity/{entity}"


def test_s5_6_costream_entity_route():
    call("POST", "/audit/v1/costream/session", CS)
    b = call("GET", "/audit/v1/qr/cs-session-101")[1]
    assert b["target_route"] == "/web/costream/cs-session-101"


def test_s5_6_new_match_gets_qr_and_location_header_follows_state():
    mid = new_match()
    b = call("GET", f"/audit/v1/qr/{mid}")[1]
    assert b["target_route"] == f"/web/matches/{mid}/preview"
    short = b["short_url"].rsplit("/", 1)[1]
    assert call("GET", f"/q/{short}", follow=False)[2]["location"].endswith(f"/web/matches/{mid}/preview")
    event(mid, "match_start")
    assert call("GET", f"/q/{short}", follow=False)[2]["location"].endswith(f"/web/matches/{mid}/live")
    event(mid, "match_end")
    assert call("GET", f"/q/{short}", follow=False)[2]["location"].endswith(f"/web/matches/{mid}/vod")


def test_s5_6_unknown_entity_404():
    assert is_error(call("GET", "/audit/v1/qr/match-unknown"), 404, "QR_NOT_FOUND")
    assert is_error(call("GET", "/audit/v1/qr/player-unknown"), 404, "QR_NOT_FOUND")


def test_s5_6_svg_encodes_short_url():
    s, b, h = call("GET", "/audit/v1/qr/match-m1/export.svg")
    assert s == 200 and h["content-type"].startswith("image/svg+xml") and b.lstrip()[:4] in (b"<svg", b"<?xm")
    # Re-encode the short_url independently (segno, inside the api image) and compare the QR module matrix.
    script = ("import segno,urllib.request,re;"
              "svg=urllib.request.urlopen('http://localhost:8080/audit/v1/qr/match-m1/export.svg').read();"
              "ref=segno.make('http://localhost:8080/q/m1-live',error='m');"
              "import io;buf=io.BytesIO();ref.save(buf,kind='svg',scale=8,border=4,xmldecl=True);"
              "print('MATCH' if buf.getvalue()==svg else 'DIFF')")
    out = subprocess.run(["docker", "compose", "exec", "-T", "api", "python", "-c", script], cwd=REPO,
                         capture_output=True, text=True, timeout=60).stdout.strip()
    assert out == "MATCH", out


# ------------------------------------------------------------------ §5.7 guest boundary + cart merge
def test_s5_7_example_response_exact():
    s, b, _ = call("POST", "/audit/v1/guest/cart-merge", MERGE)
    assert s == 200 and {k: v for k, v in b.items() if k != "signature"} == {
        "guest_token": GUEST, "write_block_verified": True, "write_rejection_code": 403, "cart_merged": True,
        "active_cart": {"user_id": "player-alpha-1", "currency": "PKR", "total_items": 1, "subtotal_minor": 450000,
                        "items": [{"variant_id": "var-jersey-001-L", "quantity": 1, "unit_price_minor": 450000}]}}


@pytest.mark.parametrize("patch_,field", [
    ({"guest_token": "anon_123"}, "guest_token"), ({"guest_token": ""}, "guest_token"),
    ({"registered_user_id": 7}, "registered_user_id"), ({"guest_cart": []}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}] * 11}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 0}]}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": "1"}]}, "guest_cart"),
    ({"test_write_block": "true"}, "test_write_block")])
def test_s5_7_schema_errors(patch_, field):
    r = call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, **patch_))
    assert is_error(r, 400, "VALIDATION_ERROR") and field in fields(r)


def test_s5_7_existence_errors():
    assert is_error(call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, registered_user_id="nobody")), 404,
                    "PLAYER_NOT_FOUND")
    r = call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, guest_cart=[{"variant_id": "var-nope", "quantity": 1}]))
    assert is_error(r, 404, "VARIANT_NOT_FOUND")


def test_s5_7_out_of_stock_has_variant_id():
    r = call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, guest_cart=[{"variant_id": "var-jersey-001-L", "quantity": 6}]))
    assert is_error(r, 409, "OUT_OF_STOCK") and r[1]["error"]["details"]["variant_id"] == "var-jersey-001-L"


def test_s5_7_write_block_false_reports_null_code():
    b = call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, test_write_block=False))[1]
    assert b["write_block_verified"] is False and b["write_rejection_code"] is None


def test_s5_7_sums_existing_cart_quantities():
    call("POST", "/audit/v1/guest/cart-merge", MERGE)
    b = call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, guest_token="guest_second_tok",
                                                       guest_cart=[{"variant_id": "var-jersey-001-L", "quantity": 2},
                                                                   {"variant_id": "var-jersey-001-M", "quantity": 1}]))[1]
    items = {i["variant_id"]: i["quantity"] for i in b["active_cart"]["items"]}
    assert items == {"var-jersey-001-L": 3, "var-jersey-001-M": 1} and b["active_cart"]["total_items"] == 4
    assert b["active_cart"]["subtotal_minor"] == 4 * 450000


def test_s5_7_reuse_after_merge_is_409():
    call("POST", "/audit/v1/guest/cart-merge", MERGE)
    assert is_error(call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, registered_user_id="player-alpha-2")), 409,
                    "GUEST_TOKEN_ALREADY_MERGED")
    r = call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, guest_cart=[{"variant_id": "var-jersey-001-L", "quantity": 2}]))
    assert is_error(r, 409, "GUEST_TOKEN_ALREADY_MERGED")


@pytest.mark.parametrize("path", ["/api/v1/chat", "/audit/v1/checkout", "/audit/v1/events"])
def test_s5_7_direct_write_enforcement(path):
    assert is_error(call("POST", path, {"x": 1}, token=GUEST), 403, "GUEST_WRITE_FORBIDDEN")


# ------------------------------------------------------------------ §5.8 moderation + DLQ
def test_s5_8_example_response_exact():
    s, b, _ = call("POST", "/audit/v1/moderation/test", MOD)
    assert s == 200 and {k: v for k, v in b.items() if k != "signature"} == {
        "chat_room_id": "chat-cs-session-101",
        "filtered_messages": [
            {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary", "flagged": False,
             "reason": None},
            {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream *** now!",
             "flagged": True, "reason": "profanity_leetspeak"}],
        "kicked_users": ["user-spammer"], "muted_users": ["user-flooder"],
        "dlq_status": {"queue_depth": 0, "undelivered_events": []}}


@pytest.mark.parametrize("word", ["badword", "b@d_w0rd", "bad_word", "porn", "p0rn", "p.0.r.n", "scam", "sc@m", "s!c@m",
                                  "fuck", "f*u*c*k", "shit", "bitch", "asshole", "a$$h0le", "idiot_spam"])
def test_s5_8_dictionary_and_obfuscations_masked(word):
    b = call("POST", "/audit/v1/moderation/test", {"chat_room_id": "chat-t", "check_dlq": False, "incoming_messages": [
        {"message_id": "m", "sender": "u", "text": f"you {word} there"}]})[1]
    m = b["filtered_messages"][0]
    assert m["text"] == "you *** there" and m["flagged"] is True and m["reason"] == "profanity_leetspeak"
    assert b["kicked_users"] == ["u"]


@pytest.mark.parametrize("text", ["AAAA", "goooool aaaa", "what???", "wow!!!", "nooOO oo", "zzZZ"])
def test_s5_8_flood_dropped_and_muted(text):
    b = call("POST", "/audit/v1/moderation/test", {"chat_room_id": "chat-t", "check_dlq": False, "incoming_messages": [
        {"message_id": "m", "sender": "flooder", "text": text}]})[1]
    if re.search(r"(.)\1{3,}", text, re.I) or re.search(r"[!?]{3,}", text):
        assert b["filtered_messages"] == [] and b["muted_users"] == ["flooder"]


def test_s5_8_kicked_dedup_in_violation_order():
    msgs = [{"message_id": f"m{i}", "sender": s, "text": "scam"} for i, s in enumerate(["b", "a", "b", "c", "a"])]
    b = call("POST", "/audit/v1/moderation/test", {"chat_room_id": "chat-t", "incoming_messages": msgs, "check_dlq": False})[1]
    assert b["kicked_users"] == ["b", "a", "c"]


def test_s5_8_dlq_enqueue_and_persist_until_reset():
    b = call("POST", "/audit/v1/moderation/test", dict(MOD, simulate_failed_notifications=3))[1]
    assert b["dlq_status"]["queue_depth"] == 3 and len(b["dlq_status"]["undelivered_events"]) == 3
    b = call("POST", "/audit/v1/moderation/test", MOD)[1]
    assert b["dlq_status"]["queue_depth"] == 3                       # persistent, not per request
    call("POST", "/audit/v1/reset")
    assert call("POST", "/audit/v1/moderation/test", MOD)[1]["dlq_status"]["queue_depth"] == 0


# ------------------------------------------------------------------ §5.9
def test_s5_9_metrics_and_privacy_shapes():
    s, body, h = call("GET", "/metrics")
    assert s == 200 and h["content-type"].startswith("text/plain; version=0.0.4")
    for name in ("nascon_active_ws_connections", "nascon_active_streams_total", "nascon_stream_bitrate_kbps",
                 "nascon_dlq_depth", "nascon_qr_scans_total"):
        assert re.search(rf"^{name} [0-9.]+$", body.decode(), re.M), name
    assert call("DELETE", "/audit/v1/privacy/user/player-alpha-1")[:2] == (200, {
        "user_id": "player-alpha-1", "status": "anonymized", "pii_retained": False, "tokens_wiped": True})


# ------------------------------------------------------------------ §6 QA harness artefacts
def test_s6_2_1_compose_selenium_rules():
    import yaml
    d = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    hub = d["selenium-hub"]
    assert hub["container_name"] == "nascon-selenium-hub" and {"4444:4444", "4442:4442", "4443:4443"} <= set(hub["ports"])
    for n in ("node-chrome-1", "node-chrome-2", "node-firefox"):
        env = set(d[n]["environment"])
        assert d[n]["shm_size"] in ("1gb", "2gb") and "selenium-hub" in d[n]["depends_on"]
        assert {"SE_EVENT_BUS_HOST=selenium-hub", "SE_EVENT_BUS_PUBLISH_PORT=4442", "SE_EVENT_BUS_SUBSCRIBE_PORT=4443",
                "SE_NODE_MAX_SESSIONS=2", "SE_START_VNC=false"} <= env, n


def test_s6_2_3_selenium_suite_has_three_required_tests():
    src = (REPO / "tests/selenium/test_guest_grid.py").read_text(encoding="utf-8")
    assert len(re.findall(r"^def test_", src, re.M)) >= 3 and "/q/m1-live" in src and "progressive-auth-modal" in src


def test_s6_3_manifest_intent_filter_and_appium_suite():
    man = (REPO / "mobile/android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    for needle in ("android.intent.action.VIEW", "android.intent.category.DEFAULT", "android.intent.category.BROWSABLE",
                   'android:scheme="nascon"'):
        assert needle in man, needle
    src = (REPO / "tests/appium/test_mobile_deeplink.py").read_text(encoding="utf-8")
    assert "nascon://entity/match-m1" in src and "nascon://stream/cs-session-101" in src and "4723" in src
    assert "/web/costream/cs-session-101" in src                      # cross-surface test


def test_s6_3_appium_status_when_running():
    try:
        with urllib.request.urlopen("http://localhost:4723/status", timeout=3) as r:
            assert json.loads(r.read())["value"]["ready"] is True
    except OSError:
        pytest.skip("Appium runs on the phone laptop (Huzaifa), not this one")


def test_s6_4_k6_profile_is_exact():
    js = (REPO / "tests/k6_load.js").read_text(encoding="utf-8")
    for needle in ("vus: 500", "vus: 50", "duration: '15s'", "exec: 'viewStream'", "exec: 'postChat'",
                   "http_req_failed: ['rate==0.00']", "http_req_duration: ['p(95)<800']",
                   "http://localhost:8080/audit/v1/qr/match-m1?inspect=true",
                   "http://localhost:8080/audit/v1/moderation/test", "chat-cs-session-101", "check_dlq: false",
                   "sleep(0.1)", "sleep(0.2)"):
        assert needle in js, needle


def test_s6_4_k6_summary_report_passed_thresholds():
    s = json.loads((REPO / "tests/reports/k6-summary.json").read_text(encoding="utf-8"))["metrics"]
    assert s["http_req_failed"]["value"] == 0 if "value" in s["http_req_failed"] else s["http_req_failed"]["rate"] == 0
    assert s["http_req_duration"]["p(95)"] < 800


# ------------------------------------------------------------------ §7.2 coverage file
def test_s7_2_coverage_day2_keys_and_bar():
    cov = json.loads((REPO / "COVERAGE_DAY2.json").read_text(encoding="utf-8"))
    assert set(cov) == {"streaming", "costream", "qr_guest", "moderation_dlq", "observability"}
    assert all(isinstance(v, (int, float)) and v >= 85 for v in cov.values()), cov


# ------------------------------------------------------------------ §8 hidden scenarios
def test_s8_scenario_1_host_drop_keeps_chat_room_and_url():
    nodrop = call("POST", "/audit/v1/costream/session", dict(CS, session_id="cs-session-202", simulate_host_drop=False))[1]
    drop = call("POST", "/audit/v1/costream/session", dict(CS, session_id="cs-session-203"))[1]
    assert drop["active_host"] == CS["participants"][1] and drop["handoff_occurred"] is True
    assert drop["participant_count"] == 3 and drop["chat_room_id"] == "chat-cs-session-203"
    assert nodrop["composite_playback_url"].endswith("/costream/cs-session-202/index.m3u8")


@needs_salt
@pytest.mark.parametrize("transition,route", [("completed", "/web/matches/match-m1/vod"),
                                              ("postponed", "/web/matches/match-m1/notice?state=postponed")])
def test_s8_scenario_2_qr_mutation(transition, route):
    before = call("GET", "/audit/v1/qr/match-m1")[1]
    if transition == "completed":
        event("match-m1", "match_end")
    else:
        org = login("organizer@nascon.test")
        assert call("POST", "/api/v1/matches/match-m1/status", {"to": "postponed"}, token=org)[0] in (200, 201)
    after = call("GET", "/audit/v1/qr/match-m1")[1]
    assert after["short_url"] == before["short_url"] and after["target_route"] == route
    assert after["signature"] != before["signature"]
    assert after["signature"] == sign_day2(SALT2, "match-m1", {"entity_id": "match-m1", "short_url": after["short_url"],
                                                               "target_route": route})


def test_s8_scenario_3_ten_parallel_moderators():
    body = {"chat_room_id": "chat-cs-session-101", "check_dlq": True, "incoming_messages": [
        {"message_id": "x", "sender": "user-spammer", "text": "sc@m"}]}
    out = []
    barrier = threading.Barrier(10)

    def go():
        barrier.wait()
        out.append(call("POST", "/audit/v1/moderation/test", body))
    ts = [threading.Thread(target=go) for _ in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(r[0] == 200 and r[1]["kicked_users"] == ["user-spammer"] for r in out)
    assert len({r[1]["dlq_status"]["queue_depth"] for r in out}) == 1


def test_s8_scenario_4_double_merge_no_double_reservation():
    stock = call("GET", "/audit/v1/inventory/var-jersey-001-L")[1]
    a = call("POST", "/audit/v1/guest/cart-merge", MERGE)
    b = call("POST", "/audit/v1/guest/cart-merge", MERGE)
    assert (a[0], b[0]) == (200, 200) and b[1]["active_cart"]["total_items"] == 1 and a[1] == b[1]
    assert call("GET", "/audit/v1/inventory/var-jersey-001-L")[1] == stock


# ------------------------------------------------------------------ Appendix A vectors
def test_appendix_a_vector_1_and_2_reference_function():
    v1 = sign_day2(REF_SALT, "sk_live_9f83a1b2c3d4e5f6", {"action": "rotate", "player_id": "player-alpha-1",
                                                          "status": "active", "stream_key": "sk_live_9f83a1b2c3d4e5f6"})
    assert v1 == "9bd054eb746844b4701c6f158209c315ef2b16f392efd733bdf0715940610289"
    msg = "sk_live_101|" + canonical({"action": "rotate", "player_id": "player-alpha-1"})
    assert msg == 'sk_live_101|{"action":"rotate","player_id":"player-alpha-1"}'


# ------------------------------------------------------------------ Appendix B: every Part II error code is reachable
def test_appendix_b_every_error_code():
    viewer = login("viewer@nascon.test")
    k = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})[1]["stream_key"]
    call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})
    call("POST", "/audit/v1/guest/cart-merge", MERGE)
    cases = [
        (call("POST", "/audit/v1/stream/key", {"action": "nope", "player_id": "player-alpha-1"}), 400, "VALIDATION_ERROR"),
        (call("POST", "/audit/v1/costream/session", dict(CS, layout="solo", simulate_host_drop=False)), 400,
         "UNSUPPORTED_LAYOUT"),
        (call("GET", "/api/v1/me"), 401, "UNAUTHENTICATED"),
        (call("POST", "/api/v1/chat", {}, token=GUEST), 403, "GUEST_WRITE_FORBIDDEN"),
        (call("POST", "/audit/v1/rbac/tenants", {}, token=viewer), 403, "FORBIDDEN"),
        (call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "ghost"}), 404, "PLAYER_NOT_FOUND"),
        (call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-beta-2"}), 404, "STREAM_NOT_FOUND"),
        (call("GET", "/audit/v1/qr/club-ghost"), 404, "QR_NOT_FOUND"),
        (call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, guest_token="guest_x2",
                                                         guest_cart=[{"variant_id": "v-ghost", "quantity": 1}])), 404,
         "VARIANT_NOT_FOUND"),
        (call("POST", "/audit/v1/costream/session", dict(CS, participants=CS["participants"] + ["player-alpha-1b"])),
         409, "COSTREAM_SESSION_FULL"),
        (call("POST", "/audit/v1/stream/publish", {"stream_key": k}), 409, "KEY_REVOKED"),
        (call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, registered_user_id="player-alpha-2")), 409,
         "GUEST_TOKEN_ALREADY_MERGED"),
        (call("POST", "/audit/v1/guest/cart-merge", dict(MERGE, guest_token="guest_x3",
                                                         guest_cart=[{"variant_id": "var-jersey-001-M", "quantity": 2}])),
         409, "OUT_OF_STOCK"),
    ]
    for r, status, err in cases:
        assert is_error(r, status, err), (err, r[0], r[1])


def test_appendix_b_rate_limited_on_api_v1_and_chat_flood():
    statuses = [call("GET", "/api/v1/ping")[0] for _ in range(130)]
    assert 429 in statuses
    r = next(call("GET", "/api/v1/ping") for _ in range(1))
    assert r[0] == 429 and code(r) == "RATE_LIMITED" and "retry-after" in r[2]


# ------------------------------------------------------------------ Appendix C checklist (web part)
def test_appendix_c_live_page_has_all_nine_testids():
    html = call("GET", "/web/matches/match-m1/live")[1].decode()
    assert all(f'data-testid="{t}"' in html for t in TESTIDS)
