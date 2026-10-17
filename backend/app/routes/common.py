import json
import logging

import psycopg
from fastapi import Request
from fastapi.responses import JSONResponse

from .. import config
from ..db import tx
from ..errors import ApiError, validation_error

log = logging.getLogger("routes")


async def json_body(request: Request):
    """Parse the raw body ourselves: 413 over 1 MB, 400 on malformed JSON, None when empty."""
    raw = await request.body()
    if len(raw) > config.MAX_BODY_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB")
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise validation_error(["body"], "Malformed JSON") from exc


def run_tx(fn, *args, retries: int = 2):
    """Run fn(conn, *args) in one transaction; retry on unique-race / serialization / deadlock."""
    for attempt in range(retries + 1):
        try:
            with tx() as conn:
                return fn(conn, *args)
        except (psycopg.errors.UniqueViolation, psycopg.errors.SerializationFailure,
                psycopg.errors.DeadlockDetected):
            if attempt == retries:
                raise
            log.info("retrying transaction after concurrency conflict")


def respond(status: int, body) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)
