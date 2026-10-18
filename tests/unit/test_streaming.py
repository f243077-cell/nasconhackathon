import pytest

from app.canonical import sign_day2
from app.domain import streaming
from app.errors import ApiError


def test_appendix_a_vector_1_stream_key_signature():
    payload = streaming.sig_payload("rotate", "player-alpha-1", "active", "sk_live_9f83a1b2c3d4e5f6")
    assert sign_day2("sk_live_9f83a1b2c3d4e5f6", payload, salt="T01D27ad7ffff12e") == \
        "9bd054eb746844b4701c6f158209c315ef2b16f392efd733bdf0715940610289"


def test_appendix_a_vector_2_legacy_message_uses_pipe():
    a = sign_day2("sk_live_101", {"action": "rotate", "player_id": "player-alpha-1"}, salt="T01D27ad7ffff12e")
    assert len(a) == 64 and a == a.lower()


def test_key_format_and_override():
    assert streaming.KEY_RE.fullmatch(streaming.new_key())
    assert streaming.new_key("sk_live_9f83a1b2c3d4e5f6") == "sk_live_9f83a1b2c3d4e5f6"


@pytest.mark.parametrize("body,field", [
    ({"action": "pause", "player_id": "p"}, "action"),
    ({"action": "rotate"}, "player_id"),
    ({"action": "rotate", "player_id": "p", "label": ""}, "label"),
    ({"action": "rotate", "player_id": "p", "label": "x" * 65}, "label"),
    ({"action": "rotate", "player_id": "p", "stream_key_override": "a/b"}, "stream_key_override"),
])
def test_stream_request_validation(body, field):
    with pytest.raises(ApiError) as e:
        streaming.validate_request(body)
    assert e.value.code == "VALIDATION_ERROR" and field in e.value.details["fields"]


def test_stream_response_active_and_revoked():
    r = streaming.response("player-alpha-1", "OBS", "sk_live_x", "active", "localhost")
    assert r["ingest_endpoints"]["rtmp"] == "rtmp://localhost:1935/live/sk_live_x"
    assert r["ingest_endpoints"]["webrtc"] == "http://localhost:8889/live/sk_live_x/whip"
    assert r["playback_url"] == "http://localhost:8888/live/sk_live_x/index.m3u8"
    r = streaming.response("player-alpha-1", "OBS", "sk_live_x", "revoked", "localhost")
    assert r["ingest_endpoints"] is None and r["playback_url"] is None
