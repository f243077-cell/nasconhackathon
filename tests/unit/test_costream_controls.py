import hashlib
import hmac
import json

import pytest

from app.canonical import canonical
from app.domain import costream as cs
from app.errors import ApiError


def sign(entity_id, payload):
    return hmac.new(b"unit-salt", (entity_id + "|" + canonical(payload)).encode(), hashlib.sha256).hexdigest()


STATE = cs.state_from_response({"session_id": "cs-1", "status": "active", "active_host": "h",
                                "active_participants": ["h", "a", "b"], "layout": "grid_4"})


def err(fn, *a):
    with pytest.raises(ApiError) as e:
        fn(*a)
    return e.value


def test_state_and_view():
    assert STATE == {"session_id": "cs-1", "status": "active", "host": "h", "participants": ["h", "a", "b"],
                     "layout": "grid_4", "muted": [], "spotlight": None, "kicked": []}
    assert cs.view(STATE) == {"session_id": "cs-1", "status": "active", "active_host": "h", "participant_count": 3,
                              "active_participants": ["h", "a", "b"], "layout": "grid_4", "muted": [], "spotlight": None,
                              "composite_playback_url": "http://localhost:8888/costream/cs-1/index.m3u8",
                              "chat_room_id": "chat-cs-1"}


def test_mute_unmute_idempotent_and_input_not_mutated():
    s1 = cs.apply_control(STATE, "h", "mute", "a")
    assert s1["muted"] == ["a"] and STATE["muted"] == []
    assert cs.apply_control(s1, "h", "mute", "a")["muted"] == ["a"]
    assert cs.apply_control(s1, "h", "unmute", "a")["muted"] == []
    assert cs.apply_control(STATE, "h", "unmute", "a")["muted"] == []


def test_spotlight_switches_layout():
    s = cs.apply_control(STATE, "h", "spotlight", "b")
    assert (s["spotlight"], s["layout"]) == ("b", "spotlight")


def test_kick_removes_everywhere_and_blocks_rejoin():
    s = cs.apply_control(cs.apply_control(cs.apply_control(STATE, "h", "mute", "a"), "h", "spotlight", "a"), "h", "kick", "a")
    assert s["participants"] == ["h", "b"] and s["muted"] == [] and s["spotlight"] is None and s["kicked"] == ["a"]
    invite = {"session_id": "cs-1", "player_id": "a", "exp": 10}
    assert err(cs.join, s, "a", invite).code == "FORBIDDEN"


def test_control_errors():
    assert err(cs.apply_control, STATE, "a", "mute", "b").code == "FORBIDDEN"          # not the host
    assert err(cs.apply_control, STATE, None, "mute", "b").code == "FORBIDDEN"
    e = err(cs.apply_control, STATE, "h", "kick", "zz")
    assert (e.status, e.code) == (404, "PLAYER_NOT_FOUND")
    assert err(cs.apply_control, STATE, "h", "kick", "h").code == "VALIDATION_ERROR"   # host can't kick self
    assert err(cs.apply_control, STATE, "h", "kick", None).code == "VALIDATION_ERROR"
    assert err(cs.apply_control, STATE, "h", "teleport", "a").code == "VALIDATION_ERROR"
    ended = {**STATE, "status": "terminated"}
    assert (err(cs.apply_control, ended, "h", "mute", "a").code) == "STREAM_NOT_FOUND"


def test_host_drop_hands_off_in_array_order_and_cleans_up():
    s = cs.apply_control(cs.apply_control(STATE, "h", "mute", "h"), "h", "spotlight", "h")
    after = cs.host_drop(s)
    assert (after["host"], after["participants"], after["status"]) == ("a", ["a", "b"], "active")
    assert after["muted"] == [] and after["spotlight"] is None
    last = cs.host_drop(cs.host_drop(after))
    assert (last["status"], last["host"], last["participants"]) == ("terminated", None, [])
    assert err(cs.host_drop, last).code == "STREAM_NOT_FOUND"


def test_invite_roundtrip_and_tampering():
    payload = cs.invite_payload("cs-1", "c", issued_at=1000)
    assert payload == {"session_id": "cs-1", "player_id": "c", "exp": 1000 + cs.INVITE_TTL_S}
    token = cs.make_invite(payload, sign)
    assert token.startswith("inv.") and token.count(".") == 2
    assert cs.read_invite(token, sign, now=1001) == payload
    assert err(cs.read_invite, token, sign, 1000 + cs.INVITE_TTL_S + 1).code == "FORBIDDEN"   # expired
    _, body, sig = token.split(".")
    forged = json.dumps({**payload, "player_id": "evil"}, sort_keys=True, separators=(",", ":"))
    import base64
    forged_body = base64.urlsafe_b64encode(forged.encode()).decode().rstrip("=")
    for bad in (f"inv.{forged_body}.{sig}", f"inv.{body}.{'0' * 64}", "inv.%%%.x", "nope", None, "inv.a.b.c",
                f"inv.{base64.urlsafe_b64encode(b'[1]').decode().rstrip('=')}.{sig}"):
        assert err(cs.read_invite, bad, sign, 1001).code == "FORBIDDEN"


def test_join_rules():
    invite = {"session_id": "cs-1", "player_id": "c", "exp": 99}
    assert cs.join(STATE, "c", invite)["participants"] == ["h", "a", "b", "c"]
    assert cs.join(STATE, "a", {**invite, "player_id": "a"}) is STATE                 # already in: idempotent
    assert err(cs.join, STATE, "d", invite).code == "FORBIDDEN"                       # invite for someone else
    assert err(cs.join, STATE, "c", {**invite, "session_id": "cs-2"}).code == "FORBIDDEN"
    full = {**STATE, "participants": ["h", "a", "b", "x"]}
    assert err(cs.join, full, "c", invite).code == "COSTREAM_SESSION_FULL"
    duo = {**STATE, "participants": ["h", "a"], "layout": "grid_2"}
    assert err(cs.join, duo, "c", invite).code == "UNSUPPORTED_LAYOUT"
    assert err(cs.join, {**STATE, "status": "terminated"}, "c", invite).code == "STREAM_NOT_FOUND"
