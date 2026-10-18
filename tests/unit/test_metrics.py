import re

import pytest

from app.services import metrics

NAMES = ["nascon_active_ws_connections", "nascon_active_streams_total", "nascon_stream_bitrate_kbps",
         "nascon_dlq_depth", "nascon_qr_scans_total"]
SAMPLE = re.compile(r"^[a-z_]+ -?\d+(\.\d+)?$")


def test_content_type_is_prometheus_0_0_4():
    assert metrics.CONTENT_TYPE == "text/plain; version=0.0.4"


def test_all_five_metrics_with_help_type_and_sample():
    text = metrics.render({"nascon_active_ws_connections": 25, "nascon_active_streams_total": 2,
                           "nascon_stream_bitrate_kbps": 2500.5, "nascon_dlq_depth": 3, "nascon_qr_scans_total": 41})
    lines = text.splitlines()
    assert text.endswith("\n") and len(lines) == 15
    for name in NAMES:
        assert f"# HELP {name} " in text
    assert "# TYPE nascon_qr_scans_total counter" in lines
    assert "# TYPE nascon_dlq_depth gauge" in lines
    samples = [ln for ln in lines if not ln.startswith("#")]
    assert samples == ["nascon_active_ws_connections 25", "nascon_active_streams_total 2",
                       "nascon_stream_bitrate_kbps 2500.5", "nascon_dlq_depth 3", "nascon_qr_scans_total 41"]
    assert all(SAMPLE.match(s) for s in samples)


@pytest.mark.parametrize("value,printed", [
    (None, "0"), ("7", "0"), (True, "0"), (-4, "0"), (-0.5, "0"), (float("nan"), "0"), (float("inf"), "0"),
    (12.0, "12"), (0.25, "0.25"), (0, "0"),
])
def test_bad_values_never_break_the_exposition(value, printed):
    text = metrics.render({"nascon_dlq_depth": value})
    assert f"nascon_dlq_depth {printed}" in text.splitlines()


def test_missing_values_default_to_zero():
    samples = [ln for ln in metrics.render({}).splitlines() if not ln.startswith("#")]
    assert samples == [f"{n} 0" for n in NAMES]
