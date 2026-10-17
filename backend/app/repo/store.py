"""Concurrency-safe checkout and inventory (FR-2.3, NFR-3, spec 5.12)."""
import base64
import json

from ..canonical import canonical, sign
from ..domain import store as store_domain
from ..errors import ApiError
from ..services import bus, payments, receipts
from ..validate import now_iso


def _order_conflict(conn, body) -> tuple[int, dict] | None:
    prev = conn.execute("SELECT request, response FROM orders WHERE order_id = %s", (body["order_id"],)).fetchone()
    if prev is None:
        return None
    if prev["request"] == canonical(body):
        return 200, json.loads(prev["response"])
    raise ApiError(409, "DUPLICATE_ORDER_ID", "order_id already used with a different body",
                   {"order_id": body["order_id"]})


def checkout(conn, body) -> tuple[int, dict]:
    store_domain.validate_checkout(body)
    # Serialize requests that share an order_id so an identical replay never reserves twice.
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("order:" + body["order_id"],))
    replay = _order_conflict(conn, body)
    if replay:
        return replay

    items = body["items"]
    ids = [it["variant_id"] for it in items]
    rows = conn.execute(
        "SELECT v.variant_id, v.price_minor, p.tenant_id FROM variants v JOIN products p ON p.product_id = v.product_id "
        "WHERE v.variant_id = ANY(%s)", (ids,),
    ).fetchall()
    found = {r["variant_id"]: r for r in rows}
    for vid in ids:
        if vid not in found:
            raise ApiError(404, "VARIANT_NOT_FOUND", "Variant not found", {"variant_id": vid})
    codes = {r["code"]: r["percent"] for r in conn.execute("SELECT code, percent FROM discount_codes").fetchall()}
    percent = store_domain.resolve_discount(body.get("discount_code"), codes)

    now = now_iso()
    prices = {}
    for vid in ids:
        sched = conn.execute(
            "SELECT price_minor FROM price_schedule WHERE variant_id = %s AND effective_at <= %s "
            "ORDER BY effective_at DESC LIMIT 1", (vid, now),
        ).fetchone()
        prices[vid] = sched["price_minor"] if sched else found[vid]["price_minor"]
    lines, subtotal = store_domain.price_lines(items, prices)
    discount = store_domain.discount_minor(subtotal, percent)
    total = subtotal - discount

    # Atomic reservation: conditional decrement per variant in a fixed order (no deadlocks, no oversell).
    for it in sorted(items, key=lambda i: i["variant_id"]):
        ok = conn.execute(
            "UPDATE inventory SET stock = stock - %s, reserved = reserved + %s "
            "WHERE variant_id = %s AND stock >= %s RETURNING stock",
            (it["quantity"], it["quantity"], it["variant_id"], it["quantity"]),
        ).fetchone()
        if not ok:
            raise ApiError(409, "OUT_OF_STOCK", f"Variant {it['variant_id']} has no stock left.",
                           {"variant_id": it["variant_id"]})

    token = body["payment"]["token"]
    try:
        auth_id = payments.authorize(token, total)
        cap_id = payments.capture(token, auth_id)
    except payments.PaymentError as exc:
        # Raising rolls back the transaction, which releases the reservation.
        bus.emit_domain_event("order.payment_failed", {"order_id": body["order_id"], "code": exc.code})
        raise ApiError(402, exc.code, exc.message, {"order_id": body["order_id"]}) from exc

    for it in items:
        conn.execute("UPDATE inventory SET reserved = reserved - %s WHERE variant_id = %s",
                     (it["quantity"], it["variant_id"]))

    payload = {
        "order_id": body["order_id"], "customer_id": body["customer_id"], "items": lines,
        "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": total, "currency": "PKR",
        "paid_at": now,
    }
    pdf = receipts.render_pdf(payload)
    response = {
        "order_id": body["order_id"], "status": "paid", "currency": "PKR", "items": lines,
        "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": total,
        "payment": {"authorization_id": auth_id, "capture_id": cap_id, "state": "captured"},
        "receipt": {"payload": payload, "signature": sign(body["order_id"], payload),
                    "pdf_base64": base64.b64encode(pdf).decode("ascii")},
    }
    conn.execute(
        "INSERT INTO orders (order_id, request, status, customer_id, total_minor, response, pdf, created_at) "
        "VALUES (%s, %s, 'paid', %s, %s, %s, %s, %s)",
        (body["order_id"], canonical(body), body["customer_id"], total, json.dumps(response), pdf, now),
    )
    conn.execute("INSERT INTO order_status_log (order_id, status, at) VALUES (%s, 'pending', %s), (%s, 'paid', %s)",
                 (body["order_id"], now, body["order_id"], now))
    bus.emit_domain_event("order.status_changed", {"order_id": body["order_id"], "from": "pending", "to": "paid",
                                                   "total_minor": total, "at": now})
    return 201, response


def after_commit_store_pdf(response: dict) -> None:
    pdf = base64.b64decode(response["receipt"]["pdf_base64"])
    receipts.store_pdf(response["order_id"], pdf)


def inventory(conn, variant_id: str) -> dict:
    row = conn.execute("SELECT variant_id, stock, reserved FROM inventory WHERE variant_id = %s",
                       (variant_id,)).fetchone()
    if not row:
        raise ApiError(404, "VARIANT_NOT_FOUND", "Variant not found", {"variant_id": variant_id})
    return {"variant_id": row["variant_id"], "stock": row["stock"], "reserved": row["reserved"]}


def receipt_pdf(conn, order_id: str) -> bytes:
    row = conn.execute("SELECT pdf FROM orders WHERE order_id = %s", (order_id,)).fetchone()
    if not row:
        raise ApiError(404, "ORDER_NOT_FOUND", "Order not found", {"order_id": order_id})
    return bytes(row["pdf"])
