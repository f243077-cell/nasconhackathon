import pytest

from app.domain import store
from app.errors import ApiError
from app.services import payments, receipts

BODY = {"order_id": "ord-1", "customer_id": "cust-<script>'\"", "items": [{"variant_id": "v1", "quantity": 2}],
        "discount_code": None, "payment": {"token": "tok_success"}}


def test_valid_checkout_passes():
    store.validate_checkout(BODY)


@pytest.mark.parametrize("patch,field", [
    ({"order_id": "a|b"}, "order_id"),
    ({"customer_id": ""}, "customer_id"),
    ({"items": []}, "items"),
    ({"items": [{"variant_id": "v", "quantity": i} for i in range(1, 12)]}, "items"),
    ({"items": [{"variant_id": "v1", "quantity": 0}]}, "items"),
    ({"items": [{"variant_id": "v1", "quantity": 11}]}, "items"),
    ({"items": [{"variant_id": "v1", "quantity": True}]}, "items"),
    ({"items": [{"variant_id": "v1", "quantity": 1}, {"variant_id": "v1", "quantity": 1}]}, "items"),
    ({"discount_code": 10}, "discount_code"),
    ({"payment": {}}, "payment"),
])
def test_invalid_checkout(patch, field):
    with pytest.raises(ApiError) as e:
        store.validate_checkout(dict(BODY, **patch))
    assert e.value.status == 400 and field in e.value.details["fields"]


def test_not_an_object():
    with pytest.raises(ApiError):
        store.validate_checkout(None)


def test_pricing_discount_and_format():
    lines, subtotal = store.price_lines([{"variant_id": "v1", "quantity": 3}], {"v1": 450000})
    assert subtotal == 1350000 and lines[0]["unit_price_minor"] == 450000
    assert store.discount_minor(450001, 10) == 45000
    assert store.resolve_discount(None, {}) == 0
    assert store.resolve_discount("WELCOME10", {"WELCOME10": 10}) == 10
    with pytest.raises(ApiError) as e:
        store.resolve_discount("NOPE", {"WELCOME10": 10})
    assert e.value.code == "INVALID_DISCOUNT_CODE"
    assert store.format_pkr(450000) == "PKR 4500.00" and store.format_pkr(405) == "PKR 4.05"


def test_order_state_machine():
    assert store.can_transition("pending", "paid")
    assert store.can_transition("shipped", "delivered")
    assert not store.can_transition("delivered", "paid")
    assert not store.can_transition("refunded", "paid")


def test_mock_gateway():
    auth = payments.authorize(payments.SUCCESS, 100)
    assert auth.startswith("auth_") and payments.capture(payments.SUCCESS, auth).startswith("cap_")
    with pytest.raises(payments.PaymentError) as e:
        payments.authorize(payments.DECLINED, 100)
    assert e.value.code == "PAYMENT_DECLINED"
    auth = payments.authorize(payments.CAPTURE_FAIL, 100)
    with pytest.raises(payments.PaymentError) as e:
        payments.capture(payments.CAPTURE_FAIL, auth)
    assert e.value.code == "PAYMENT_CAPTURE_FAILED"
    assert payments.refund("cap_x", 100).startswith("ref_")


def test_pdf_contains_order_and_total():
    from pypdf import PdfReader
    import io

    payload = {"order_id": "ord-001", "customer_id": "c", "items": [{"variant_id": "v", "quantity": 1,
               "unit_price_minor": 450000}], "subtotal_minor": 450000, "discount_minor": 0,
               "total_minor": 450000, "currency": "PKR", "paid_at": "2026-10-17T11:20:05Z"}
    pdf = receipts.render_pdf(payload)
    assert pdf.startswith(b"%PDF")
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "ord-001" in text and "PKR 4500.00" in text


def test_store_pdf_is_best_effort_when_object_store_unreachable(monkeypatch):
    from app import config as cfg
    monkeypatch.setattr(cfg, "MINIO_ENDPOINT", "127.0.0.1:1")
    receipts.store_pdf("ord-x", b"%PDF-1.4")  # must not raise
