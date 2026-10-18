"""Prometheus text exposition for GET /metrics (NFR-6, ADR-16). Pure formatting."""

CONTENT_TYPE = "text/plain; version=0.0.4"

# name -> (type, help). Order is the order printed.
METRICS = {
    "nascon_active_ws_connections": ("gauge", "Open WebSocket connections"),
    "nascon_active_streams_total": ("gauge", "Live streams currently publishing"),
    "nascon_stream_bitrate_kbps": ("gauge", "Aggregate inbound stream bitrate in kbps"),
    "nascon_dlq_depth": ("gauge", "Undelivered notifications in the dead-letter queue"),
    "nascon_qr_scans_total": ("counter", "Total dynamic QR scans"),
}


def _number(value) -> str:
    """Prometheus sample value: integers stay integers, floats keep their digits, bad input becomes 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "0"
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf are never exported
        return "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render(values: dict) -> str:
    """HELP, TYPE and one sample per metric; a missing value is exported as 0, negatives clamp to 0."""
    lines = []
    for name, (kind, help_) in METRICS.items():
        v = values.get(name, 0)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
            v = 0
        lines += [f"# HELP {name} {help_}", f"# TYPE {name} {kind}", f"{name} {_number(v)}"]
    return "\n".join(lines) + "\n"
