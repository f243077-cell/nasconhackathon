"""FR-3.3 co-stream host controls for the app (/api/v1/costream/*): create, view, signed invites, join, mute,
spotlight, kick and host leave. The acting player is the caller's own player_id; only the active host controls."""
import asyncio
import json
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, WebSocket

from .. import config
from ..auth import jwt_tokens
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


# ------------------------------------------------------------------ host presence (FR-3.3, hidden scenario 1)
def _drop_if_host(session_id: str, player_id: str) -> dict | None:
    """The socket of the active host closed: hand off in array order, or end the session. No-op otherwise
    (the player already left, was kicked, or is not the host)."""
    try:
        return run_tx(social_repo.host_drop, session_id, player_id)
    except ApiError:
        return None


@router.websocket("/sessions/{session_id}/ws")
async def presence(ws: WebSocket, session_id: str, token: str | None = None):
    """A broadcaster's live connection. Sends the session view, then every update for this session. When the
    active host's socket drops, hosting moves to the next participant immediately (well inside 1.5 s); both
    tasks are cancelled and awaited, so nothing is left running."""
    try:
        claims = jwt_tokens.verify(token or "")
    except ApiError:
        await ws.close(code=4401)
        return
    player_id = claims.get("player_id")
    try:
        snapshot = await asyncio.to_thread(_view, session_id)
    except ApiError:
        await ws.close(code=4404)
        return
    await ws.accept()
    r = aioredis.from_url(config.REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe(config.REALTIME_CHANNEL)

    async def receive():
        while True:
            await ws.receive_text()      # pings from the app; raises WebSocketDisconnect on close

    async def send():
        await ws.send_json({"type": "costream_snapshot", "match_id": None, "data": snapshot})
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                data = json.loads(msg["data"])
                body = data.get("data") or {}
                if body.get("session_id") == session_id or body.get("chat_room_id") == f"chat-{session_id}":
                    await ws.send_json(data)
            else:
                await asyncio.sleep(0.01)

    tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pubsub.unsubscribe(config.REALTIME_CHANNEL)
        await r.aclose()
        if player_id:
            await asyncio.to_thread(_drop_if_host, session_id, player_id)


def _view(session_id: str) -> dict:
    with tx() as conn:
        return social_repo.session_view(conn, session_id)


# ------------------------------------------------------------------ guest viewers (FR-3.3 unified chat, FR-4.2)
viewer_router = APIRouter()


@viewer_router.websocket("/ws/costream/{session_id}")
async def costream_feed(ws: WebSocket, session_id: str):
    """Read-only feed for the Guest Web Player on /web/costream/{id}: session updates and the room's chat
    (chat-{session_id}), open to guests. The session may not exist yet (a viewer can arrive before the host)."""
    await ws.accept()
    try:
        snapshot = await asyncio.to_thread(_view, session_id)
    except ApiError:
        snapshot = None
    r = aioredis.from_url(config.REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe(config.REALTIME_CHANNEL)

    async def receive():
        while True:
            await ws.receive_text()

    async def send():
        if snapshot:
            await ws.send_json({"type": "costream_snapshot", "match_id": session_id, "data": snapshot})
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                data = json.loads(msg["data"])
                body = data.get("data") or {}
                if data.get("match_id") == session_id or body.get("session_id") == session_id \
                        or body.get("chat_room_id") == f"chat-{session_id}":
                    await ws.send_json(data)
            else:
                await asyncio.sleep(0.01)

    tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pubsub.unsubscribe(config.REALTIME_CHANNEL)
        await r.aclose()
