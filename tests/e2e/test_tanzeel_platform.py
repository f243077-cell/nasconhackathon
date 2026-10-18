"""Live end-to-end tests for the Part II platform areas that tools/day2_check.py, tools/smoke_day2_social.py,
tools/ws_latency.py and the Selenium suite do not cover: the real media pipeline (RTMP publish, auth hook, revoke
kick, HLS, recording -> MinIO -> VOD), guest token lifecycle and the full write-guard surface, guest-readable and
member routes, SSE, QR routing/exports/telemetry, metrics values, privacy erasure side effects, web serving,
rate-limit exemptions and the stack itself.

Run against a live stack (each test resets it first):
    DAY2_SALT=<s2> pytest tests/e2e -q --junitxml=tests/reports/backend-e2e-report.xml
Media tests need ffmpeg on PATH; DB-level checks need `docker compose` in the repo root.
"""
import asyncio
import io
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
import websockets

BASE = os.environ.get("API_URL", "http://localhost:8080").rstrip("/")
GRID = os.environ.get("GRID_URL", "http://localhost:4444").rstrip("/")
HLS = os.environ.get("HLS_URL", "http://localhost:8888").rstrip("/")
RTMP = os.environ.get("RTMP_URL", "rtmp://localhost:1935")
REPO = Path(__file__).resolve().parents[2]
PASSWORD = "Nascon@26"
GUEST = "guest_anon_tok_7721"
FFMPEG = shutil.which("ffmpeg")
DOCKER = shutil.which("docker")
TESTIDS = ("guest-video-player", "live-score-banner", "pinned-merch-card", "add-to-guest-cart-btn", "guest-cart-count",
           "chat-message-list", "chat-input-field", "chat-send-btn", "progressive-auth-modal")


# ------------------------------------------------------------------ helpers
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def call(method, path, body=None, token=None, headers=None, raw=None, follow=True, timeout=20):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(path if path.startswith("http") else BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, _decode(r), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, _decode(e), {k.lower(): v for k, v in e.headers.items()}


def _decode(r):
    raw = r.read()
    if "json" in (r.headers.get("Content-Type") or "") and raw:
        return json.loads(raw)
    return raw


def code(resp):
    body = resp[1]
    return body.get("error", {}).get("code") if isinstance(body, dict) else None


def login(email):
    s, b, _ = call("POST", "/api/v1/auth/login", {"email": email, "password": PASSWORD})
    assert s == 200, (email, s, b)
    return b["token"]


def metric(name):
    s, body, _ = call("GET", "/metrics")
    assert s == 200
    m = re.search(rf"^{name} ([0-9.eE+-]+)$", body.decode(), re.M)
    assert m, f"{name} missing from /metrics"
    return float(m.group(1))


def psql(sql):
    out = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "nascon", "-d", "nascon",
                          "-tAc", sql], cwd=REPO, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def event(match_id, etype, payload=None):
    s, b, _ = call("POST", "/audit/v1/events", {"event_id": f"e2e-{uuid.uuid4().hex[:12]}", "match_id": match_id,
                                                 "type": etype, "payload": payload or {}})
    assert s in (200, 201), (etype, s, b)
    return b


def new_match(league="league-alpha-1"):
    mid = f"match-e2e-{uuid.uuid4().hex[:8]}"
    event(mid, "match_init", {"sport_id": "football", "home_team_id": "club-alpha-1", "away_team_id": "club-alpha-2",
                              "league_id": league})
    return mid


def new_key(player="player-alpha-2"):
    s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": player})
    assert s == 201, b
    return b["stream_key"]


