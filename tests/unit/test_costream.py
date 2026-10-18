import pytest

from app.domain import costream as cs
from app.errors import ApiError

PLAYERS = {"player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2", "player-x"}
exists = PLAYERS.__contains__

SPEC = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
        "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"],
        "layout": "grid_4", "simulate_host_drop": True}


def err(body, player_exists=exists):
    with pytest.raises(ApiError) as e:
        cs.plan_session(body, player_exists)
    return e.value


def test_spec_example_host_drop():
    assert cs.plan_session(SPEC, exists) == {
        "session_id": "cs-session-101", "status": "active", "active_host": "player-alpha-2", "handoff_occurred": True,
        "participant_count": 3, "active_participants": ["player-alpha-2", "player-beta-1", "player-beta-2"],
        "layout": "grid_4", "composite_playback_url": "http://localhost:8888/costream/cs-session-101/index.m3u8",
        "chat_room_id": "chat-cs-session-101"}


def test_no_drop_keeps_host_and_everyone():
    out = cs.plan_session({**SPEC, "simulate_host_drop": False}, exists)
    assert out["active_host"] == "player-alpha-1" and out["handoff_occurred"] is False
    assert out["participant_count"] == 4 and out["active_participants"] == SPEC["participants"]
    assert out["status"] == "active"


def test_handoff_goes_to_next_in_array_order_not_first_listed():
    body = {**SPEC, "host_player_id": "player-beta-1"}
    out = cs.plan_session(body, exists)
    assert out["active_host"] == "player-alpha-1"
    assert out["active_participants"] == ["player-alpha-1", "player-alpha-2", "player-beta-2"]


def test_drop_of_only_participant_terminates():
    out = cs.plan_session({"session_id": "cs-1", "host_player_id": "player-x", "participants": ["player-x"],
                           "simulate_host_drop": True, "layout": "solo"}, exists)
    assert out["status"] == "terminated" and out["active_host"] is None and out["handoff_occurred"] is False
    assert out["participant_count"] == 0 and out["active_participants"] == []
    assert out["chat_room_id"] == "chat-cs-1"


def test_defaults_layout_grid_4_and_no_drop():
    out = cs.plan_session({"session_id": "cs-2", "host_player_id": "player-x", "participants": ["player-x"]}, exists)
    assert out["layout"] == "grid_4" and out["handoff_occurred"] is False


@pytest.mark.parametrize("patch,field", [
    ({"session_id": ""}, "session_id"),
    ({"session_id": "a|b"}, "session_id"),
    ({"host_player_id": 7}, "host_player_id"),
    ({"participants": []}, "participants"),
    ({"participants": "player-alpha-1"}, "participants"),
    ({"participants": ["player-alpha-1", "player-alpha-1"]}, "participants"),
    ({"participants": ["player-alpha-1", 3]}, "participants"),
    ({"simulate_host_drop": "yes"}, "simulate_host_drop"),
    ({"layout": "grid_9"}, "layout"),
])
def test_schema_errors(patch, field):
    e = err({**SPEC, **patch})
    assert (e.status, e.code) == (400, "VALIDATION_ERROR") and field in e.details["fields"]


def test_non_object():
    assert err(None).code == "VALIDATION_ERROR"


def test_unknown_participant_is_404_with_its_id():
    e = err({**SPEC, "participants": ["player-alpha-1", "ghost"]})
    assert (e.status, e.code, e.details) == (404, "PLAYER_NOT_FOUND", {"player_id": "ghost"})


def test_unknown_host_is_404_before_membership_400():
    e = err({**SPEC, "host_player_id": "ghost"})
    assert (e.status, e.details) == (404, {"player_id": "ghost"})


def test_host_not_in_participants_is_400():
    e = err({**SPEC, "host_player_id": "player-x"})
    assert (e.status, e.code, e.details["fields"]) == (400, "VALIDATION_ERROR", ["host_player_id"])


def test_five_participants_is_409_after_existence():
    five = [*SPEC["participants"], "player-x"]
    e = err({**SPEC, "participants": five})
    assert (e.status, e.code) == (409, "COSTREAM_SESSION_FULL") and e.details["participant_count"] == 5
    # a missing player among five still reports 404 first
    assert err({**SPEC, "participants": [*SPEC["participants"], "ghost"]}).code == "PLAYER_NOT_FOUND"


def test_full_beats_layout_check():
    assert err({**SPEC, "participants": [*SPEC["participants"], "player-x"], "layout": "solo"}).code == "COSTREAM_SESSION_FULL"


@pytest.mark.parametrize("layout,parts,drop,ok", [
    ("solo", 1, False, True), ("solo", 2, False, False), ("solo", 2, True, True), ("solo", 3, True, False),
    ("grid_2", 2, False, True), ("grid_2", 3, False, False), ("grid_2", 3, True, True), ("grid_2", 4, True, False),
    ("grid_4", 4, False, True), ("spotlight", 4, False, True), ("spotlight", 1, False, True),
])
def test_layout_capacity_uses_count_after_handoff(layout, parts, drop, ok):
    people = SPEC["participants"][:parts]
    body = {"session_id": "cs-3", "host_player_id": people[0], "participants": people, "layout": layout,
            "simulate_host_drop": drop}
    if ok:
        assert cs.plan_session(body, exists)["layout"] == layout
    else:
        e = err(body)
        assert (e.status, e.code) == (400, "UNSUPPORTED_LAYOUT")


def test_custom_media_base():
    out = cs.plan_session(SPEC, exists, media_base="http://10.0.0.5:8888")
    assert out["composite_playback_url"] == "http://10.0.0.5:8888/costream/cs-session-101/index.m3u8"


def test_sig_payload_is_the_six_keys_from_the_response():
    out = cs.plan_session(SPEC, exists)
    assert cs.sig_payload(out) == {"active_host": "player-alpha-2", "handoff_occurred": True, "layout": "grid_4",
                                   "participant_count": 3, "session_id": "cs-session-101", "status": "active"}
