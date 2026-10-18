"""Part II autograder interface (spec II 5): stream keys, QR, short links, metrics, privacy, media auth hook."""
import json

import redis.asyncio as aioredis
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import RedirectResponse, Response

from .. import config
from ..db import tx
from ..errors import ApiError, validation_error
from ..repo import day2 as day2_repo
from ..services import bus, media, qr_export
from ..services import metrics as metrics_text
from ..validate import is_id
from .common import json_body, respond, run_tx

router = APIRouter()
EXPORT_TYPES = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}


@router.post("/audit/v1/stream/key")
def stream_key(body=Depends(json_body)):
    status, resp = run_tx(day2_repo.stream_key, body)
    return respond(status, day2_repo.kick_after_commit(resp))


@router.post("/audit/v1/stream/publish")
def stream_publish(body=Depends(json_body)):
    """Ingest activation check: revoked keys are refused with 409 KEY_REVOKED (same rule as the media auth hook)."""
    if not isinstance(body, dict) or not isinstance(body.get("stream_key"), str):
        raise validation_error(["stream_key"], "stream_key is required")
    with tx() as conn:
        return day2_repo.publish_check(conn, body["stream_key"])


@router.post("/internal/media/auth")
async def media_auth(request: Request):
    """MediaMTX HTTP auth hook: publish on live/<key> only with an active key; reads are open (guest playback)."""
    try:
        data = json.loads(await request.body() or b"{}")
    except ValueError:
        return Response(status_code=400)
    if data.get("action") != "publish":
        return Response(status_code=200)
    path = data.get("path") or ""
    if path.startswith("costream/"):
        return Response(status_code=200)
    if path.startswith("live/"):
        with tx() as conn:
            if day2_repo.key_status(conn, path[len("live/"):]) == "active":
                return Response(status_code=200)
    return Response(status_code=401)


_aredis = None


def _cache():
    global _aredis
    if _aredis is None:
        _aredis = aioredis.from_url(config.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
    return _aredis


@router.get("/audit/v1/qr/{entity_id}")
async def qr_resolve(entity_id: str, inspect: bool = False, user_agent: str | None = Header(default=None)):
    """Read-only inspections (the k6 guest-viewer load, NFR-2) are served from a short Redis cache that is
    invalidated on every scan and every match event, so the route and scan count stay exact."""
    key = bus.qr_cache_key(entity_id)
    if inspect:
        try:
            hit = await _cache().get(key)
            if hit:
                return Response(content=hit, media_type="application/json")
        except Exception:  # noqa: BLE001  cache is optional
            pass
    resp = await run_in_threadpool(run_tx, day2_repo.qr_resolve, entity_id, inspect, user_agent)
    try:
        if inspect:
            await _cache().set(key, json.dumps(resp, ensure_ascii=False, separators=(",", ":")), px=1500)
        else:
            await _cache().delete(key)
    except Exception:  # noqa: BLE001
        pass
    return respond(200, resp)


@router.get("/audit/v1/qr/{entity_id}/export.{fmt}")
def qr_export_route(entity_id: str, fmt: str):
    if fmt not in EXPORT_TYPES:
        raise validation_error(["fmt"], "Format must be svg, png or pdf")
    with tx() as conn:
        url, title = day2_repo.qr_export_info(conn, entity_id)
    body = {"svg": lambda: qr_export.svg(url), "png": lambda: qr_export.png(url),
            "pdf": lambda: qr_export.pdf(entity_id, url, title)}[fmt]()
    return Response(content=body, media_type=EXPORT_TYPES[fmt],
                    headers={"Content-Disposition": f'inline; filename="qr-{entity_id}.{fmt}"'})


@router.get("/q/{short_code}")
def short_link(short_code: str, user_agent: str | None = Header(default=None)):
    route = run_tx(day2_repo.qr_redirect, short_code, user_agent)
    return RedirectResponse(url=route, status_code=302)


@router.get("/metrics")
def metrics():
    with tx() as conn:
        counts = day2_repo.metric_counts(conn)
    streams, kbps = media.stream_stats()
    try:
        ws = int(bus.client().get("metrics:ws_active") or 0)
    except Exception:  # noqa: BLE001
        ws = 0
    body = metrics_text.render({
        "nascon_active_ws_connections": ws,
        "nascon_active_streams_total": streams,
        "nascon_stream_bitrate_kbps": kbps,
        "nascon_dlq_depth": counts["dlq"],
        "nascon_qr_scans_total": counts["qr"],
    })
    return Response(content=body, headers={"Content-Type": metrics_text.CONTENT_TYPE})


@router.delete("/audit/v1/privacy/user/{user_id}")
def privacy_erase(user_id: str):
    if not is_id(user_id):
        raise validation_error(["user_id"], "Invalid user id")
    return respond(200, run_tx(day2_repo.erase_user, user_id))
