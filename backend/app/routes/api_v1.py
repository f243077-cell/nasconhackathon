"""Production API for the mobile app (/api/v1/*, JWT, rate-limited). Reuses the audit code paths."""
import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response

from ..auth import jwt_tokens, policy
from ..db import tx
from ..errors import ApiError, validation_error
from ..repo import events as events_repo
from ..repo import leagues as leagues_repo
from ..repo import roster as roster_repo
from ..repo import store as store_repo
from ..repo import sync as sync_repo
from ..repo.seed import verify_password
from ..services import bus
from ..domain import competition as competition_domain
from ..domain import fixtures as fixtures_domain
from ..domain import roster as roster_domain
from ..validate import is_id, is_str, is_ts, today_iso
from .audit import compute_standings
from .common import json_body, respond, run_tx
from .rbac import load_user

router = APIRouter(prefix="/api/v1")


def principal(authorization: str | None = Header(default=None)) -> dict:
    return jwt_tokens.principal_from_header(authorization)


def principal_or_guest(authorization: str | None = Header(default=None)) -> dict:
    """Read routes the Guest Web Player uses: an anonymous guest bearer (or no bearer) reads public data."""
    if not authorization or authorization[7:].strip().startswith("guest_"):
        return {"role": "guest", "sub": (authorization or "")[7:].strip() or None, "tenant_id": None}
    return jwt_tokens.principal_from_header(authorization)


def require(p: dict, action: str, resource: dict | None = None) -> None:
    if not policy.is_allowed(p, action, resource):
        raise ApiError(403, "FORBIDDEN", "You don't have permission to do that", {"action": action})


def _tenant_view(conn, tenant_id):
    if tenant_id is None:
        return {"tenant_id": None, "name": "NaSCon Platform", "logo_url": None,
                "primary_color": "#1F2937", "secondary_color": "#F59E0B"}
    return conn.execute("SELECT tenant_id, name, logo_url, primary_color, secondary_color FROM tenants "
                        "WHERE tenant_id = %s", (tenant_id,)).fetchone()


@router.get("/ping")
def ping():
    return {"pong": True}


@router.post("/auth/login")
def login(body=Depends(json_body)):
    if not isinstance(body, dict) or not is_str(body.get("email"), 3, 254) or not is_str(body.get("password"), 1, 256):
        raise validation_error(["email", "password"], "Email and password are required")
    with tx() as conn:
        user = load_user(conn, body["email"].strip().lower())
        if user is None or not verify_password(body["password"], user["password_hash"]):
            raise ApiError(401, "UNAUTHENTICATED", "Wrong email or password")
        tenant = _tenant_view(conn, user["tenant_id"])
    return {
        "token": jwt_tokens.issue(user),
        "role": user["role"],
        "user": {"id": user["user_id"], "email": user["email"], "display_name": user["display_name"],
                 "club_id": user["club_id"], "league_ids": user["league_ids"], "player_id": user["player_id"]},
        "tenant": tenant,
    }


@router.get("/me")
def me(p: dict = Depends(principal)):
    return {"user_id": p["sub"], "role": p["role"], "tenant_id": p.get("tenant_id"),
            "league_ids": p.get("league_ids"), "club_id": p.get("club_id"), "player_id": p.get("player_id")}


@router.get("/leagues")
def leagues(p: dict = Depends(principal)):
    with tx() as conn:
        if p["role"] == "super_admin":
            rows = conn.execute("SELECT league_id, name, sport_id, season, tenant_id FROM leagues "
                                "WHERE tenant_id IS NOT NULL ORDER BY seq").fetchall()
        else:
            rows = conn.execute("SELECT league_id, name, sport_id, season, tenant_id FROM leagues "
                                "WHERE tenant_id = %s ORDER BY seq", (p.get("tenant_id"),)).fetchall()
    return rows


def _scoped_league(conn, p, league_id):
    lg = leagues_repo.get_league(conn, league_id)
    if lg is None or lg["tenant_id"] is None:
        raise ApiError(404, "LEAGUE_NOT_FOUND", "League not found", {"league_id": league_id})
    require(p, "league.read", {"tenant_id": lg["tenant_id"], "league_id": league_id})
    return lg


