"""Negative-authorization tests for every role boundary of the spec 5.13 matrix (FR-5.1)."""
import time

import jwt as pyjwt
import pytest

from app import config
from app.auth import jwt_tokens, policy
from app.errors import ApiError

P = {
    "super_admin": {"role": "super_admin", "tenant_id": None, "league_ids": [], "club_id": None, "player_id": None},
    "league_organizer": {"role": "league_organizer", "tenant_id": "tenant-alpha", "league_ids": ["league-alpha-1"],
                         "club_id": None, "player_id": None},
    "club_manager": {"role": "club_manager", "tenant_id": "tenant-alpha", "league_ids": [], "club_id": "club-alpha-1",
                     "player_id": None},
    "player": {"role": "player", "tenant_id": "tenant-alpha", "league_ids": [], "club_id": "club-alpha-1",
               "player_id": "player-alpha-1"},
    "viewer": {"role": "viewer", "tenant_id": "tenant-alpha", "league_ids": [], "club_id": None, "player_id": None},
}
ROLES = list(P)
A, D = True, False
OWN_LEAGUE = {"tenant_id": "tenant-alpha", "league_id": "league-alpha-1"}
OTHER_LEAGUE = {"tenant_id": "tenant-alpha", "league_id": "league-alpha-2"}
FOREIGN_LEAGUE = {"tenant_id": "tenant-beta", "league_id": "league-beta-1"}
OWN_CLUB = {"tenant_id": "tenant-alpha", "club_id": "club-alpha-1"}
OTHER_CLUB = {"tenant_id": "tenant-alpha", "club_id": "club-alpha-2"}
FOREIGN_CLUB = {"tenant_id": "tenant-beta", "club_id": "club-beta-1"}
OWN_PLAYER = {"tenant_id": "tenant-alpha", "club_id": "club-alpha-1", "player_id": "player-alpha-1"}
OTHER_PLAYER = {"tenant_id": "tenant-alpha", "club_id": "club-alpha-2", "player_id": "player-alpha-2"}
FOREIGN_PLAYER = {"tenant_id": "tenant-beta", "club_id": "club-beta-1", "player_id": "player-beta-1"}

MATRIX = [
    ("tenant.create", None, [A, D, D, D, D]),
    ("league.fixtures.write", OWN_LEAGUE, [A, A, D, D, D]),
    ("league.fixtures.write", OTHER_LEAGUE, [A, D, D, D, D]),
    ("league.fixtures.write", FOREIGN_LEAGUE, [A, D, D, D, D]),
    ("club.roster.write", OWN_CLUB, [A, D, A, D, D]),
    ("club.products.write", OWN_CLUB, [A, D, A, D, D]),
    ("club.roster.write", OTHER_CLUB, [A, D, D, D, D]),
    ("club.products.write", OTHER_CLUB, [A, D, D, D, D]),
    ("club.roster.write", FOREIGN_CLUB, [A, D, D, D, D]),
    ("club.products.write", FOREIGN_CLUB, [A, D, D, D, D]),
    ("player.update", OWN_PLAYER, [A, D, A, A, D]),
    ("player.update", OTHER_PLAYER, [A, D, D, D, D]),
    ("player.update", FOREIGN_PLAYER, [A, D, D, D, D]),
    ("club.read", OWN_CLUB, [A, A, A, A, A]),
    ("club.read", OTHER_CLUB, [A, A, A, A, A]),
    ("club.read", FOREIGN_CLUB, [A, D, D, D, D]),
    ("platform.config.read", None, [A, D, D, D, D]),
]


@pytest.mark.parametrize("action,resource,expected", MATRIX)
def test_spec_matrix(action, resource, expected):
    got = [policy.is_allowed(P[r], action, resource) for r in ROLES]
    assert got == expected


def test_unknown_action_and_role_denied():
    assert not policy.is_allowed(P["viewer"], "does.not.exist", {})
    assert not policy.is_allowed({"role": "hacker", "tenant_id": "tenant-alpha"}, "club.read", OWN_CLUB)
    assert not policy.is_allowed(P["club_manager"], "club.roster.write", {"tenant_id": "tenant-alpha"})
    assert not policy._rule_ok("mystery", P["viewer"], {})


def _user():
    return {"user_id": "u1", "role": "viewer", "tenant_id": "tenant-alpha", "league_ids": [], "club_id": None,
            "player_id": None}


def test_jwt_roundtrip_and_header_parsing():
    tok = jwt_tokens.issue(_user())
    claims = jwt_tokens.principal_from_header(f"Bearer {tok}")
    assert claims["role"] == "viewer" and claims["exp"] - claims["iat"] >= 3600


@pytest.mark.parametrize("header", [None, "", "Token abc", "Bearer ", "Bearer not.a.jwt"])
def test_missing_or_malformed_token(header):
    with pytest.raises(ApiError) as e:
        jwt_tokens.principal_from_header(header)
    assert e.value.status == 401 and e.value.code == "UNAUTHENTICATED"


def test_tampered_expired_and_alg_none_rejected():
    tok = jwt_tokens.issue(_user())
    head, body, sig = tok.split(".")
    for bad in (f"{head}.{body}.{sig[:-2]}xx",
                pyjwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) + 60}, "wrong-secret",
                             algorithm="HS256"),
                pyjwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) - 5}, config.JWT_SECRET,
                             algorithm="HS256"),
                pyjwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) + 60}, None,
                             algorithm="none")):
        with pytest.raises(ApiError) as e:
            jwt_tokens.verify(bad)
        assert e.value.status == 401
