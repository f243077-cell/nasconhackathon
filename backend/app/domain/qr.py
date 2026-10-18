"""QR deep-link rules (FR-4.1, spec 5.6, ADR-13). Pure functions.

The short URL is fixed when the mapping is created; the target route is computed at read time from the
entity's live state, so a printed QR follows a match from live to VOD or to a postponement notice.
Routing reads only the match status, never a sport name.
"""
import hashlib
import hmac
from datetime import datetime, timezone

from ..errors import ApiError

# (id prefix, entity_type) - longest prefix first so "cs-session-" never falls through.
ENTITY_PREFIXES = (("cs-session-", "costream"), ("match-", "match"), ("player-", "player"), ("club-", "club"))
NOTICE_STATES = ("postponed", "cancelled", "abandoned")
MATCH_ROUTES = {"upcoming": "preview", "in_progress": "live", "completed": "vod"}
EXPORT_FORMATS = ("svg", "png", "pdf")

DEFAULT_SHORT_CODES = {"match-m1": "m1-live", "player-alpha-1": "p-alpha-1", "club-alpha-1": "c-alpha-1"}
_SHORT_PREFIX = {"match": "m", "player": "p", "club": "c", "costream": "cs"}


def entity_type(entity_id) -> str | None:
    if not isinstance(entity_id, str):
        return None
    for prefix, kind in ENTITY_PREFIXES:
        if entity_id.startswith(prefix) and len(entity_id) > len(prefix):
            return kind
    return None


def require_entity_type(entity_id) -> str:
    kind = entity_type(entity_id)
    if kind is None:
        raise ApiError(404, "QR_NOT_FOUND", "No QR code for that entity", {"entity_id": entity_id})
    return kind


def target_route(entity_id: str, status: str | None = None) -> str:
    """Guest Web Player route for the entity's current state (spec 5.6 table)."""
    kind = require_entity_type(entity_id)
    if kind == "match":
        if status in NOTICE_STATES:
            return f"/web/matches/{entity_id}/notice?state={status}"
        return f"/web/matches/{entity_id}/{MATCH_ROUTES.get(status, 'preview')}"
    if kind == "player":
        return f"/web/players/{entity_id}"
    if kind == "club":
        return f"/web/clubs/{entity_id}"
    return f"/web/costream/{entity_id}"


def deep_link_uri(entity_id: str) -> str:
    """Native app link: co-streams open the stream screen, everything else the entity screen."""
    if require_entity_type(entity_id) == "costream":
        return f"nascon://stream/{entity_id}"
    return f"nascon://entity/{entity_id}"


def short_code_for(entity_id: str, salt: str) -> str:
    """Stable code for an entity without a seeded mapping: type prefix + 10 hex of HMAC(DAY2_SALT, id).
    Same id + same salt -> same code, so regenerating never changes a printed URL."""
    if entity_id in DEFAULT_SHORT_CODES:
        return DEFAULT_SHORT_CODES[entity_id]
    kind = require_entity_type(entity_id)
    digest = hmac.new(salt.encode("utf-8"), entity_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{_SHORT_PREFIX[kind]}-{digest[:10]}"


def short_url(base: str, code: str) -> str:
    return f"{base}/q/{code}"


def export_urls(base: str, entity_id: str) -> dict:
    return {fmt: f"{base}/audit/v1/qr/{entity_id}/export.{fmt}" for fmt in EXPORT_FORMATS}


def build_view(entity_id: str, status: str | None, code: str, scan_count: int, base: str = "http://localhost:8080") -> dict:
    """GET /audit/v1/qr/{entity_id} response without `signature`."""
    return {
        "entity_id": entity_id,
        "entity_type": require_entity_type(entity_id),
        "entity_status": status,
        "short_url": short_url(base, code),
        "target_route": target_route(entity_id, status),
        "deep_link_uri": deep_link_uri(entity_id),
        "scan_count": scan_count,
        "export_formats": export_urls(base, entity_id),
    }


def sig_payload(view: dict) -> dict:
    """Exact DAY2 signature payload (spec 5.3), from the CURRENT view so it changes with the target route."""
    return {"entity_id": view["entity_id"], "short_url": view["short_url"], "target_route": view["target_route"]}


# ---- privacy-safe telemetry (NFR-9): device family + UTC hour bucket only, never the UA or IP ----

_MOBILE_HINTS = ("mobi", "android", "iphone", "ipad", "ipod", "windows phone", "blackberry", "opera mini")


def device_family(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    return "mobile" if any(h in ua for h in _MOBILE_HINTS) else "desktop"


def hour_bucket(at: datetime) -> str:
    """UTC hour, e.g. 2026-10-18T11:00Z. A naive datetime is taken as UTC."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00Z")
