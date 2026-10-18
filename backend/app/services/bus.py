"""Redis helpers: domain-event stream (internal queue) and realtime pub/sub. Best effort: never fail a request."""
import json
import logging

import redis

from .. import config

log = logging.getLogger("bus")
_client: redis.Redis | None = None


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(config.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
    return _client


def emit_domain_event(event_type: str, data: dict) -> None:
    try:
        client().xadd(config.DOMAIN_EVENTS_STREAM, {"type": event_type, "data": json.dumps(data)}, maxlen=10000)
    except Exception as exc:  # noqa: BLE001
        log.warning("domain event %s not emitted: %s", event_type, exc)


def publish_realtime(msg_type: str, match_id: str | None, data: dict) -> None:
    try:
        client().publish(config.REALTIME_CHANNEL, json.dumps({"type": msg_type, "match_id": match_id, "data": data}))
    except Exception as exc:  # noqa: BLE001
        log.warning("realtime %s not published: %s", msg_type, exc)


def qr_cache_key(entity_id: str) -> str:
    return f"qr:view:{entity_id}"


def invalidate_qr(entity_id: str) -> None:
    try:
        client().delete(qr_cache_key(entity_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("qr cache invalidation for %s failed: %s", entity_id, exc)
