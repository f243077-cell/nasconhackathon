"""Guest boundary and atomic guest-cart merge (FR-4.3, FR-4.4, spec 5.7). Pure functions.

The route (Tanzeel) locks the guest token row FOR UPDATE, then calls, in order:
validate_request -> check_existence -> replay_decision -> merge_items (409 OUT_OF_STOCK) -> build_response.
"""
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..canonical import canonical
from ..errors import ApiError, validation_error
from ..validate import is_int, is_str

GUEST_PREFIX = "guest_"
ANON_PREFIX = "guest_anon_tok_"
MAX_ITEMS = 10
CURRENCY = "PKR"


def is_guest_token(token) -> bool:
    """A bearer that must never write (ADR-12)."""
    return isinstance(token, str) and token.startswith(ANON_PREFIX)


def guest_write_forbidden(token: str) -> ApiError:
    return ApiError(403, "GUEST_WRITE_FORBIDDEN", "Guests can't do that. Sign in to continue.", {"guest_token": token})


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def token_expires_at(created_at: str, ttl_s: int) -> str:
    """When a guest token issued at `created_at` stops being usable (FR-4.2 short-lived)."""
    return (_parse_ts(created_at) + timedelta(seconds=ttl_s)).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_token_usable(token: str, status: str, created_at: str, now: str, ttl_s: int) -> None:
    """A wiped (privacy-erased) or expired guest token can't stage a new merge -> 409 GUEST_TOKEN_EXPIRED.
    Identical replays are decided before this check, so a merged cart is still returned after expiry."""
    if status == "wiped" or _parse_ts(now) >= _parse_ts(created_at) + timedelta(seconds=ttl_s):
        raise ApiError(409, "GUEST_TOKEN_EXPIRED", "This guest session has expired. Start a new one.",
                       {"guest_token": token, "expired_at": token_expires_at(created_at, ttl_s)})


def validate_request(body) -> dict:
    """Step 1. Returns the request with test_write_block defaulted to true."""
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    tok = body.get("guest_token")
    if not is_str(tok, 1, 128) or not tok.startswith(GUEST_PREFIX):
        bad.append("guest_token")
    if not is_str(body.get("registered_user_id"), 1, 128):
        bad.append("registered_user_id")
    cart = body.get("guest_cart")
    if not isinstance(cart, list) or not 1 <= len(cart) <= MAX_ITEMS:
        bad.append("guest_cart")
    else:
        for it in cart:
            if (not isinstance(it, dict) or not is_str(it.get("variant_id"), 1, 128) or not is_int(it.get("quantity"))
                    or it["quantity"] < 1):
                bad.append("guest_cart")
                break
    block = body.get("test_write_block", True)
    if not isinstance(block, bool):
        bad.append("test_write_block")
    if bad:
        raise validation_error(bad, "Invalid cart merge request")
    return {"guest_token": tok, "registered_user_id": body["registered_user_id"],
            "guest_cart": [{"variant_id": i["variant_id"], "quantity": i["quantity"]} for i in cart],
            "test_write_block": block}


def check_existence(req: dict, user_exists: Callable[[str], bool], variant_exists: Callable[[str], bool]) -> None:
    """Step 2: the user first, then every variant in cart order."""
    if not user_exists(req["registered_user_id"]):
        raise ApiError(404, "PLAYER_NOT_FOUND", "User not found", {"registered_user_id": req["registered_user_id"]})
    for it in req["guest_cart"]:
        if not variant_exists(it["variant_id"]):
            raise ApiError(404, "VARIANT_NOT_FOUND", "Variant not found", {"variant_id": it["variant_id"]})


def request_key(req: dict) -> str:
    """Canonical identity of a merge request: an identical replay has the same key."""
    return canonical(req)


def replay_decision(req: dict, stored_key: str | None) -> str:
    """'new' when the token was never merged, 'replay' for an identical resend (200, no double add).
    Anything else on a merged token -> 409 GUEST_TOKEN_ALREADY_MERGED."""
    if stored_key is None:
        return "new"
    if stored_key == request_key(req):
        return "replay"
    raise ApiError(409, "GUEST_TOKEN_ALREADY_MERGED", "This guest cart was already merged",
                   {"guest_token": req["guest_token"]})


def merge_items(existing: list[dict], guest: list[dict], stock: dict[str, int], prices: dict[str, int]) -> list[dict]:
    """Step 3 + 5. Sum quantities per variant (existing order first, new variants after, guest duplicates summed).
    Any merged quantity above stock -> 409 OUT_OF_STOCK with details.variant_id; nothing is changed."""
    qty: dict[str, int] = {}
    for it in [*existing, *guest]:
        qty[it["variant_id"]] = qty.get(it["variant_id"], 0) + it["quantity"]
    for vid, q in qty.items():
        if q > stock.get(vid, 0):
            raise ApiError(409, "OUT_OF_STOCK", "Not enough stock for this item",
                           {"variant_id": vid, "requested": q, "available": stock.get(vid, 0)})
    return [{"variant_id": vid, "quantity": q, "unit_price_minor": prices[vid]} for vid, q in qty.items()]


def active_cart(user_id: str, items: list[dict]) -> dict:
    return {"user_id": user_id, "currency": CURRENCY, "total_items": sum(i["quantity"] for i in items),
            "subtotal_minor": sum(i["quantity"] * i["unit_price_minor"] for i in items), "items": items}


def build_response(req: dict, items: list[dict]) -> dict:
    """Response body without `signature`. write_rejection_code is 403 when the guard was exercised, else null."""
    verified = req["test_write_block"]
    return {
        "guest_token": req["guest_token"],
        "write_block_verified": verified,
        "write_rejection_code": 403 if verified else None,
        "cart_merged": True,
        "active_cart": active_cart(req["registered_user_id"], items),
    }


def verify_write_block(token: str, guard: Callable[[str], None]) -> int:
    """Step 4: run the real guard with the guest token and return the status it rejected with.
    The guard must raise GUEST_WRITE_FORBIDDEN; anything else means the boundary is broken."""
    try:
        guard(token)
    except ApiError as e:
        if e.status == 403 and e.code == "GUEST_WRITE_FORBIDDEN":
            return 403
        raise
    raise RuntimeError("guest write guard did not reject a guest token")


def sig_payload(resp: dict) -> dict:
    """Exact DAY2 signature payload for POST /audit/v1/guest/cart-merge (spec 5.3)."""
    return {"cart_merged": resp["cart_merged"], "guest_token": resp["guest_token"],
            "registered_user_id": resp["active_cart"]["user_id"], "total_items": resp["active_cart"]["total_items"],
            "write_rejection_code": resp["write_rejection_code"]}
