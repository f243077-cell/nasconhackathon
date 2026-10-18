"""MediaMTX control-API client (FR-3.2). Best effort with short timeouts: the API must never hang a request."""
import json
import logging
import time
import urllib.error
import urllib.request

from .. import config
from . import bus

log = logging.getLogger("media")
KICK_ROUTES = {"rtmpConn": "rtmpconns", "webRTCSession": "webrtcsessions", "rtspSession": "rtspsessions",
               "srtConn": "srtconns"}


def _call(method: str, path: str, timeout: float = 1.0):
    req = urllib.request.Request(config.MEDIAMTX_API + path, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return json.loads(body) if body else None


def reachable() -> bool:
    try:
        _call("GET", "/v3/paths/list")
        return True
    except Exception:  # noqa: BLE001
        return False


def kick_publisher(stream_key: str) -> bool:
    """Revoke/rotate must cut an active ingest within 2 s: find the path's source and kick it."""
    try:
        path = _call("GET", f"/v3/paths/get/live/{stream_key}")
        src = (path or {}).get("source") or {}
        route = KICK_ROUTES.get(src.get("type"))
        if route and src.get("id"):
            _call("POST", f"/v3/{route}/kick/{src['id']}")
            return True
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            log.warning("kick %s failed: %s", stream_key, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("kick %s failed: %s", stream_key, exc)
    return False


def stream_stats() -> tuple[int, float]:
    """(active streams, aggregate inbound kbps). kbps is derived from bytesReceived deltas kept in Redis."""
    try:
        items = (_call("GET", "/v3/paths/list") or {}).get("items", [])
    except Exception:  # noqa: BLE001
        return 0, 0.0
    ready = [p for p in items if p.get("ready")]
    total_bytes = sum(int(p.get("bytesReceived", 0)) for p in ready)
    now = time.time()
    kbps = 0.0
    try:
        r = bus.client()
        prev = r.get("metrics:bytes")
        if prev:
            pb, pt = prev.decode().split(":")
            dt = now - float(pt)
            if dt > 0 and total_bytes >= int(pb):
                kbps = (total_bytes - int(pb)) * 8 / 1000 / dt
        r.set("metrics:bytes", f"{total_bytes}:{now}", ex=300)
    except Exception:  # noqa: BLE001
        pass
    return len(ready), round(kbps, 1)
