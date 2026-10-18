"""FR-3.3 co-stream host controls for the app (/api/v1/costream/*): create, view, signed invites, join, mute,
spotlight, kick and host leave. The acting player is the caller's own player_id; only the active host controls."""
import time

from fastapi import APIRouter, Depends

from ..db import tx
from ..errors import ApiError, validation_error
from ..repo import social as social_repo
from .api_v1 import principal, principal_or_guest
from .common import json_body, respond, run_tx

router = APIRouter(prefix="/api/v1/costream")


def _player(p: dict) -> str:
    pid = p.get("player_id")
    if not pid:
        raise ApiError(403, "FORBIDDEN", "Only athletes can broadcast", {"action": "costream"})
    return pid


def _body(body) -> dict:
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    return body


@router.post("/sessions")
def create_session(body=Depends(json_body), p: dict = Depends(principal)):
    """Start a co-stream as its host (same rules and response as the audit route)."""
    body = _body(body)
    if p.get("role") != "super_admin" and body.get("host_player_id") != _player(p):
        raise ApiError(403, "FORBIDDEN", "You can only host your own co-stream", {"action": "costream.create"})
    status, resp = run_tx(social_repo.costream_session, body)
    return respond(status, resp)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, p: dict = Depends(principal_or_guest)):
    with tx() as conn:
        return social_repo.session_view(conn, session_id)


@router.post("/sessions/{session_id}/invite")
def invite(session_id: str, body=Depends(json_body), p: dict = Depends(principal)):
    """Signed invite token for a squad member, pushed to them over the realtime bus (DLQ on failure)."""
    body = _body(body)
    return respond(201, run_tx(social_repo.invite, session_id, _player(p), body.get("player_id"),
                               body.get("simulate_dlq") is True, int(time.time())))


@router.post("/sessions/{session_id}/join")
def join(session_id: str, body=Depends(json_body), p: dict = Depends(principal)):
    body = _body(body)
    return respond(200, run_tx(social_repo.join, session_id, _player(p), body.get("invite_token"), int(time.time())))


def _control(action: str):
    def route(session_id: str, body=Depends(json_body), p: dict = Depends(principal)):
        body = _body(body)
        act = action
        if action == "mute" and body.get("muted") is False:
            act = "unmute"
        return respond(200, run_tx(social_repo.host_control, session_id, _player(p), act, body.get("player_id")))
    route.__name__ = f"costream_{action}"
    return route


router.post("/sessions/{session_id}/mute")(_control("mute"))
router.post("/sessions/{session_id}/spotlight")(_control("spotlight"))
router.post("/sessions/{session_id}/kick")(_control("kick"))


@router.post("/sessions/{session_id}/leave")
def leave(session_id: str, p: dict = Depends(principal)):
    """The host leaves: hosting moves to the next participant in array order, or the session ends."""
    return respond(200, run_tx(social_repo.host_drop, session_id, _player(p)))
