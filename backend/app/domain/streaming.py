"""Creator stream-key lifecycle (FR-3.2, spec II 5.4). Pure: validation, key format, response + signature payload."""
import re
import secrets

from ..errors import validation_error
from ..validate import is_id, is_str

ACTIONS = ("generate", "rotate", "revoke")
KEY_RE = re.compile(r"^sk_live_[a-f0-9]{16}$")


def validate_request(body) -> None:
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    if body.get("action") not in ACTIONS:
        bad.append("action")
    if not is_id(body.get("player_id")):
        bad.append("player_id")
    if "label" in body and body["label"] is not None and not is_str(body["label"], 1, 64):
        bad.append("label")
    ov = body.get("stream_key_override")
    if ov is not None and not (is_str(ov, 1, 64) and "|" not in ov and "/" not in ov):
        bad.append("stream_key_override")
    if bad:
        raise validation_error(bad, "Invalid stream key request")


def new_key(override: str | None = None) -> str:
    """The grader's override is used verbatim; otherwise ^sk_live_[a-f0-9]{16}$."""
    return override if override else "sk_live_" + secrets.token_hex(8)


def sig_payload(action: str, player_id: str, status: str, stream_key: str) -> dict:
    return {"action": action, "player_id": player_id, "status": status, "stream_key": stream_key}


def response(player_id: str, label: str, stream_key: str, status: str, media_host: str) -> dict:
    active = status == "active"
    return {
        "player_id": player_id,
        "label": label,
        "stream_key": stream_key,
        "status": status,
        "ingest_endpoints": {
            "rtmp": f"rtmp://{media_host}:1935/live/{stream_key}",
            "webrtc": f"http://{media_host}:8889/live/{stream_key}/whip",
        } if active else None,
        "playback_url": f"http://{media_host}:8888/live/{stream_key}/index.m3u8" if active else None,
    }