def publisher(key, seconds=40):
    """ffmpeg test pattern published over RTMP to live/<key>."""
    return subprocess.Popen(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast",
         "-tune", "zerolatency", "-g", "15", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
         "-f", "flv", f"{RTMP}/live/{key}"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def wait_until(fn, timeout, step=0.25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def hls_ready(key):
    try:
        with urllib.request.urlopen(f"{HLS}/live/{key}/index.m3u8", timeout=3) as r:
            return r.status == 200 and b"#EXTM3U" in r.read()
    except Exception:  # noqa: BLE001
        return False


needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")
needs_docker = pytest.mark.skipif(DOCKER is None, reason="docker not on PATH")


@pytest.fixture(autouse=True)
def reset():
    s, _, _ = call("POST", "/audit/v1/reset")
    assert s == 200
    yield


# ------------------------------------------------------------------ 1. stack and infrastructure
def test_health_ok_and_checks_db_redis_media():
    s, b, _ = call("GET", "/health")
    assert (s, b) == (200, {"status": "ok"})


def test_selenium_grid_ready_with_three_nodes():
    s, b, _ = call("GET", f"{GRID}/status")
    assert s == 200 and b["value"]["ready"] is True and len(b["value"]["nodes"]) >= 3


def test_costream_composite_playback_is_alive():
    """FR-3.3 / scenario 1: the composite URL serves HLS on demand (FFmpeg started and stopped by MediaMTX)."""
    s, b, _ = call("POST", "/audit/v1/costream/session", {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
                   "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"],
                   "layout": "grid_4", "simulate_host_drop": True})
    url = b["composite_playback_url"].replace("http://localhost:8888", HLS)

    def alive():
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                return r.status == 200 and b"#EXTM3U" in r.read()
        except Exception:  # noqa: BLE001
            return False
    assert wait_until(alive, 30), url


@pytest.mark.parametrize("port", [1935, 8888, 8889, 4444, 8080])
def test_mandatory_ports_accept_connections(port):
    with socket.create_connection(("localhost", port), timeout=3):
        pass


@needs_docker
def test_every_container_running_and_healthchecked_ones_healthy():
    out = subprocess.run(["docker", "compose", "ps", "--format", "{{.Service}}|{{.State}}|{{.Health}}"], cwd=REPO,
                         capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
    rows = dict((r.split("|")[0], r.split("|")[1:]) for r in out)
    for svc in ("postgres", "redis", "minio", "api", "worker", "mediamtx", "selenium-hub", "node-chrome-1",
                "node-chrome-2", "node-firefox"):
        assert svc in rows and rows[svc][0] == "running", (svc, rows.get(svc))
        assert rows[svc][1] in ("", "healthy"), (svc, rows[svc])


def test_compose_forwards_both_salts_and_grid_rules():
    text = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert "DAY1_SALT: ${DAY1_SALT}" in text and "DAY2_SALT: ${DAY2_SALT}" in text
    assert text.count('shm_size: "1gb"') >= 3 and text.count("SE_START_VNC=false") >= 3


# ------------------------------------------------------------------ 2. media pipeline (FR-3.2)
def test_stream_key_contract_extras():
    s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "generate", "player_id": "player-alpha-2"})
    assert s == 201 and b["label"] == "default" and re.fullmatch(r"sk_live_[a-f0-9]{16}", b["stream_key"])
    key = b["stream_key"]
    assert b["ingest_endpoints"] == {"rtmp": f"rtmp://localhost:1935/live/{key}",
                                     "webrtc": f"http://localhost:8889/live/{key}/whip"}
    assert b["playback_url"] == f"http://localhost:8888/live/{key}/index.m3u8"
    # a second generate replaces the first key: the old one can no longer publish
    key2 = new_key()
    assert key2 != key
    r = call("POST", "/audit/v1/stream/publish", {"stream_key": key})
    assert r[0] == 409 and code(r) == "KEY_REVOKED"
    assert call("POST", "/audit/v1/stream/publish", {"stream_key": key2})[0] == 200
    r = call("POST", "/audit/v1/stream/publish", {"stream_key": "sk_live_ffffffffffffffff"})
    assert r[0] == 404 and code(r) == "STREAM_NOT_FOUND"
    # revoke twice: the second has no active key left
    assert call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})[0] == 200
    r = call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})
    assert r[0] == 404 and code(r) == "STREAM_NOT_FOUND"


def test_media_auth_hook_rules():
    key = new_key()
    hook = "/internal/media/auth"
    assert call("POST", hook, {"action": "publish", "path": f"live/{key}"})[0] == 200
    assert call("POST", hook, {"action": "publish", "path": "live/sk_live_0000000000000000"})[0] >= 400
    assert call("POST", hook, {"action": "read", "path": f"live/{key}"})[0] == 200   # guests may watch
    call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})
    assert call("POST", hook, {"action": "publish", "path": f"live/{key}"})[0] >= 400


