"""4-way co-stream session init and host-drop handoff (FR-3.3, spec 5.5). Pure functions.

Checks run in the spec's exact order:
1. schema -> 400 VALIDATION_ERROR
2. every participant, then the host, exists -> 404 PLAYER_NOT_FOUND; host not in participants -> 400 VALIDATION_ERROR
3. more than 4 participants -> 409 COSTREAM_SESSION_FULL
4. layout capacity against the count AFTER the handoff rule -> 400 UNSUPPORTED_LAYOUT (ADR: a host drop that
   leaves 2 people on grid_2 is valid; the layout must fit who is actually on screen)
5. handoff: drop -> next participant in array order hosts; nobody left -> terminated
"""
import base64
import hmac
import json
from typing import Callable

from ..canonical import canonical
from ..errors import ApiError, validation_error
from ..validate import is_id, is_str

MAX_PARTICIPANTS = 4
LAYOUTS = ("solo", "grid_2", "grid_4", "spotlight")
LAYOUT_CAPACITY = {"solo": 1, "grid_2": 2, "grid_4": 4, "spotlight": 4}
DEFAULT_LAYOUT = "grid_4"


def validate_request(body) -> dict:
    """Step 1. Returns the request with defaults applied (layout, simulate_host_drop)."""
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    if not is_id(body.get("session_id")):
        bad.append("session_id")
    if not is_str(body.get("host_player_id"), 1, 128):
        bad.append("host_player_id")
    parts = body.get("participants")
    if (not isinstance(parts, list) or not parts or not all(is_str(p, 1, 128) for p in parts)
            or len(set(parts)) != len(parts)):
        bad.append("participants")
    drop = body.get("simulate_host_drop", False)
    if not isinstance(drop, bool):
        bad.append("simulate_host_drop")
    layout = body.get("layout", DEFAULT_LAYOUT)
    if layout not in LAYOUTS:
        bad.append("layout")
    if bad:
        raise validation_error(bad, "Invalid co-stream request")
    return {"session_id": body["session_id"], "host_player_id": body["host_player_id"], "participants": list(parts),
            "layout": layout, "simulate_host_drop": drop}


def check_players(req: dict, player_exists: Callable[[str], bool]) -> None:
    """Step 2: existence (404) before membership (400)."""
    for pid in [*req["participants"], req["host_player_id"]]:
        if not player_exists(pid):
            raise ApiError(404, "PLAYER_NOT_FOUND", "Player not found", {"player_id": pid})
    if req["host_player_id"] not in req["participants"]:
        raise validation_error(["host_player_id"], "The host must be one of the participants")


def handoff(participants: list[str], host: str, drop: bool) -> dict:
    """Step 5. When the host drops, they leave and the next participant in array order takes over."""
    if not drop:
        return {"status": "active", "active_host": host, "handoff_occurred": False,
                "participant_count": len(participants), "active_participants": list(participants)}
    remaining = [p for p in participants if p != host]
    if not remaining:
        return {"status": "terminated", "active_host": None, "handoff_occurred": False,
                "participant_count": 0, "active_participants": []}
    return {"status": "active", "active_host": remaining[0], "handoff_occurred": True,
            "participant_count": len(remaining), "active_participants": remaining}


def plan_session(body, player_exists: Callable[[str], bool], media_base: str = "http://localhost:8888") -> dict:
    """Steps 1-5. Returns the response body without `signature`."""
    req = validate_request(body)
    check_players(req, player_exists)
    if len(req["participants"]) > MAX_PARTICIPANTS:
        raise ApiError(409, "COSTREAM_SESSION_FULL", "A co-stream holds at most 4 broadcasters",
                       {"session_id": req["session_id"], "participant_count": len(req["participants"]),
                        "max_participants": MAX_PARTICIPANTS})
    result = handoff(req["participants"], req["host_player_id"], req["simulate_host_drop"])
    if result["participant_count"] > LAYOUT_CAPACITY[req["layout"]]:
        raise ApiError(400, "UNSUPPORTED_LAYOUT", "This layout can't fit that many broadcasters",
                       {"layout": req["layout"], "participant_count": result["participant_count"],
                        "max_for_layout": LAYOUT_CAPACITY[req["layout"]]})
    sid = req["session_id"]
    return {
        "session_id": sid,
        "status": result["status"],
        "active_host": result["active_host"],
        "handoff_occurred": result["handoff_occurred"],
        "participant_count": result["participant_count"],
        "active_participants": result["active_participants"],
        "layout": req["layout"],
        "composite_playback_url": f"{media_base}/costream/{sid}/index.m3u8",
        "chat_room_id": chat_room_id(sid),
    }


def chat_room_id(session_id: str) -> str:
    """Exactly one room per session, kept across handoffs."""
    return f"chat-{session_id}"


def sig_payload(resp: dict) -> dict:
    """Exact DAY2 signature payload for POST /audit/v1/costream/session (spec 5.3), from the response values."""
    return {k: resp[k] for k in ("active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status")}


# ------------------------------------------------------------------ host controls (FR-3.3)
# Session state kept by the repo: {session_id, status, host, participants (active, in order), layout,
# muted [], spotlight, kicked []}. Only the active host may invite, mute, spotlight or kick.
INVITE_TTL_S = 600
CONTROL_ACTIONS = ("mute", "unmute", "spotlight", "kick")


