"""RBAC matrix + 7 authorization probes (spec 5.13). Auth (401) first, then existence (404), then policy (403)."""
import json

from fastapi import APIRouter, Header

from ..auth import jwt_tokens, policy
from ..db import tx
from ..errors import ApiError
from .common import respond

router = APIRouter(prefix="/audit/v1")

DEMO_USERS = {
    "super_admin": "admin@nascon.test",
    "league_organizer": "organizer@nascon.test",
    "club_manager": "manager@nascon.test",
    "player": "player@nascon.test",
    "viewer": "viewer@nascon.test",
}
CONTEXT = {
    "tenant_id": "tenant-alpha", "foreign_tenant_id": "tenant-beta",
    "own_league_id": "league-alpha-1", "other_league_id": "league-alpha-2", "foreign_league_id": "league-beta-1",
    "own_club_id": "club-alpha-1", "other_club_id": "club-alpha-2", "foreign_club_id": "club-beta-1",
    "own_player_id": "player-alpha-1", "other_player_id": "player-alpha-2", "foreign_player_id": "player-beta-1",
}
ALLOWED = {"authorized": True}


def load_user(conn, email: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
    if row:
        row["league_ids"] = json.loads(row["league_ids"])
    return row


@router.post("/rbac-matrix")
def rbac_matrix():
    with tx() as conn:
        tokens = {}
        for role, email in DEMO_USERS.items():
            user = load_user(conn, email)
            if user is None:
                raise ApiError(503, "NOT_READY", "Demo users missing; call /audit/v1/reset")
            tokens[role] = jwt_tokens.issue(user)
    return {"tokens": tokens, "context": CONTEXT}


def _league(conn, league_id):
    row = conn.execute("SELECT league_id, tenant_id FROM leagues WHERE league_id = %s AND tenant_id IS NOT NULL",
                       (league_id,)).fetchone()
    if not row:
        raise ApiError(404, "LEAGUE_NOT_FOUND", "League not found", {"league_id": league_id})
    return {"tenant_id": row["tenant_id"], "league_id": row["league_id"]}


def _club(conn, club_id):
    row = conn.execute("SELECT club_id, tenant_id FROM clubs WHERE club_id = %s", (club_id,)).fetchone()
    if not row:
        raise ApiError(404, "CLUB_NOT_FOUND", "Club not found", {"club_id": club_id})
    return {"tenant_id": row["tenant_id"], "club_id": row["club_id"]}


def _player(conn, player_id):
    row = conn.execute("SELECT player_id, club_id, tenant_id FROM players WHERE player_id = %s",
                       (player_id,)).fetchone()
    if not row:
        raise ApiError(404, "PLAYER_NOT_FOUND", "Player not found", {"player_id": player_id})
    return {"tenant_id": row["tenant_id"], "club_id": row["club_id"], "player_id": row["player_id"]}


def probe(authorization: str | None, action: str, loader=None, ident=None):
    principal = jwt_tokens.principal_from_header(authorization)
    resource = None
    if loader is not None:
        with tx() as conn:
            resource = loader(conn, ident)
    if not policy.is_allowed(principal, action, resource):
        raise ApiError(403, "FORBIDDEN", "Not allowed", {"action": action})
    return respond(200, ALLOWED)


@router.post("/rbac/tenants")
def p1(authorization: str | None = Header(default=None)):
    return probe(authorization, "tenant.create")


@router.post("/rbac/leagues/{league_id}/fixtures")
def p2(league_id: str, authorization: str | None = Header(default=None)):
    return probe(authorization, "league.fixtures.write", _league, league_id)


@router.post("/rbac/clubs/{club_id}/roster")
def p3(club_id: str, authorization: str | None = Header(default=None)):
    return probe(authorization, "club.roster.write", _club, club_id)


@router.post("/rbac/clubs/{club_id}/products")
def p4(club_id: str, authorization: str | None = Header(default=None)):
    return probe(authorization, "club.products.write", _club, club_id)


@router.patch("/rbac/players/{player_id}")
def p5(player_id: str, authorization: str | None = Header(default=None)):
    return probe(authorization, "player.update", _player, player_id)


@router.get("/rbac/clubs/{club_id}")
def p6(club_id: str, authorization: str | None = Header(default=None)):
    return probe(authorization, "club.read", _club, club_id)


@router.get("/rbac/platform/config")
def p7(authorization: str | None = Header(default=None)):
    return probe(authorization, "platform.config.read")