@needs_ffmpeg
def test_rtmp_publish_hls_playback_metrics_then_revoke_kicks_within_2s():
    base = metric("nascon_active_streams_total")   # an on-demand co-stream composite may still be closing
    key = new_key()
    proc = publisher(key)
    try:
        assert wait_until(lambda: hls_ready(key), 20), "HLS manifest never became available"
        assert wait_until(lambda: metric("nascon_active_streams_total") >= base + 1, 10)
        metric("nascon_stream_bitrate_kbps")
        time.sleep(1.5)
        assert wait_until(lambda: metric("nascon_stream_bitrate_kbps") > 0, 10), "bitrate stayed 0 while publishing"
        t0 = time.monotonic()
        s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})
        assert s == 200 and b["status"] == "revoked"
        proc.wait(timeout=10)
        cut = time.monotonic() - t0
        assert cut <= 2.0, f"publisher still connected {cut:.2f} s after revoke"
        assert wait_until(lambda: metric("nascon_active_streams_total") <= base, 10)
    finally:
        if proc.poll() is None:
            proc.kill()


@needs_ffmpeg
def test_revoked_key_cannot_publish():
    key = new_key()
    call("POST", "/audit/v1/stream/key", {"action": "revoke", "player_id": "player-alpha-2"})
    proc = publisher(key, seconds=10)
    try:
        rc = proc.wait(timeout=15)
        assert rc != 0, "ffmpeg published with a revoked key"
        assert not hls_ready(key)
    finally:
        if proc.poll() is None:
            proc.kill()


@needs_ffmpeg
def test_rotate_cuts_old_key_publisher():
    key = new_key()
    proc = publisher(key)
    try:
        assert wait_until(lambda: hls_ready(key), 20)
        t0 = time.monotonic()
        s, b, _ = call("POST", "/audit/v1/stream/key", {"action": "rotate", "player_id": "player-alpha-2"})
        assert s == 200 and b["stream_key"] != key and b["status"] == "active"
        proc.wait(timeout=10)
        assert time.monotonic() - t0 <= 2.0
    finally:
        if proc.poll() is None:
            proc.kill()


@needs_ffmpeg
def test_recording_lands_in_minio_and_is_indexed_as_vod():
    key = new_key()
    proc = publisher(key, seconds=6)
    assert proc.wait(timeout=30) == 0

    def vod():
        s, b, _ = call("GET", "/api/v1/athletes/player-alpha-2")
        return next((v for v in b.get("vods", []) if v["stream_key"] == key), None) if s == 200 else None
    v = wait_until(vod, 20, step=0.5)
    assert v, "no VOD indexed within 20 s of the stream ending"
    assert v["recording_path"].startswith(f"s3://vods/live/{key}/")
    s, body, h = call("GET", v["playback_url"].replace("http://localhost:8080", BASE))
    assert s == 200 and h["content-type"] == "video/mp4" and len(body) > 1000
    assert b"ftyp" in body[:32], "VOD object is not an MP4"


def test_vod_media_unknown_is_404_and_recorded_hook_locked():
    r = call("GET", "/api/v1/vods/999999/media")
    assert r[0] == 404 and code(r) == "VOD_NOT_FOUND"
    assert call("POST", "/internal/media/recorded", {"path": "live/x", "segment_path": "/recordings/x"})[0] in (403, 404)


# ------------------------------------------------------------------ 3. guest token + write guard (FR-4.2, FR-4.3)
def test_guest_token_issue_shape_and_expiry():
    s, b, _ = call("POST", "/api/v1/guest/token")
    assert s == 201 and re.fullmatch(r"guest_anon_tok_[a-f0-9]{16}", b["guest_token"])
    assert b["read_only"] is True and b["role"] == "guest" and b["expires_in"] > 0
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", b["expires_at"])
    # issuing works with a guest bearer too (that route is exempt from the write guard)
    assert call("POST", "/api/v1/guest/token", token=b["guest_token"])[0] == 201


