"""Mandatory autograder interface /audit/v1/* (spec 5). No auth except RBAC probes (see rbac.py)."""
from fastapi import APIRouter, Depends

from ..db import tx
from ..errors import ApiError
from ..repo import events as events_repo
from ..repo import leagues as leagues_repo
from ..repo import roster as roster_repo
from ..repo import seed as seed_repo
from ..repo import store as store_repo
from ..repo import sync as sync_repo
from ..services import bus, media
from .common import json_body, respond, run_tx

router = APIRouter()

try:  # Gunee's pure modules; answer 501 until they land.
    from ..domain import fixtures as fixtures_domain
except ImportError:  # pragma: no cover
    fixtures_domain = None
try:
    from ..domain import standings as standings_domain
except ImportError:  # pragma: no cover
    standings_domain = None


@router.get("/health")
def health():
    try:
        with tx() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'seeded'").fetchone()
        bus.client().ping()
    except Exception:  # noqa: BLE001
        row = None
    # Part II: the media server must be up too (spec II 5.1).
    if not row or not media.reachable():
        return respond(503, {"error": {"code": "NOT_READY", "message": "Not ready", "details": {}}})
    return {"status": "ok"}


@router.post("/audit/v1/reset")
def reset(body=Depends(json_body)):
    return respond(200, run_tx(seed_repo.reset, body))


@router.post("/audit/v1/sports")
def create_sport(body=Depends(json_body)):
    return respond(201, run_tx(leagues_repo.create_sport, body))


@router.post("/audit/v1/fixtures")
def fixtures(body=Depends(json_body)):
    if fixtures_domain is None or not hasattr(fixtures_domain, "generate"):
        raise ApiError(501, "NOT_IMPLEMENTED", "Fixture generation not available yet")
    return respond(200, fixtures_domain.generate(body))


@router.post("/audit/v1/leagues")
def leagues(body=Depends(json_body)):
    return respond(201, run_tx(leagues_repo.register_league, body))


@router.post("/audit/v1/events")
def events(body=Depends(json_body)):
    status, resp = run_tx(events_repo.append_event, body)
    return respond(status, resp)


@router.get("/audit/v1/score/{match_id}")
def score(match_id: str):
    return respond(200, run_tx(events_repo.score, match_id))


def compute_standings(conn, league_id: str) -> dict:
    if standings_domain is None or not hasattr(standings_domain, "compute"):
        raise ApiError(501, "NOT_IMPLEMENTED", "Standings engine not available yet")
    league = leagues_repo.get_league(conn, league_id)
    if league is None:
        raise ApiError(404, "LEAGUE_NOT_FOUND", "League not found", {"league_id": league_id})
    sport = events_repo.get_sport(conn, league["sport_id"])
    matches = [events_repo.score(conn, f["match_id"]) for f in league["config"]["fixtures"]]
    return standings_domain.compute(league["config"], sport, matches)


@router.get("/audit/v1/standings/{league_id}")
def standings(league_id: str):
    return respond(200, run_tx(compute_standings, league_id))


@router.post("/audit/v1/roster/setup")
def roster_setup(body=Depends(json_body)):
    return respond(201, run_tx(roster_repo.setup, body))


@router.post("/audit/v1/roster/transfer")
def roster_transfer(body=Depends(json_body)):
    status, resp = run_tx(roster_repo.transfer, body)
    return respond(status, resp)


@router.get("/audit/v1/roster/history/{player_id}")
def roster_history(player_id: str, as_of: str | None = None):
    return respond(200, run_tx(roster_repo.history, player_id, as_of))


@router.post("/audit/v1/checkout")
def checkout(body=Depends(json_body)):
    status, resp = run_tx(store_repo.checkout, body)
    if status == 201:
        store_repo.after_commit_store_pdf(resp)
    return respond(status, resp)


@router.get("/audit/v1/inventory/{variant_id}")
def inventory(variant_id: str):
    return respond(200, run_tx(store_repo.inventory, variant_id))


@router.post("/audit/v1/offline-sync")
def offline_sync(body=Depends(json_body)):
    return respond(200, run_tx(sync_repo.offline_sync, body))
