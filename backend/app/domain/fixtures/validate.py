"""Shared input checks for /audit/v1/fixtures. Pure: raises ApiError, touches no DB."""
from __future__ import annotations

import re

from app.errors import validation_error

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

TEAM_LIMITS = {
    "round_robin": (2, 40),
    "swiss": (2, 64),
    "single_elim": (2, 128),
    "double_elim": (3, 128),
}


def is_int(x) -> bool:
    return type(x) is int


def is_id(x) -> bool:
    return isinstance(x, str) and ID_RE.match(x) is not None


def teams(body: dict, fmt: str) -> list[str]:
    t = body.get("teams")
    lo, hi = TEAM_LIMITS[fmt]
    if not isinstance(t, list) or not all(is_id(x) for x in t) or len(set(t)) != len(t) or not lo <= len(t) <= hi:
        raise validation_error(["teams"])
    return list(t)


def params(body: dict) -> dict:
    p = body.get("params", {})
    if p is None:
        return {}
    if not isinstance(p, dict):
        raise validation_error(["params"])
    return p


def opt_bool(p: dict, key: str, default: bool = False) -> bool:
    v = p.get(key, default)
    if v is None:
        return default
    if type(v) is not bool:
        raise validation_error([key])
    return v