GUARDED = [
    ("POST", "/api/v1/chat"), ("POST", "/api/v1/checkout"), ("POST", "/api/v1/events"),
    ("POST", "/api/v1/roster/transfer"), ("POST", "/api/v1/sync"), ("POST", "/api/v1/matches/match-m1/pin"),
    ("POST", "/api/v1/matches/match-m1/status"), ("POST", "/api/v1/orders/ord-x/status"), ("POST", "/api/v1/cart"),
    ("POST", "/api/v1/athletes/player-alpha-1/follow"), ("DELETE", "/api/v1/athletes/player-alpha-1/follow"),
    ("POST", "/api/v1/costream/sessions"), ("POST", "/api/v1/stream/key"),
    ("POST", "/audit/v1/checkout"), ("POST", "/audit/v1/events"), ("POST", "/audit/v1/roster/transfer"),
    ("POST", "/audit/v1/offline-sync"),
]


@pytest.mark.parametrize("method,path", GUARDED)
def test_guest_write_forbidden_everywhere_before_validation(method, path):
    for token in (GUEST, "guest_anon_tok_" + uuid.uuid4().hex[:16]):
        r = call(method, path, raw=b"{not json", token=token)
        assert r[0] == 403 and code(r) == "GUEST_WRITE_FORBIDDEN", (path, r[0], r[1])
        assert r[1]["error"]["details"]["guest_token"] == token


def test_member_writes_are_not_caught_by_guest_guard():
    tok = login("player@nascon.test")
    s, b, _ = call("POST", "/api/v1/chat", {"chat_room_id": "chat-match-m1", "text": "member hello"}, token=tok)
    assert s in (200, 201) and b["delivered"] is True


@needs_docker
def test_expired_guest_token_cannot_merge_but_seeded_one_can():
    old = "guest_anon_tok_e2eexpired0001"
    psql(f"INSERT INTO guest_tokens (guest_token, status, created_at) VALUES ('{old}','active','2020-01-01T00:00:00Z')")
    body = {"registered_user_id": "player-alpha-1", "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}]}
    r = call("POST", "/audit/v1/guest/cart-merge", dict(body, guest_token=old))
    assert r[0] == 409 and code(r) == "GUEST_TOKEN_EXPIRED"
    r = call("POST", "/audit/v1/guest/cart-merge", dict(body, guest_token=GUEST))
    assert r[0] == 200 and r[1]["active_cart"]["total_items"] == 1


# ------------------------------------------------------------------ 4. guest-readable + member routes
@pytest.mark.parametrize("token", [None, GUEST])
def test_guest_reads_match_athlete_and_chat(token):
    s, b, _ = call("GET", "/api/v1/matches/match-m1", token=token)
    assert s == 200 and b["status"] == "in_progress" and (b["home"]["score"], b["away"]["score"]) == (1, 0)
    assert b["pinned_product"]["product_id"] == "prod-jersey-001"
    s, b, _ = call("GET", "/api/v1/athletes/player-alpha-1", token=token)
    assert s == 200 and b["athlete_id"] == "player-alpha-1" and "follower_count" in b and "vods" in b
    s, b, _ = call("GET", "/api/v1/chat?room_id=chat-match-m1", token=token)
    assert s == 200 and b["chat_room_id"] == "chat-match-m1"


def test_member_chat_masks_sequences_and_reaches_match_socket():
    tok = login("player@nascon.test")

    async def run():
        async with websockets.connect(BASE.replace("http", "ws", 1) + "/ws/matches/match-m1") as ws:
            await asyncio.wait_for(ws.recv(), 5)           # snapshot
            await asyncio.sleep(0.3)
            r = await asyncio.to_thread(call, "POST", "/api/v1/chat",
                                        {"chat_room_id": "chat-match-m1", "text": "this is a sc@m"}, tok)
            assert r[0] in (200, 201) and r[1]["message"]["text"] == "this is a ***" and r[1]["message"]["flagged"] is True
            end = time.monotonic() + 2
            while time.monotonic() < end:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 2))
                if "chat_message" in json.dumps(msg):
                    return msg
            return None
    assert asyncio.run(run()), "chat message never reached /ws/matches/match-m1"
    time.sleep(2.1)
    call("POST", "/api/v1/chat", {"chat_room_id": "chat-match-m1", "text": "second"}, token=tok)
    s, b, _ = call("GET", "/api/v1/chat?room_id=chat-match-m1")
    seqs = [m["seq"] for m in b["messages"]]
    assert len(seqs) >= 2 and seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_member_cart_route_merges_guest_cart():
    tok = login("player@nascon.test")
    s, b, _ = call("POST", "/api/v1/guest/token")
    g = b["guest_token"]
    items = [{"variant_id": "var-jersey-001-L", "quantity": 2}]
    s1, b1, _ = call("POST", "/api/v1/cart", {"guest_token": g, "items": items}, token=tok)
    assert s1 == 200 and b1["active_cart"]["total_items"] == 2 and b1["active_cart"]["user_id"] == "player-alpha-1"
    s2, b2, _ = call("POST", "/api/v1/cart", {"guest_token": g, "items": items}, token=tok)
    assert s2 == 200 and b2["active_cart"]["total_items"] == 2           # replay never double-adds


