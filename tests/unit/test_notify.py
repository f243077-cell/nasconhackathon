import pytest

from app.domain import notify


def test_backoff_doubles_from_100_ms():
    assert [notify.backoff_ms(i) for i in (1, 2, 3, 4)] == [100, 200, 400, 800]
    assert notify.backoff_ms(2, base_ms=50) == 100
    with pytest.raises(ValueError):
        notify.backoff_ms(0)


def test_schedule_has_one_wait_between_each_attempt():
    assert notify.schedule() == [100, 200]
    assert notify.schedule(1) == []
    assert notify.schedule(4, base_ms=10) == [10, 20, 40]


def test_first_try_success_never_sleeps():
    waits = []
    assert notify.deliver(lambda: True, waits.append) == {"delivered": True, "attempts": 1, "last_error": None}
    assert waits == []


def test_success_on_third_attempt_after_two_backoffs():
    outcomes, waits = iter([False, False, True]), []
    assert notify.deliver(lambda: next(outcomes), waits.append) == {"delivered": True, "attempts": 3, "last_error": None}
    assert waits == [0.1, 0.2]


def test_three_failures_go_to_dlq_and_stop_retrying():
    calls, waits = [], []

    def down():
        calls.append(1)
        raise ConnectionError("subscriber_unreachable")
    result = notify.deliver(down, waits.append)
    assert result == {"delivered": False, "attempts": 3, "last_error": "ConnectionError"}
    assert len(calls) == 3 and waits == [0.1, 0.2]


def test_rejected_without_exception():
    assert notify.deliver(lambda: False, lambda _s: None, max_attempts=2)["last_error"] == "rejected"


def test_dlq_event_record():
    result = {"delivered": False, "attempts": 3, "last_error": "ConnectionError"}
    assert notify.dlq_event("chat_notification", "chat-cs-session-101", result, index=1) == {
        "type": "chat_notification", "target": "chat-cs-session-101", "attempts": 3, "last_error": "ConnectionError",
        "backoff_ms": [100, 200], "index": 1}
