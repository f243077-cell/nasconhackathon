"""Chat moderation (FR-5.3, spec 5.8). Pure functions: no DB, no clock, no I/O after import.

Order per message (first match wins, ADR-14):
1. Rate: more than 3 messages from one sender inside a 2 s sliding window (only when messages carry `sent_at`
   seconds) -> dropped, sender muted, reason rate_limit_exceeded.
2. Flood: >= 4 consecutive identical non-space characters (case-insensitive) or >= 3 consecutive `!`/`?`
   -> dropped, sender muted, reason flood_character_repeat.
3. Profanity after leetspeak normalisation -> each offending token replaced in place by `***`, kept in the
   output with flagged true, sender kicked, reason profanity_leetspeak.
4. Otherwise the message passes unchanged.
kicked_users / muted_users are deduplicated and kept in order of first violation.
flagged_count = number of flagged messages in filtered_messages (dropped messages are not in that list).
"""
import json
import os
import re

from ..errors import validation_error
from ..validate import is_int, is_str

REASON_PROFANITY = "profanity_leetspeak"
REASON_FLOOD = "flood_character_repeat"
REASON_RATE = "rate_limit_exceeded"
MASK = "***"

RATE_LIMIT = 3          # messages allowed per window; the 4th inside the window is blocked
RATE_WINDOW_S = 2.0
MAX_MESSAGES = 1000

_LEET = str.maketrans({"@": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s"})
_STRIP = re.compile(r"[_.\-*​‌‍⁠﻿]")
_REPEAT = re.compile(r"(\S)\1{3,}", re.IGNORECASE)
_PUNCT_RUN = re.compile(r"[!?]{3,}")
_EDGE_PUNCT = ",;:?!.\"')]}"
_LEAD_PUNCT = "\"'([{"


def _load_words() -> frozenset:
    path = os.path.join(os.path.dirname(__file__), "..", "seed", "moderation_words.json")
    with open(path, encoding="utf-8") as fh:
        words = json.load(fh)["words"]
    return frozenset(_STRIP.sub("", w.lower()) for w in words)


WORDS = _load_words()


def normalise(token: str) -> str:
    """Leetspeak normalisation from the spec: @->a 0->o 1/!->i 3->e $->s, strip _ . - * and zero-width chars."""
    return _STRIP.sub("", token.lower().translate(_LEET))


def _candidates(token: str) -> set[str]:
    # `!` is both a leet `i` and plain punctuation ("s!c@m", "now!"): try it both ways.
    low = token.lower()
    return {normalise(token), normalise(low.replace("!", "")), normalise(low.replace("1", "l"))}


def _matches(norm: str) -> bool:
    if not norm:
        return False
    if norm in WORDS:
        return True
    # plurals: "scams", "bitches"
    return (norm.endswith("es") and norm[:-2] in WORDS) or (norm.endswith("s") and norm[:-1] in WORDS)


def is_profane(token: str) -> bool:
    return any(_matches(c) for c in _candidates(token))


def mask_token(token: str) -> str | None:
    """`***` (keeping surrounding plain punctuation) when the token is profane, else None."""
    core = token.lstrip(_LEAD_PUNCT)
    lead = token[: len(token) - len(core)]
    stripped = core.rstrip(_EDGE_PUNCT)
    tail = core[len(stripped):]
    if stripped and is_profane(stripped):
        return lead + MASK + tail
    if is_profane(token):
        return MASK
    return None


def mask_text(text: str) -> tuple[str, bool]:
    """Replace each offending whitespace-separated token in place; whitespace is preserved exactly."""
    parts = re.split(r"(\s+)", text)
    hit = False
    for i, part in enumerate(parts):
        if not part or part.isspace():
            continue
        masked = mask_token(part)
        if masked is not None:
            parts[i] = masked
            hit = True
    return "".join(parts), hit


def is_flood(text: str) -> bool:
    return bool(_REPEAT.search(text) or _PUNCT_RUN.search(text))


def rate_exceeded(previous: list[float], now: float, limit: int = RATE_LIMIT, window: float = RATE_WINDOW_S) -> bool:
    """True when `now` would be message limit+1 inside the sliding window ending at `now`."""
    return sum(1 for t in previous if now - t < window) >= limit


def validate_request(body) -> None:
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    if not is_str(body.get("chat_room_id"), 1, 128):
        bad.append("chat_room_id")
    msgs = body.get("incoming_messages")
    if not isinstance(msgs, list) or len(msgs) > MAX_MESSAGES:
        bad.append("incoming_messages")
    else:
        for m in msgs:
            if (not isinstance(m, dict) or not is_str(m.get("message_id"), 1, 128) or not is_str(m.get("sender"), 1, 128)
                    or not isinstance(m.get("text"), str) or len(m["text"]) > 4000
                    or ("sent_at" in m and (isinstance(m["sent_at"], bool) or not isinstance(m["sent_at"], (int, float))))):
                bad.append("incoming_messages")
                break
    if "check_dlq" in body and not isinstance(body["check_dlq"], bool):
        bad.append("check_dlq")
    failed = body.get("simulate_failed_notifications", 0)
    if not is_int(failed) or not 0 <= failed <= 100:
        bad.append("simulate_failed_notifications")
    if bad:
        raise validation_error(bad, "Invalid moderation request")


def moderate(messages: list[dict]) -> dict:
    """Apply the rules to messages in order. Returns filtered_messages, kicked/muted users, flagged_count and
    `blocked` ({message_id, sender, reason}) for the route to persist or report."""
    filtered, blocked = [], []
    kicked: dict[str, None] = {}
    muted: dict[str, None] = {}
    seen_at: dict[str, list[float]] = {}
    for m in messages:
        sender, text = m["sender"], m["text"]
        sent_at = m.get("sent_at")
        if sent_at is not None:
            history = seen_at.setdefault(sender, [])
            limited = rate_exceeded(history, float(sent_at))
            history.append(float(sent_at))
            if limited:
                muted.setdefault(sender)
                blocked.append({"message_id": m["message_id"], "sender": sender, "reason": REASON_RATE})
                continue
        if is_flood(text):
            muted.setdefault(sender)
            blocked.append({"message_id": m["message_id"], "sender": sender, "reason": REASON_FLOOD})
            continue
        masked, hit = mask_text(text)
        if hit:
            kicked.setdefault(sender)
        filtered.append({"message_id": m["message_id"], "sender": sender, "text": masked,
                         "flagged": hit, "reason": REASON_PROFANITY if hit else None})
    return {
        "filtered_messages": filtered,
        "kicked_users": list(kicked),
        "muted_users": list(muted),
        "flagged_count": sum(1 for f in filtered if f["flagged"]),
        "blocked": blocked,
    }


def sig_payload(chat_room_id: str, flagged_count: int, kicked_users: list[str], queue_depth: int) -> dict:
    """Exact DAY2 signature payload for POST /audit/v1/moderation/test (spec 5.3)."""
    return {"chat_room_id": chat_room_id, "flagged_count": flagged_count,
            "kicked_users": kicked_users, "queue_depth": queue_depth}