def test_sse_stream_delivers_score_update():
    got = {}

    def reader():
        req = urllib.request.Request(BASE + "/api/v1/matches/match-m1/stream")
        with urllib.request.urlopen(req, timeout=10) as r:
            for line in r:
                line = line.decode().strip()
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    if data.get("type") == "snapshot":
                        got["snapshot"] = time.monotonic()
                    elif "home_score" in json.dumps(data):
                        got["update"] = (time.monotonic(), data)
                        return
    t = threading.Thread(target=reader, daemon=True)
    t.start()
    assert wait_until(lambda: "snapshot" in got, 5)
    time.sleep(0.3)
    t0 = time.monotonic()
    event("match-m1", "score", {"team_id": "club-alpha-1", "event_type": "goal"})
    t.join(5)
    assert "update" in got, "no SSE update after a score event"
    assert got["update"][0] - t0 < 0.5


# ------------------------------------------------------------------ 5. QR routing, exports, telemetry (FR-4.1, NFR-9)
@pytest.mark.parametrize("code_,location", [("m1-live", "/web/matches/match-m1/live"),
                                            ("p-alpha-1", "/web/players/player-alpha-1"),
                                            ("c-alpha-1", "/web/clubs/club-alpha-1")])
def test_short_links_redirect_302(code_, location):
    s, _, h = call("GET", f"/q/{code_}", follow=False)
    assert s == 302 and h["location"].endswith(location)


def test_unknown_short_code_and_entity_are_404():
    r = call("GET", "/q/does-not-exist", follow=False)
    assert r[0] == 404 and code(r) == "QR_NOT_FOUND"
    r = call("GET", "/audit/v1/qr/match-nope/export.svg")
    assert r[0] == 404 and code(r) == "QR_NOT_FOUND"


def test_target_route_for_every_match_state():
    org = login("organizer@nascon.test")
    up = new_match()
    s, b, _ = call("GET", f"/audit/v1/qr/{up}?inspect=true")
    assert s == 200 and b["target_route"] == f"/web/matches/{up}/preview" and b["entity_status"] == "upcoming"
    short = b["short_url"]
    for state in ("postponed", "cancelled"):
        mid = new_match()
        s, b, _ = call("POST", f"/api/v1/matches/{mid}/status", {"to": state}, token=org)
        assert s in (200, 201), b
        s, b, _ = call("GET", f"/audit/v1/qr/{mid}?inspect=true")
        assert b["target_route"] == f"/web/matches/{mid}/notice?state={state}"
    ab = new_match()
    event(ab, "match_start")
    call("POST", f"/api/v1/matches/{ab}/status", {"to": "abandoned"}, token=org)
    assert call("GET", f"/audit/v1/qr/{ab}?inspect=true")[1]["target_route"] == f"/web/matches/{ab}/notice?state=abandoned"
    event(up, "match_start")
    s, b, _ = call("GET", f"/audit/v1/qr/{up}?inspect=true")
    assert b["target_route"] == f"/web/matches/{up}/live" and b["short_url"] == short     # short URL never changes


