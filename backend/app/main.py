import logging
import math
import time
import uuid

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .errors import ApiError, error_response
from .routes import api_v1, audit, rbac, ws

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="NaSCon League & Club Platform", version="1.0.0")

# Sliding-window limiter: 100 requests per rolling 10 s per client IP (atomic in Redis).
RATE_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, tostring(oldest[2])}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('PEXPIRE', key, math.ceil(window * 1000) + 1000)
return {1, '0'}
"""
_aredis = None


def _redis():
    global _aredis
    if _aredis is None:
        _aredis = aioredis.from_url(config.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
    return _aredis


class BodyLimitAndRateLimit:
    """Pure ASGI middleware: 413 before anything else, then /api/v1/* rate limiting."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    size = int(value)
                except ValueError:
                    size = 0
                if size > config.MAX_BODY_BYTES:
                    resp = error_response(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB")
                    return await resp(scope, receive, send)
        path = scope.get("path", "")
        if path.startswith("/api/v1/"):
            client = scope.get("client")
            ip = client[0] if client else "unknown"
            try:
                now = time.time()
                allowed, oldest = await _redis().eval(
                    RATE_LUA, 1, f"rl:{ip}", now, config.RATE_LIMIT_WINDOW_S, config.RATE_LIMIT_MAX,
                    f"{now}:{uuid.uuid4().hex}",
                )
                if int(allowed) == 0:
                    retry = max(1, math.ceil(float(oldest) + config.RATE_LIMIT_WINDOW_S - now))
                    resp = error_response(429, "RATE_LIMITED", "Too many requests", {"retry_after": retry},
                                          headers={"Retry-After": str(retry)})
                    return await resp(scope, receive, send)
            except Exception as exc:  # noqa: BLE001  limiter must never take the API down
                log.warning("rate limiter unavailable: %s", exc)
        return await self.app(scope, receive, send)


app.add_middleware(BodyLimitAndRateLimit)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return error_response(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    fields = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path", "header")]
        fields.append(".".join(loc) or "body")
    return error_response(400, "VALIDATION_ERROR", "Invalid request", {"fields": fields})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "INTERNAL_ERROR", "Unexpected server error")


app.include_router(audit.router)
app.include_router(rbac.router)
app.include_router(api_v1.router)
app.include_router(ws.router)
