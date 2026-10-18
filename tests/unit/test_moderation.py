import pytest

from app.domain import moderation as mod
from app.errors import ApiError


def msg(i, sender, text, **extra):
    return {"message_id": f"msg-{i}", "sender": sender, "text": text, **extra}


def test_spec_example():
    out = mod.moderate([
        msg(1, "user-guest-1", "Clean sports commentary"),
        msg(2, "user-spammer", "Watch this illegal stream p0rn now!"),
        msg(3, "user-flooder", "GOAL!!!"),
    ])
    assert out["filtered_messages"] == [
        {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary", "flagged": False, "reason": None},
        {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream *** now!", "flagged": True,
         "reason": "profanity_leetspeak"},
    ]
    assert out["kicked_users"] == ["user-spammer"]
    assert out["muted_users"] == ["user-flooder"]
    assert out["flagged_count"] == 1
    assert out["blocked"] == [{"message_id": "msg-3", "sender": "user-flooder", "reason": "flood_character_repeat"}]


@pytest.mark.parametrize("word", [
    "badword", "b@d_w0rd", "bad_word", "BAD-WORD", "porn", "p0rn", "p.0.r.n", "scam", "sc@m", "s!c@m",
    "fuck", "f*u*c*k", "FUCK", "shit", "sh1t", "$hit", "bitch", "b1tch", "asshole", "a$$h0le", "a$$ho1e",
    "idiot_spam", "1d10t_$p@m", "sc​am", "scams", "bitches",
])
def test_dictionary_and_obfuscations_are_masked(word):
    text, hit = mod.mask_text(f"you {word} here")
    assert hit
    assert text == "you *** here"


@pytest.mark.parametrize("text", [
    "Clean sports commentary", "Great save by the keeper", "Scampi for dinner", "shell company", "assessment day",
    "now!", "pass it 10 yards", "$100 prize", "I said hi", "",
])
def test_clean_text_is_untouched(text):
    assert mod.mask_text(text) == (text, False)


def test_punctuation_around_token_is_kept():
    assert mod.mask_text("total sc@m, honestly") == ("total ***, honestly", True)
    assert mod.mask_text("(p0rn)") == ("(***)", True)
    assert mod.mask_text("what a scam?") == ("what a ***?", True)


def test_whitespace_preserved_and_every_token_masked():
    assert mod.mask_text("scam  and\tporn") == ("***  and\t***", True)


@pytest.mark.parametrize("text,flood", [
    ("AAAA", True), ("aaAA", True), ("goooool", True), ("....", True), ("!!!", True), ("?!?", True), ("??", False),
    ("aaa", False), ("hello!!", False), ("    spaced    out", False), ("Good game", False),
])
def test_flood_rules(text, flood):
    assert mod.is_flood(text) is flood


def test_flood_is_dropped_and_muted_even_if_profane():
    out = mod.moderate([msg(1, "u1", "scam!!!")])
    assert out["filtered_messages"] == []
    assert out["muted_users"] == ["u1"]
    assert out["kicked_users"] == []


def test_kick_and_mute_lists_dedup_in_first_violation_order():
    out = mod.moderate([
        msg(1, "b", "sc@m"), msg(2, "a", "p0rn"), msg(3, "b", "porn again"),
        msg(4, "z", "AAAA"), msg(5, "y", "!!!"), msg(6, "z", "BBBB"),
    ])
    assert out["kicked_users"] == ["b", "a"]
    assert out["muted_users"] == ["z", "y"]
    assert out["flagged_count"] == 3


def test_ten_identical_runs_kick_exactly_once():
    out = mod.moderate([msg(i, "user-spammer", "b@d_w0rd") for i in range(10)])
    assert out["kicked_users"] == ["user-spammer"]
    assert out["flagged_count"] == 10


def test_rate_limit_sliding_window():
    msgs = [msg(i, "fast", f"hi {i}", sent_at=t) for i, t in enumerate([0.0, 0.5, 1.0, 1.5, 2.6, 4.7])]
    out = mod.moderate(msgs)
    # t=1.5 is the 4th inside 2 s -> blocked; t=2.6 sees only 1.0 and 1.5 (0.5 is 2.1 s old) -> allowed.
    assert [m["message_id"] for m in out["filtered_messages"]] == ["msg-0", "msg-1", "msg-2", "msg-4", "msg-5"]
    assert out["muted_users"] == ["fast"]
    assert out["blocked"] == [{"message_id": "msg-3", "sender": "fast", "reason": "rate_limit_exceeded"}]


def test_rate_limit_is_per_sender_and_needs_timestamps():
    out = mod.moderate([msg(i, f"s{i % 2}", "ok", sent_at=0.1 * i) for i in range(6)])
    assert len(out["filtered_messages"]) == 6
    out = mod.moderate([msg(i, "same", "ok") for i in range(8)])
    assert len(out["filtered_messages"]) == 8


def test_rate_exceeded_helper():
    assert not mod.rate_exceeded([0.0, 0.5], 1.0)
    assert mod.rate_exceeded([0.0, 0.5, 1.0], 1.5)
    assert not mod.rate_exceeded([0.0, 0.5, 1.0], 2.5)


def test_sig_payload_shape():
    assert mod.sig_payload("chat-cs-session-101", 1, ["user-spammer"], 0) == {
        "chat_room_id": "chat-cs-session-101", "flagged_count": 1, "kicked_users": ["user-spammer"], "queue_depth": 0}


GOOD = {"chat_room_id": "chat-cs-session-101", "incoming_messages": [msg(1, "u", "hi")], "check_dlq": True,
        "simulate_failed_notifications": 0}


def test_valid_request_passes():
    mod.validate_request(GOOD)
    mod.validate_request({"chat_room_id": "r", "incoming_messages": []})
    mod.validate_request({**GOOD, "incoming_messages": [msg(1, "u", "hi", sent_at=1.5)]})


@pytest.mark.parametrize("patch,field", [
    ({"chat_room_id": ""}, "chat_room_id"),
    ({"chat_room_id": 5}, "chat_room_id"),
    ({"incoming_messages": "x"}, "incoming_messages"),
    ({"incoming_messages": [{"message_id": "m", "sender": "u"}]}, "incoming_messages"),
    ({"incoming_messages": [{"message_id": "m", "sender": "", "text": "x"}]}, "incoming_messages"),
    ({"incoming_messages": [msg(1, "u", "x", sent_at=True)]}, "incoming_messages"),
    ({"incoming_messages": [msg(1, "u", "x", sent_at="now")]}, "incoming_messages"),
    ({"incoming_messages": [msg(1, "u", "x" * 4001)]}, "incoming_messages"),
    ({"incoming_messages": [msg(i, "u", "x") for i in range(1001)]}, "incoming_messages"),
    ({"check_dlq": "yes"}, "check_dlq"),
    ({"simulate_failed_notifications": -1}, "simulate_failed_notifications"),
    ({"simulate_failed_notifications": True}, "simulate_failed_notifications"),
    ({"simulate_failed_notifications": 101}, "simulate_failed_notifications"),
])
def test_invalid_requests(patch, field):
    with pytest.raises(ApiError) as e:
        mod.validate_request({**GOOD, **patch})
    assert e.value.status == 400 and e.value.code == "VALIDATION_ERROR"
    assert field in e.value.details["fields"]


def test_non_object_body():
    with pytest.raises(ApiError):
        mod.validate_request([])