def state_from_response(resp: dict) -> dict:
    return {"session_id": resp["session_id"], "status": resp["status"], "host": resp["active_host"],
            "participants": list(resp["active_participants"]), "layout": resp["layout"],
            "muted": [], "spotlight": None, "kicked": []}


def view(state: dict, media_base: str = "http://localhost:8888") -> dict:
    sid = state["session_id"]
    return {"session_id": sid, "status": state["status"], "active_host": state["host"],
            "participant_count": len(state["participants"]), "active_participants": list(state["participants"]),
            "layout": state["layout"], "muted": list(state["muted"]), "spotlight": state["spotlight"],
            "composite_playback_url": f"{media_base}/costream/{sid}/index.m3u8", "chat_room_id": chat_room_id(sid)}


def _require_live(state: dict) -> None:
    if state["status"] != "active":
        raise ApiError(404, "STREAM_NOT_FOUND", "This co-stream has ended", {"session_id": state["session_id"]})


def _require_host(state: dict, actor: str | None) -> None:
    if actor != state["host"]:
        raise ApiError(403, "FORBIDDEN", "Only the host can do that", {"session_id": state["session_id"]})


def _require_participant(state: dict, player_id) -> None:
    if not is_str(player_id, 1, 128):
        raise validation_error(["player_id"], "player_id is required")
    if player_id not in state["participants"]:
        raise ApiError(404, "PLAYER_NOT_FOUND", "That player isn't in this co-stream", {"player_id": player_id})


def apply_control(state: dict, actor: str | None, action: str, target) -> dict:
    """mute / unmute / spotlight / kick by the host. Idempotent: repeating an action changes nothing."""
    if action not in CONTROL_ACTIONS:
        raise validation_error(["action"], "Unknown host control")
    _require_live(state)
    _require_host(state, actor)
    _require_participant(state, target)
    new = {**state, "participants": list(state["participants"]), "muted": list(state["muted"]),
           "kicked": list(state["kicked"])}
    if action == "mute" and target not in new["muted"]:
        new["muted"].append(target)
    elif action == "unmute" and target in new["muted"]:
        new["muted"].remove(target)
    elif action == "spotlight":
        new["spotlight"], new["layout"] = target, "spotlight"
    elif action == "kick":
        if target == state["host"]:
            raise validation_error(["player_id"], "The host can't kick themselves")
        new["participants"].remove(target)
        if target in new["muted"]:
            new["muted"].remove(target)
        if new["spotlight"] == target:
            new["spotlight"] = None
        new["kicked"].append(target)
    return new


def host_drop(state: dict) -> dict:
    """The host disconnected: the next participant in array order hosts, or the session ends (5.5 step 5)."""
    _require_live(state)
    result = handoff(state["participants"], state["host"], True)
    new = {**state, "status": result["status"], "host": result["active_host"],
           "participants": result["active_participants"]}
    new["muted"] = [m for m in state["muted"] if m in new["participants"]]
    if new["spotlight"] not in new["participants"]:
        new["spotlight"] = None
    return new


def invite_payload(session_id: str, player_id: str, issued_at: int, ttl: int = INVITE_TTL_S) -> dict:
    return {"session_id": session_id, "player_id": player_id, "exp": issued_at + ttl}


def make_invite(payload: dict, sign: Callable[[str, dict], str]) -> str:
    """inv.<base64url canonical payload>.<HMAC over session_id|payload>; `sign` is sign_day2."""
    body = base64.urlsafe_b64encode(canonical(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"inv.{body}.{sign(payload['session_id'], payload)}"


def read_invite(token, sign: Callable[[str, dict], str], now: int) -> dict:
    """Payload of a valid, unexpired invite; anything else is 403 FORBIDDEN (never reveals which check failed)."""
    denied = ApiError(403, "FORBIDDEN", "This invite is invalid or has expired")
    if not isinstance(token, str) or token.count(".") != 2 or not token.startswith("inv."):
        raise denied
    _, body, sig = token.split(".")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        raise denied from None
    if (not isinstance(payload, dict) or not isinstance(payload.get("session_id"), str)
            or not hmac.compare_digest(sign(payload["session_id"], payload), sig)
            or not isinstance(payload.get("exp"), int) or now > payload["exp"]):
        raise denied
    return payload


def join(state: dict, player_id: str, invite: dict) -> dict:
    """Accept an invite: the invite must name this session and this player; capacity and layout still apply."""
    _require_live(state)
    if invite.get("session_id") != state["session_id"] or invite.get("player_id") != player_id:
        raise ApiError(403, "FORBIDDEN", "This invite is for someone else")
    if player_id in state["participants"]:
        return state
    if player_id in state["kicked"]:
        raise ApiError(403, "FORBIDDEN", "You were removed from this co-stream")
    if len(state["participants"]) >= MAX_PARTICIPANTS:
        raise ApiError(409, "COSTREAM_SESSION_FULL", "A co-stream holds at most 4 broadcasters",
                       {"session_id": state["session_id"], "participant_count": len(state["participants"]),
                        "max_participants": MAX_PARTICIPANTS})
    if len(state["participants"]) + 1 > LAYOUT_CAPACITY[state["layout"]]:
        raise ApiError(400, "UNSUPPORTED_LAYOUT", "This layout can't fit another broadcaster",
                       {"layout": state["layout"], "participant_count": len(state["participants"]) + 1,
                        "max_for_layout": LAYOUT_CAPACITY[state["layout"]]})
    return {**state, "participants": [*state["participants"], player_id]}
