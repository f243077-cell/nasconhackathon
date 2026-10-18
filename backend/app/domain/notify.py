"""Notification delivery policy (FR-5.2, ADR-15): bounded exponential retry, then the dead-letter queue.
Pure: the caller passes the send function and the sleep function."""
from typing import Callable

MAX_ATTEMPTS = 3
BASE_DELAY_MS = 100


def backoff_ms(attempt: int, base_ms: int = BASE_DELAY_MS) -> int:
    """Delay before retry number `attempt` (1-based): 100, 200, 400 ms..."""
    if attempt < 1:
        raise ValueError("attempt starts at 1")
    return base_ms * 2 ** (attempt - 1)


def schedule(max_attempts: int = MAX_ATTEMPTS, base_ms: int = BASE_DELAY_MS) -> list[int]:
    """Delays between the attempts: max_attempts tries means max_attempts - 1 waits."""
    return [backoff_ms(i, base_ms) for i in range(1, max_attempts)]


def deliver(send: Callable[[], bool], sleep: Callable[[float], None], max_attempts: int = MAX_ATTEMPTS,
            base_ms: int = BASE_DELAY_MS) -> dict:
    """Try `send` up to max_attempts times with exponential backoff. A raised exception counts as a failure.
    Returns {delivered, attempts, last_error}; delivered False means the event goes to the DLQ."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            if send():
                return {"delivered": True, "attempts": attempt, "last_error": None}
            last_error = "rejected"
        except Exception as exc:  # noqa: BLE001  any delivery failure is retried, never raised
            last_error = type(exc).__name__
        if attempt < max_attempts:
            sleep(backoff_ms(attempt, base_ms) / 1000)
    return {"delivered": False, "attempts": max_attempts, "last_error": last_error}


def dlq_event(kind: str, target: str, result: dict, **extra) -> dict:
    """The record stored in the DLQ for an event that exhausted its retries."""
    return {"type": kind, "target": target, "attempts": result["attempts"], "last_error": result["last_error"],
            "backoff_ms": schedule(result["attempts"]), **extra}
