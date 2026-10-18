"""FR-3.1 athlete profile + follow (/api/v1/athletes/*) and the FR-3.2 VOD index hook."""
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..auth import policy
from ..db import tx
from ..errors import ApiError
from ..repo import athletes as athletes_repo
from .api_v1 import principal, principal_or_guest
from .common import respond, run_tx

router = APIRouter()


def _check_tenant(p: dict, player: dict) -> None:
    """Guests read public athlete pages (the Guest Web Player /web/players/{id}); members stay in their tenant."""
    if p.get("role") == "guest":
        return
    if not policy.is_allowed(p, "club.read", {"tenant_id": player["tenant_id"], "club_id": player["club_id"]}):
        raise ApiError(403, "FORBIDDEN", "You don't have permission to do that", {"action": "club.read"})


@router.get("/api/v1/athletes/{player_id}")
def athlete_profile(player_id: str, p: dict = Depends(principal_or_guest)):
    with tx() as conn:
        player = athletes_repo.get_player(conn, player_id)
        _check_tenant(p, player)
        viewer = p["sub"] if p.get("role") != "guest" else None
        return athletes_repo.profile(conn, player, viewer)


def _toggle(player_id: str, p: dict, follow: bool):
    def apply(conn):
        player = athletes_repo.get_player(conn, player_id)
        _check_tenant(p, player)
        return athletes_repo.set_follow(conn, p["sub"], p.get("player_id"), player_id, follow)
    return respond(200, run_tx(apply))


@router.post("/api/v1/athletes/{player_id}/follow")
def follow(player_id: str, p: dict = Depends(principal)):
    return _toggle(player_id, p, True)


@router.delete("/api/v1/athletes/{player_id}/follow")
def unfollow(player_id: str, p: dict = Depends(principal)):
    return _toggle(player_id, p, False)


@router.post("/internal/media/recorded")
async def media_recorded(request: Request):
    """MediaMTX runOnRecordSegmentComplete hook: {"path": "live/<key>", "segment_path": "...", "started_at"?, "ended_at"?}."""
    try:
        data = json.loads(await request.body() or b"{}")
    except ValueError:
        return Response(status_code=400)
    if not isinstance(data, dict) or not isinstance(data.get("path"), str) or not isinstance(data.get("segment_path"), str):
        return Response(status_code=400)
    vod = run_tx(athletes_repo.index_recording, data["path"], data["segment_path"], data.get("started_at"),
                 data.get("ended_at"))
    return respond(201 if vod else 202, vod or {"indexed": False})