def _team_names(conn, ids):
    rows = conn.execute("SELECT club_id, name FROM clubs WHERE club_id = ANY(%s)", (list(ids),)).fetchall()
    names = {r["club_id"]: r["name"] for r in rows}
    return {i: names.get(i, i) for i in ids}


@router.get("/leagues/{league_id}/fixtures")
def league_fixtures(league_id: str, p: dict = Depends(principal)):
    with tx() as conn:
        _scoped_league(conn, p, league_id)
        rows = conn.execute("SELECT match_id, home, away, scheduled_at, venue FROM matches WHERE league_id = %s "
                            "ORDER BY scheduled_at NULLS LAST, seq", (league_id,)).fetchall()
        names = _team_names(conn, {r["home"] for r in rows} | {r["away"] for r in rows})
        out = []
        for r in rows:
            proj = events_repo.score(conn, r["match_id"])
            out.append({"match_id": r["match_id"], "home": r["home"], "away": r["away"],
                        "home_name": names[r["home"]], "away_name": names[r["away"]],
                        "status": proj["status"], "scheduled_at": r["scheduled_at"], "venue": r["venue"],
                        "home_score": proj["home"]["score"], "away_score": proj["away"]["score"]})
    return out


@router.get("/sports/{sport_id}/event-types")
def sport_event_types(sport_id: str, p: dict = Depends(principal)):
    """Scoring buttons for the organizer screen, straight from the sport config (works for mystery sports)."""
    with tx() as conn:
        sport = events_repo.get_sport(conn, sport_id)
    if sport is None:
        raise ApiError(404, "SPORT_NOT_FOUND", "Sport not found", {"sport_id": sport_id})
    types = [dict({"key": key, "label": key.replace("_", " ").title()}, **cfg)
             for key, cfg in sport["scoring_events"].items()]
    return {"sport_id": sport["sport_id"], "name": sport["name"], "scoring_model": sport["scoring_model"],
            "event_types": types}


@router.get("/leagues/{league_id}/squads")
def league_squads(league_id: str, p: dict = Depends(principal)):
    """Transfer picker: squads of a league with their current players (derived from the roster audit log)."""
    with tx() as conn:
        _scoped_league(conn, p, league_id)
        state = roster_repo.load_state(conn, league_id)
    if state is None:
        return {"league_id": league_id, "transfer_window": None, "squads": []}
    today = date.fromisoformat(today_iso())
    members: dict[str, list] = {sid: [] for sid in state["squads"]}
    for pl in state["players"].values():
        squad_id, parent = roster_domain.placement(state, pl["player_id"], today)
        if squad_id in members:
            members[squad_id].append({"player_id": pl["player_id"], "name": pl["name"], "position": pl["position"],
                                      "role": pl["role"], "on_loan_from": parent})
    return {
        "league_id": league_id,
        "transfer_window": state["league"]["transfer_window"],
        "max_squad_size": state["league"]["max_squad_size"],
        "squads": [{"squad_id": s["squad_id"], "club_id": s["club_id"], "name": s["name"],
                    "player_count": len(members[s["squad_id"]]), "players": members[s["squad_id"]]}
                   for s in state["squads"].values()],
    }


@router.get("/standings/{league_id}")
def standings(league_id: str, p: dict = Depends(principal)):
    with tx() as conn:
        _scoped_league(conn, p, league_id)
        return compute_standings(conn, league_id)


def _product_view(conn, product_id):
    prod = conn.execute("SELECT product_id, tenant_id, club_id, name, type, image_url FROM products "
                        "WHERE product_id = %s", (product_id,)).fetchone()
    if not prod:
        return None
    prod["variants"] = conn.execute(
        "SELECT v.variant_id, v.size, v.color, v.price_minor, i.stock FROM variants v "
        "JOIN inventory i ON i.variant_id = v.variant_id WHERE v.product_id = %s ORDER BY v.variant_id",
        (product_id,)).fetchall()
    return prod


