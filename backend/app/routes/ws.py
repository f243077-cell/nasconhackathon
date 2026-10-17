"""Realtime fan-out over WebSocket: score updates, status changes, product pins (FR-1.3, FR-2.3)."""
import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import config
from ..auth import jwt_tokens
from ..errors import ApiError

router = APIRouter()


@router.websocket("/api/v1/ws")
async def realtime(ws: WebSocket, token: str | None = None, match_id: str | None = None):
    try:
        jwt_tokens.verify(token or "")
    except ApiError:
        await ws.close(code=4401)
        return
    await ws.accept()
    r = aioredis.from_url(config.REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe(config.REALTIME_CHANNEL)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                data = json.loads(msg["data"])
                if match_id is None or data.get("match_id") == match_id:
                    await ws.send_json(data)
            else:
                await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await pubsub.unsubscribe(config.REALTIME_CHANNEL)
        await r.aclose()
