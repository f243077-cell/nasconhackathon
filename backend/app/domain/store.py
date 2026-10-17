"""Checkout validation and pricing (FR-2.3, spec 5.12). Pure functions."""
from ..errors import ApiError, validation_error
from ..validate import is_id, is_int, is_str

ORDER_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"packed", "refunded", "cancelled"},
    "packed": {"shipped", "refunded"},
    "shipped": {"delivered"},
    "delivered": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}


def validate_checkout(body) -> None:
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    if not is_id(body.get("order_id")):
        bad.append("order_id")
    if not is_str(body.get("customer_id"), 1, 256):
        bad.append("customer_id")
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        bad.append("items")
    else:
        seen = set()
        for it in items:
            if (not isinstance(it, dict) or not is_id(it.get("variant_id")) or not is_int(it.get("quantity"))
                    or not 1 <= it["quantity"] <= 10 or it["variant_id"] in seen):
                bad.append("items")
                break
            seen.add(it["variant_id"])
    dc = body.get("discount_code")
    if dc is not None and not isinstance(dc, str):
        bad.append("discount_code")
    pay = body.get("payment")
    if not isinstance(pay, dict) or not is_str(pay.get("token"), 1, 128):
        bad.append("payment")
    if bad:
        raise validation_error(bad, "Invalid checkout request")


def discount_minor(subtotal_minor: int, percent: int) -> int:
    return (subtotal_minor * percent) // 100


def price_lines(items: list[dict], prices: dict[str, int]) -> tuple[list[dict], int]:
    lines = [{"variant_id": it["variant_id"], "quantity": it["quantity"], "unit_price_minor": prices[it["variant_id"]]}
             for it in items]
    subtotal = sum(line["quantity"] * line["unit_price_minor"] for line in lines)
    return lines, subtotal


def resolve_discount(code, codes: dict[str, int]) -> int:
    """Return the discount percent; raise 400 for an unknown code."""
    if code is None:
        return 0
    if code not in codes:
        raise ApiError(400, "INVALID_DISCOUNT_CODE", "Unknown discount code", {"discount_code": code})
    return codes[code]


def format_pkr(minor: int) -> str:
    return f"PKR {minor // 100}.{minor % 100:02d}"


def can_transition(current: str, nxt: str) -> bool:
    return nxt in ORDER_TRANSITIONS.get(current, set())