@router.get("/matches/{match_id}")
def match_detail(match_id: str, p: dict = Depends(principal_or_guest)):
    with tx() as conn:
        match = events_repo.get_match(conn, match_id)
        if match is None:
            raise ApiError(404, "MATCH_NOT_FOUND", "Match not found", {"match_id": match_id})
        if match["league_id"] and p["role"] != "guest":
            _scoped_league(conn, p, match["league_id"])
        proj = events_repo.score(conn, match_id)
        names = _team_names(conn, {match["home"], match["away"]})
        proj["home"]["name"] = names[match["home"]]
        proj["away"]["name"] = names[match["away"]]
        proj["scheduled_at"] = match["scheduled_at"]
        proj["venue"] = match["venue"]
        proj["pinned_product"] = _product_view(conn, match["pinned_product_id"]) if match["pinned_product_id"] else None
    return proj


@router.get("/clubs/{club_id}")
def club(club_id: str, p: dict = Depends(principal)):
    with tx() as conn:
        row = conn.execute("SELECT club_id, tenant_id, name, profile FROM clubs WHERE club_id = %s",
                           (club_id,)).fetchone()
        if not row:
            raise ApiError(404, "CLUB_NOT_FOUND", "Club not found", {"club_id": club_id})
        require(p, "club.read", {"tenant_id": row["tenant_id"], "club_id": club_id})
        profile = json.loads(row["profile"])
        roster = []
        today = date.fromisoformat(today_iso())
        for lg_row in conn.execute("SELECT state FROM roster_state").fetchall():
            state = json.loads(lg_row["state"])
            for pl in state["players"].values():
                # Current squad is derived from the audit log (players[pid].squad_id is the initial squad).
                squad_id, parent = roster_domain.placement(state, pl["player_id"], today)
                if state["squads"].get(squad_id or "", {}).get("club_id") == club_id:
                    roster.append({"player_id": pl["player_id"], "name": pl["name"], "position": pl["position"],
                                   "role": pl["role"], "squad_id": squad_id, "parent_squad_id": parent,
                                   "league_id": state["league"]["league_id"]})
        if not roster:
            roster = conn.execute("SELECT player_id, name, position, role, club_id AS squad_id FROM players "
                                  "WHERE club_id = %s ORDER BY player_id", (club_id,)).fetchall()
    return {"club_id": row["club_id"], "name": row["name"], "tenant_id": row["tenant_id"],
            "venue": profile.get("venue"), "socials": profile.get("socials", {}), "staff": profile.get("staff", []),
            "stats": profile.get("stats", []), "roster": roster}


@router.get("/products")
def products(club_id: str | None = None, p: dict = Depends(principal)):
    with tx() as conn:
        sql = "SELECT product_id FROM products WHERE tenant_id = %s"
        args: list = [p.get("tenant_id")]
        if p["role"] == "super_admin":
            sql, args = "SELECT product_id FROM products WHERE TRUE", []
        if club_id:
            sql += " AND club_id = %s"
            args.append(club_id)
        ids = [r["product_id"] for r in conn.execute(sql + " ORDER BY seq", args).fetchall()]
        return [_product_view(conn, i) for i in ids]


@router.post("/checkout")
def checkout(body=Depends(json_body), p: dict = Depends(principal)):
    require(p, "store.checkout", {"tenant_id": p.get("tenant_id")})
    status, resp = run_tx(store_repo.checkout, body)
    if status == 201:
        store_repo.after_commit_store_pdf(resp)
    return respond(status, resp)


@router.get("/orders/{order_id}/receipt")
def receipt(order_id: str, p: dict = Depends(principal)):
    with tx() as conn:
        pdf = store_repo.receipt_pdf(conn, order_id)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="receipt-{order_id}.pdf"'})


def _authorize_event(conn, p, body):
    if isinstance(body, dict) and is_id(body.get("match_id")):
        match = events_repo.get_match(conn, body["match_id"])
        if match and match["league_id"]:
            lg = leagues_repo.get_league(conn, match["league_id"])
            require(p, "league.events.write", {"tenant_id": lg["tenant_id"], "league_id": lg["league_id"]})
            return
    require(p, "league.events.write", {"league_id": None})


@router.post("/events")
def post_event(body=Depends(json_body), p: dict = Depends(principal)):
    with tx() as conn:
        _authorize_event(conn, p, body)
    status, resp = run_tx(events_repo.append_event, body)
    return respond(status, resp)