def test_exports_are_valid_files():
    from pypdf import PdfReader
    s, b, h = call("GET", "/audit/v1/qr/match-m1/export.svg")
    assert s == 200 and h["content-type"].startswith("image/svg+xml") and (b.lstrip()[:4] in (b"<svg", b"<?xm"))
    s, b, h = call("GET", "/audit/v1/qr/player-alpha-1/export.png")
    assert s == 200 and h["content-type"] == "image/png" and b[:8] == b"\x89PNG\r\n\x1a\n"
    s, b, h = call("GET", "/audit/v1/qr/club-alpha-1/export.pdf")
    assert s == 200 and h["content-type"] == "application/pdf" and b[:5] == b"%PDF-"
    text = "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)
    assert "club-alpha-1" in text
    assert call("GET", "/audit/v1/qr/match-m1/export.gif")[0] in (400, 404)


@needs_docker
def test_scan_telemetry_counts_and_stores_no_pii():
    before = metric("nascon_qr_scans_total")
    mobile = {"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) Mobile Safari/537.36"}
    desktop = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0"}
    assert call("GET", "/audit/v1/qr/match-m1", headers=mobile)[1]["scan_count"] == 1
    assert call("GET", "/audit/v1/qr/match-m1?inspect=true", headers=desktop)[1]["scan_count"] == 1
    assert call("GET", "/q/m1-live", headers=desktop, follow=False)[0] == 302
    assert call("GET", "/audit/v1/qr/match-m1?inspect=true")[1]["scan_count"] == 2
    assert metric("nascon_qr_scans_total") == before + 2
    rows = psql("SELECT device_family || ':' || hour_bucket || ':' || scans FROM qr_scans "
                "WHERE entity_id = 'match-m1' ORDER BY device_family").splitlines()
    fams = sorted(r.split(":")[0] for r in rows)
    assert fams == ["desktop", "mobile"], rows
    cols = psql("SELECT string_agg(column_name, ',') FROM information_schema.columns WHERE table_name = 'qr_scans'")
    assert not re.search(r"ip|agent|cookie|fingerprint", cols, re.I), cols


# ------------------------------------------------------------------ 6. metrics values (NFR-6)
def test_metrics_format_and_live_values():
    s, body, h = call("GET", "/metrics")
    assert s == 200 and h["content-type"].startswith("text/plain; version=0.0.4")
    for name, kind in (("nascon_active_ws_connections", "gauge"), ("nascon_active_streams_total", "gauge"),
                       ("nascon_stream_bitrate_kbps", "gauge"), ("nascon_dlq_depth", "gauge"),
                       ("nascon_qr_scans_total", "counter")):
        assert f"# TYPE {name} {kind}" in body.decode()
    assert metric("nascon_dlq_depth") == 0
    s, b, _ = call("POST", "/audit/v1/moderation/test", {"chat_room_id": "chat-e2e", "incoming_messages": [
        {"message_id": "m1", "sender": "u1", "text": "hi"}], "check_dlq": True, "simulate_failed_notifications": 3})
    assert s == 200 and metric("nascon_dlq_depth") == b["dlq_status"]["queue_depth"] == 3

    base = metric("nascon_active_ws_connections")

    async def hold():
        url = BASE.replace("http", "ws", 1) + "/ws/matches/match-m1"
        conns = [await websockets.connect(url) for _ in range(3)]
        await asyncio.sleep(0.5)
        during = await asyncio.to_thread(metric, "nascon_active_ws_connections")
        for c in conns:
            await c.close()
        return during
    assert asyncio.run(hold()) >= base + 3
    assert wait_until(lambda: metric("nascon_active_ws_connections") <= base, 5)


