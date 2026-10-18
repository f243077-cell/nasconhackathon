"""Real-time notification dispatch with bounded retry and a persistent DLQ (FR-5.2, ADR-15).

dispatch() publishes over the realtime bus (WebSocket/SSE fan-out). A failed delivery (Redis down, or
`simulate_dlq` set by the caller to emulate a disconnected subscriber) is retried 3 times with 100/200 ms
backoff (domain/notify.py), then written to the `dlq` table in the caller's transaction."""
import json
import time
from typing import Callable

from .. import config
from ..domain import notify
from ..validate import now_iso
from . import bus


def dispatch(conn, kind: str, target: str, data: dict, simulate_dlq: bool = False,
             sleep: Callable[[float], None] = time.sleep) -> dict:
    def send() -> bool:
        if simulate_dlq:
            raise ConnectionError("subscriber_unreachable")
        bus.client().publish(config.REALTIME_CHANNEL, json.dumps({"type": kind, "match_id": None,
                                                                      "data": {**data, "target": target}}))
        return True

    result = notify.deliver(send, sleep)
    if not result["delivered"]:
        event = notify.dlq_event(kind, target, result, data=data)
        conn.execute("INSERT INTO dlq (event, attempts, created_at) VALUES (%s, %s, %s)",
                     (json.dumps(event), result["attempts"], now_iso()))
    return {"delivered": result["delivered"], "attempts": result["attempts"]}
