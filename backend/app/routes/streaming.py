"""POST /api/v1/stream/key: the app's wrapper of the audit stream-key logic (FR-3.2, AGREED_RULES II 4).
A member manages only their own player's key; the platform admin may act for any player."""
from fastapi import APIRouter, Depends

from ..errors import ApiError, validation_error
from ..repo import day2 as day2_repo
from .api_v1 import principal
from .common import json_body, respond, run_tx

router = APIRouter()


@router.post("/api/v1/stream/key")
def member_stream_key(body=Depends(json_body), p: dict = Depends(principal)):
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    if p.get("role") != "super_admin":
        if not p.get("player_id"):
            raise ApiError(403, "FORBIDDEN", "Only athletes can stream", {"action": "stream.key"})
        body = {**body, "player_id": p["player_id"]}
    status, resp = run_tx(day2_repo.stream_key, body)
    return respond(status, day2_repo.kick_after_commit(resp))
