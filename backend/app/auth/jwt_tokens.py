"""HS256 JWT issue/verify. alg:none, tampered and expired tokens are rejected (401)."""
import time

import jwt

from .. import config
from ..errors import ApiError

ALGORITHM = "HS256"


def issue(user: dict, ttl: int | None = None) -> str:
    now = int(time.time())
    claims = {
        "sub": user["user_id"],
        "role": user["role"],
        "tenant_id": user.get("tenant_id"),
        "league_ids": user.get("league_ids") or [],
        "club_id": user.get("club_id"),
        "player_id": user.get("player_id"),
        "iat": now,
        "exp": now + (ttl or config.JWT_TTL_SECONDS),
    }
    return jwt.encode(claims, config.JWT_SECRET, algorithm=ALGORITHM)


def verify(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != ALGORITHM:
            raise ApiError(401, "UNAUTHENTICATED", "Unsupported token algorithm")
        return jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITHM],
                          options={"require": ["exp", "sub", "role"]})
    except ApiError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "UNAUTHENTICATED", "Token expired") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "UNAUTHENTICATED", "Invalid token") from exc


def principal_from_header(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "Missing bearer token")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "Missing bearer token")
    return verify(token)