def _authorize_transfer(conn, p, body):
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    state = roster_repo.load_state(conn, body.get("league_id")) if is_id(body.get("league_id")) else None
    squad = (state or {}).get("squads", {}).get(body.get("from_squad_id") or "")
    if squad is None:
        require(p, "club.roster.write", {"club_id": None})
        return
    require(p, "club.roster.write", {"tenant_id": squad["tenant_id"], "club_id": squad["club_id"]})


@router.post("/roster/transfer")
def roster_transfer(body=Depends(json_body), p: dict = Depends(principal)):
    with tx() as conn:
        _authorize_transfer(conn, p, body)
    status, resp = run_tx(roster_repo.transfer, body)
    return respond(status, resp)


@router.get("/roster/history/{player_id}")
def roster_history(player_id: str, as_of: str | None = None, p: dict = Depends(principal)):
    return respond(200, run_tx(roster_repo.history, player_id, as_of))


@router.post("/sync")
def sync(body=Depends(json_body), p: dict = Depends(principal)):
    with tx() as conn:
        if isinstance(body, dict) and isinstance(body.get("actions"), list):
            for a in body["actions"]:
                if isinstance(a, dict) and isinstance(a.get("payload"), dict):
                    if a.get("type") == "score_event":
                        _authorize_event(conn, p, a["payload"])
                    elif a.get("type") == "roster_transfer":
                        _authorize_transfer(conn, p, a["payload"])
    return respond(200, run_tx(sync_repo.offline_sync, body))


@router.post("/matches/{match_id}/pin")
def pin_product(match_id: str, body=Depends(json_body), p: dict = Depends(principal)):
    if not isinstance(body, dict) or not is_id(body.get("product_id")):
        raise validation_error(["product_id"], "product_id is required")
    with tx() as conn:
        match = events_repo.get_match(conn, match_id)
        if match is None:
            raise ApiError(404, "MATCH_NOT_FOUND", "Match not found", {"match_id": match_id})
        lg = leagues_repo.get_league(conn, match["league_id"]) if match["league_id"] else None
        require(p, "match.pin", {"tenant_id": lg["tenant_id"] if lg else None,
                                 "league_id": match["league_id"]})
        product = _product_view(conn, body["product_id"])
        if product is None:
            raise ApiError(404, "PRODUCT_NOT_FOUND", "Product not found", {"product_id": body["product_id"]})
        conn.execute("UPDATE matches SET pinned_product_id = %s WHERE match_id = %s", (body["product_id"], match_id))
    bus.publish_realtime("product_pinned", match_id, {"product": product})
    return {"match_id": match_id, "pinned_product": product}


@router.post("/matches/{match_id}/status")
def match_status(match_id: str, body=Depends(json_body), p: dict = Depends(principal)):
    """FR-1.3: organizer postpones / abandons / cancels / reschedules a match (state machine, signed event)."""
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    with tx() as conn:
        match = events_repo.get_match(conn, match_id)
        if match is None:
            raise ApiError(404, "MATCH_NOT_FOUND", "Match not found", {"match_id": match_id})
        lg = leagues_repo.get_league(conn, match["league_id"]) if match["league_id"] else None
        require(p, "match.status.write", {"tenant_id": lg["tenant_id"] if lg else None,
                                          "league_id": match["league_id"]})
    if "scheduled_at" in body and body["scheduled_at"] is not None and not is_ts(body["scheduled_at"]):
        raise validation_error(["scheduled_at"], "scheduled_at must be YYYY-MM-DDTHH:MM:SSZ")
    payload = {"to": body.get("to")}
    if "reason" in body:
        payload["reason"] = body["reason"]
    event = {"event_id": body.get("event_id") or f"{match_id}-st-{uuid.uuid4().hex[:10]}", "match_id": match_id,
             "type": "status_change", "payload": payload}

    def apply(conn):
        status, resp = events_repo.append_event(conn, event, allow_internal=True)
        if body.get("to") == "upcoming" and (body.get("scheduled_at") or body.get("venue")):
            conn.execute("UPDATE matches SET scheduled_at = COALESCE(%s, scheduled_at), venue = COALESCE(%s, venue) "
                         "WHERE match_id = %s", (body.get("scheduled_at"), body.get("venue"), match_id))
        return status, resp

    status, resp = run_tx(apply)
    resp["status"] = body["to"]
    return respond(status, resp)


