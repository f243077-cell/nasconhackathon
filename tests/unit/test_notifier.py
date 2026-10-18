import json

from app.services import notifier


class FakeConn:
    def __init__(self):
        self.rows = []

    def execute(self, sql, args=()):
        self.rows.append((sql, args))


class FakeRedis:
    def __init__(self, fail=False):
        self.fail, self.sent = fail, []

    def publish(self, channel, msg):
        if self.fail:
            raise ConnectionError("redis down")
        self.sent.append(json.loads(msg))


def test_delivered_publishes_once_and_writes_no_dlq(monkeypatch):
    redis, conn, waits = FakeRedis(), FakeConn(), []
    monkeypatch.setattr(notifier.bus, "client", lambda: redis)
    out = notifier.dispatch(conn, "order_status", "cust-1", {"order_id": "o1", "to": "packed"}, sleep=waits.append)
    assert out == {"delivered": True, "attempts": 1}
    assert redis.sent == [{"type": "order_status", "match_id": None,
                           "data": {"order_id": "o1", "to": "packed", "target": "cust-1"}}]
    assert conn.rows == [] and waits == []


def test_simulate_dlq_retries_three_times_then_dead_letters(monkeypatch):
    redis, conn, waits = FakeRedis(), FakeConn(), []
    monkeypatch.setattr(notifier.bus, "client", lambda: redis)
    out = notifier.dispatch(conn, "costream_invite", "player-x", {"session_id": "cs-1"}, simulate_dlq=True,
                            sleep=waits.append)
    assert out == {"delivered": False, "attempts": 3}
    assert redis.sent == [] and waits == [0.1, 0.2]
    (sql, args), = conn.rows
    assert "INSERT INTO dlq" in sql and args[1] == 3
    event = json.loads(args[0])
    assert event["type"] == "costream_invite" and event["target"] == "player-x" and event["attempts"] == 3
    assert event["data"] == {"session_id": "cs-1"} and event["backoff_ms"] == [100, 200]


def test_bus_outage_also_dead_letters(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(notifier.bus, "client", lambda: FakeRedis(fail=True))
    out = notifier.dispatch(conn, "order_status", "c", {}, sleep=lambda _s: None)
    assert out["delivered"] is False and len(conn.rows) == 1
