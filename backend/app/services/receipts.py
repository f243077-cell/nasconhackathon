"""Server-side PDF receipt (spec 5.12). Text must contain the order_id and 'PKR 4500.00'."""
import io
import logging

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .. import config
from ..domain.store import format_pkr

log = logging.getLogger("receipts")


def render_pdf(payload: dict, tenant_name: str = "NaSCon Store") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Receipt {payload['order_id']}")
    y = 800
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"{tenant_name} - Receipt")
    c.setFont("Helvetica", 11)
    y -= 30
    for line in (
        f"Order ID: {payload['order_id']}",
        f"Customer: {payload['customer_id']}",
        f"Paid at: {payload['paid_at']}",
    ):
        c.drawString(50, y, line)
        y -= 18
    y -= 10
    for item in payload["items"]:
        c.drawString(50, y, f"{item['variant_id']}  x{item['quantity']}  {format_pkr(item['unit_price_minor'])}")
        y -= 18
    y -= 10
    c.drawString(50, y, f"Subtotal: {format_pkr(payload['subtotal_minor'])}")
    y -= 18
    c.drawString(50, y, f"Discount: {format_pkr(payload['discount_minor'])}")
    y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total: {format_pkr(payload['total_minor'])}")
    c.showPage()
    c.save()
    return buf.getvalue()


def store_pdf(order_id: str, pdf: bytes) -> None:
    """Upload to MinIO (object store). Best effort: the receipt is also kept in Postgres."""
    try:
        import urllib3
        from minio import Minio

        client = Minio(
            config.MINIO_ENDPOINT, access_key=config.MINIO_ACCESS_KEY, secret_key=config.MINIO_SECRET_KEY,
            secure=False, http_client=urllib3.PoolManager(timeout=2.0, retries=False),
        )
        if not client.bucket_exists(config.MINIO_BUCKET):
            client.make_bucket(config.MINIO_BUCKET)
        client.put_object(config.MINIO_BUCKET, f"{order_id}.pdf", io.BytesIO(pdf), len(pdf),
                          content_type="application/pdf")
    except Exception as exc:  # noqa: BLE001
        log.warning("receipt %s not stored in object store: %s", order_id, exc)
