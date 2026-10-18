"""QR exports (FR-4.1): SVG and PNG via segno, a print-ready PDF poster via reportlab."""
import io

import segno
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def svg(short_url: str) -> bytes:
    buf = io.BytesIO()
    segno.make(short_url, error="m").save(buf, kind="svg", scale=8, border=4, xmldecl=True)
    return buf.getvalue()


def png(short_url: str) -> bytes:
    buf = io.BytesIO()
    segno.make(short_url, error="m").save(buf, kind="png", scale=8, border=4)
    return buf.getvalue()


def pdf(entity_id: str, short_url: str, title: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setTitle(f"QR {entity_id}")
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 90, title)
    widget = QrCodeWidget(short_url)
    x0, y0, x1, y1 = widget.getBounds()
    size = 340
    d = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, (width - size) / 2, height - 160 - size)
    c.setFont("Helvetica", 13)
    c.drawCentredString(width / 2, height - 200 - size, f"Entity: {entity_id}")
    c.drawCentredString(width / 2, height - 220 - size, short_url)
    c.showPage()
    c.save()
    return buf.getvalue()