@router.get("/orders/{order_id}")
def order_detail(order_id: str, p: dict = Depends(principal)):
    with tx() as conn:
        order = store_repo.get_order(conn, order_id)
        if order["tenant_id"]:
            require(p, "store.checkout", {"tenant_id": order["tenant_id"]})
        return store_repo.order_view(conn, order_id)


@router.post("/orders/{order_id}/status")
def order_status(order_id: str, body=Depends(json_body), p: dict = Depends(principal)):
    """FR-2.3: club manager moves an order Paid -> Packed -> Shipped -> Delivered, or Cancelled / Refunded."""
    with tx() as conn:
        order = store_repo.get_order(conn, order_id)
        require(p, "order.manage", {"tenant_id": order["tenant_id"], "club_id": order["club_id"]})
    return respond(200, run_tx(store_repo.transition_order, order_id, body))


@router.get("/competitions/{competition_id}/promotion")
def competition_promotion(competition_id: str, p: dict = Depends(principal)):
    """FR-1.2: multi-division promotion/relegation computed from the live standings of each division."""
    with tx() as conn:
        tenant = None if p["role"] == "super_admin" else p.get("tenant_id")
        leagues = leagues_repo.competition_leagues(conn, competition_id, tenant)
        if not leagues:
            raise ApiError(404, "COMPETITION_NOT_FOUND", "Competition not found", {"competition_id": competition_id})
        divisions = [{"division": lg["competition"]["division"], "league_id": lg["league_id"],
                      "table": compute_standings(conn, lg["league_id"])["table"]} for lg in leagues]
    rules = leagues[0]["competition"]
    promote, relegate = rules.get("promote", 1), rules.get("relegate", 1)
    return {"competition_id": competition_id, "promote": promote, "relegate": relegate,
            "divisions": competition_domain.promotion_relegation(divisions, promote, relegate)}


@router.post("/leagues/{league_id}/knockout")
def league_knockout(league_id: str, body=Depends(json_body), p: dict = Depends(principal)):
    """FR-1.2 hybrid format: group-stage table -> seeded single-elimination bracket (pure computation)."""
    body = body if isinstance(body, dict) else {}
    with tx() as conn:
        lg = _scoped_league(conn, p, league_id)
        require(p, "league.fixtures.write", {"tenant_id": lg["tenant_id"], "league_id": league_id})
        table = compute_standings(conn, league_id)["table"]
    seeds = competition_domain.knockout_seeds(table, body.get("qualifiers", 4 if len(table) >= 4 else 2))
    bracket = fixtures_domain.generate({"format": "single_elim", "teams": seeds,
                                        "params": {"third_place_match": bool(body.get("third_place_match", False))}})
    return {"league_id": league_id, "seeds": seeds, "bracket": bracket}


@router.post("/chat")
def post_chat(body=Depends(json_body), p: dict = Depends(principal)):
    """Member chat post (FR-3.3, FR-5.3); anonymous guest tokens are refused earlier with GUEST_WRITE_FORBIDDEN."""
    from ..repo import day2 as day2_repo
    return respond(201, run_tx(day2_repo.post_chat, p, body))



@router.post("/guest/token")
def guest_token():
    """Issue an anonymous read-only viewer token for the Guest Web Player (FR-4.2)."""
    from ..repo import day2 as day2_repo
    return respond(201, run_tx(day2_repo.issue_guest_token))


@router.get("/chat")
def chat_history(room_id: str, p: dict = Depends(principal_or_guest)):
    from ..repo import day2 as day2_repo
    with tx() as conn:
        return day2_repo.chat_history(conn, room_id)


@router.post("/cart")
def merge_guest_cart(body=Depends(json_body), p: dict = Depends(principal)):
    """FR-4.4: after login, merge the staged guest cart into the member's persistent cart (same rules as the audit
    route: summed per variant, capped by stock, the guest token can't be merged twice)."""
    from ..repo import social as social_repo
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    req = {"guest_token": body.get("guest_token"), "registered_user_id": p.get("player_id") or p["sub"],
           "guest_cart": body.get("items"), "test_write_block": False}
    status, resp = run_tx(social_repo.cart_merge, req)
    return respond(status, resp)
