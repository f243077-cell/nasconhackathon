"""Entry point for POST /audit/v1/fixtures: pure computation, stores nothing."""
from __future__ import annotations

from app.errors import validation_error


def generate(body: dict) -> dict:
    from app.domain.fixtures import double_elim, round_robin, single_elim, swiss

    formats = {"round_robin": round_robin.generate, "swiss": swiss.generate,
               "single_elim": single_elim.generate, "double_elim": double_elim.generate}
    if not isinstance(body, dict):
        raise validation_error(["body"])
    fmt = body.get("format")
    if fmt not in formats:
        raise validation_error(["format"])
    return formats[fmt](body)