# ------------------------------------------------------------------ 7. privacy erasure (NFR-9)
@needs_docker
def test_privacy_delete_wipes_pii_tokens_follows_within_1s():
    tok = login("player@nascon.test")
    assert call("POST", "/api/v1/athletes/player-alpha-2/follow", token=tok)[0] == 200
    s, b, _ = call("POST", "/api/v1/guest/token")
    g = b["guest_token"]
    call("POST", "/api/v1/cart", {"guest_token": g, "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}]},
         token=tok)
    t0 = time.monotonic()
    s, b, _ = call("DELETE", "/audit/v1/privacy/user/player-alpha-1")
    assert time.monotonic() - t0 < 1.0
    assert (s, b) == (200, {"user_id": "player-alpha-1", "status": "anonymized", "pii_retained": False,
                            "tokens_wiped": True})
    assert call("POST", "/api/v1/auth/login", {"email": "player@nascon.test", "password": PASSWORD})[0] == 401
    assert psql(f"SELECT status FROM guest_tokens WHERE guest_token = '{g}'") == "wiped"
    assert psql("SELECT count(*) FROM follows WHERE follower_id IN "
                "(SELECT user_id FROM users WHERE player_id = 'player-alpha-1')") == "0"
    assert call("GET", "/api/v1/athletes/player-alpha-1")[1]["name"] == "Erased player"
    r = call("DELETE", "/audit/v1/privacy/user/nobody-here")
    assert r[0] == 404


# ------------------------------------------------------------------ 8. guest web serving (FR-4.2)
@pytest.mark.parametrize("path", ["/web/matches/match-m1/live", "/web/costream/cs-session-101",
                                  "/web/players/player-alpha-1", "/web/clubs/club-alpha-1",
                                  "/web/matches/match-m1/notice?state=postponed"])
def test_web_routes_serve_player_with_all_testids(path):
    s, b, h = call("GET", path)
    assert s == 200 and h["content-type"].startswith("text/html")
    html = b.decode()
    missing = [t for t in TESTIDS if f'data-testid="{t}"' not in html]
    assert not missing, missing


def test_web_static_assets_served():
    s, b, h = call("GET", "/web/static/app.js")
    assert s == 200 and len(b) > 1000
    assert call("GET", "/web/static/does-not-exist.js")[0] == 404


# ------------------------------------------------------------------ 9. limits and conventions
def test_audit_routes_exempt_from_rate_limit_under_burst():
    statuses = []

    def hit():
        statuses.append(call("GET", "/audit/v1/qr/match-m1?inspect=true")[0])
    threads = [threading.Thread(target=hit) for _ in range(250)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert statuses.count(200) == 250, {s: statuses.count(s) for s in set(statuses)}


@pytest.mark.parametrize("path", ["/audit/v1/stream/key", "/audit/v1/costream/session", "/audit/v1/guest/cart-merge",
                                  "/audit/v1/moderation/test"])
def test_part2_routes_reject_bodies_over_1mb(path):
    r = None
    for _ in range(3):   # the server answers 413 before reading the body; Windows may reset the socket mid-send
        try:
            r = call("POST", path, raw=b'{"x":"' + b"a" * (1024 * 1024 + 10) + b'"}')
            break
        except (ConnectionError, urllib.error.URLError):
            time.sleep(0.2)
    assert r is not None
    assert r[0] == 413 and code(r) == "PAYLOAD_TOO_LARGE"


@pytest.mark.parametrize("path", ["/audit/v1/stream/key", "/audit/v1/costream/session", "/audit/v1/guest/cart-merge",
                                  "/audit/v1/moderation/test"])
def test_part2_routes_malformed_json_is_validation_error(path):
    r = call("POST", path, raw=b"{bad json")
    assert r[0] == 400 and code(r) == "VALIDATION_ERROR" and isinstance(r[1]["error"]["details"].get("fields"), list)


def test_reset_seeds_day2_defaults_and_is_repeatable():
    first = call("POST", "/audit/v1/reset")[1]
    second = call("POST", "/audit/v1/reset")[1]
    assert first == second
    s, b, _ = call("GET", "/audit/v1/qr/match-m1?inspect=true")
    assert b["scan_count"] == 0 and b["short_url"].endswith("/q/m1-live")
    assert call("GET", "/audit/v1/qr/player-alpha-1?inspect=true")[1]["short_url"].endswith("/q/p-alpha-1")
    assert call("GET", "/audit/v1/qr/club-alpha-1?inspect=true")[1]["short_url"].endswith("/q/c-alpha-1")
    assert call("GET", "/api/v1/athletes/player-beta-2")[0] == 200
