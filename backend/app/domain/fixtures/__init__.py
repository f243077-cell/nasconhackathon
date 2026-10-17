"""Entry point for POST /audit/v1/fixtures: pure computation, stores nothing."""
from __future__ import annotations

from app.errors import validation_error


def generate(body: dict) -> dict:
    from app.domain.fixtures import round_robin

    formats = {"round_robin": round_robin.generate}
    if not isinstance(body, dict):
        raise validation_error(["body"])
    fmt = body.get("format")
    if fmt not in formats:
        raise validation_error(["format"])
    return formats[fmt](body)
