"""Realtime fan-out over WebSocket/SSE: score updates, status changes, product pins (FR-1.3, FR-2.3, NFR-1)."""
import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from .. import config
from ..auth import jwt_tokens
from ..db import tx
from ..errors import ApiError
from ..repo import events as events_repo

router = APIRouter()
WS_GAUGE = "metrics:ws_active"


def _snapshot(match_id: str) -> dict:
    with tx() as conn:
        proj = events_repo.score(conn, match_id)
    return {"type": "snapshot", "match_id": match_id,
            "data": {"status": proj["status"], "home_score": proj["home"]["score"],
                     "away_score": proj["away"]["score"], "version": proj["version"]}}


async def _relay(ws: WebSocket, match_id: str | None, snapshot: dict | None = None):
    r = aioredis.from_url(config.REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe(config.REALTIME_CHANNEL)
    await r.incr(WS_GAUGE)
    try:
        if snapshot:
            await ws.send_json(snapshot)
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                data = json.loads(msg["data"])
                if match_id is None or data.get("match_id") == match_id:
                    await ws.send_json(data)
            else:
                await asyncio.sleep(0.01)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await r.decr(WS_GAUGE)
        await pubsub.unsubscribe(config.REALTIME_CHANNEL)
        await r.aclose()


@router.websocket("/api/v1/ws")
async def realtime(ws: WebSocket, token: str | None = None, match_id: str | None = None):
    try:
        jwt_tokens.verify(token or "")
    except ApiError:
        await ws.close(code=4401)
        return
    await ws.accept()
    await _relay(ws, match_id)


@router.websocket("/ws/matches/{match_id}")
async def match_feed(ws: WebSocket, match_id: str):
    """Read-only live score feed (NFR-1): open to guests; first message is a snapshot, then every update."""
    try:
        snapshot = await asyncio.to_thread(_snapshot, match_id)
    except ApiError:
        await ws.close(code=4404)
        return
    await ws.accept()
    await _relay(ws, match_id, snapshot)


@router.get("/api/v1/matches/{match_id}/stream")
async def match_sse(match_id: str):
    """SSE alternative to the WebSocket feed (NFR-1)."""
    snapshot = await asyncio.to_thread(_snapshot, match_id)

    async def gen():
        r = aioredis.from_url(config.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(config.REALTIME_CHANNEL)
        try:
            yield f"data: {json.dumps(snapshot)}\n\n"
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg and msg.get("type") == "message":
                    data = json.loads(msg["data"])
                    if data.get("match_id") == match_id:
                        yield f"data: {json.dumps(data)}\n\n"
                else:
                    yield ": keep-alive\n\n"
        finally:
            await pubsub.unsubscribe(config.REALTIME_CHANNEL)
            await r.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
