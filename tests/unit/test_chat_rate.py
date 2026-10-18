import pytest

from app.errors import ApiError
from app.repo import social


class FakeRedis:
    def __init__(self):
        self.sets = {}

    def zremrangebyscore(self, key, lo, hi):
        self.sets[key] = {m: s for m, s in self.sets.get(key, {}).items() if not lo <= s <= hi}

    def zrange(self, key, a, b):
        return [str(s).encode() for s in sorted(self.sets.get(key, {}).values())]

    def zadd(self, key, mapping):
        self.sets.setdefault(key, {}).update(mapping)

    def expire(self, key, ttl):
        pass


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(social.bus, "client", lambda: fake)
    return fake


def test_fourth_message_inside_two_seconds_is_429(redis):
    for t in (0.0, 0.5, 1.0):
        social.chat_rate_check("chat-cs-1", "u1", now=100 + t)
    with pytest.raises(ApiError) as e:
        social.chat_rate_check("chat-cs-1", "u1", now=101.5)
    assert (e.value.status, e.value.code) == (429, "RATE_LIMITED")
    assert e.value.details["reason"] == "rate_limit_exceeded" and e.value.details["retry_after"] == 0.5


def test_window_slides_and_is_per_sender_and_room(redis):
    for t in (0.0, 0.5, 1.0):
        social.chat_rate_check("r", "u1", now=t)
    social.chat_rate_check("r", "u2", now=1.2)            # other sender
    social.chat_rate_check("other-room", "u1", now=1.2)   # other room
    social.chat_rate_check("r", "u1", now=2.6)            # 0.0 and 0.5 have left the window


def test_redis_outage_never_blocks_chat(monkeypatch):
    def broken():
        raise ConnectionError("down")
    monkeypatch.setattr(social.bus, "client", broken)
    for t in range(10):
        social.chat_rate_check("r", "u", now=t * 0.01)
