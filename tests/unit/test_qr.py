from datetime import datetime, timedelta, timezone

import pytest

from app.domain import qr
from app.errors import ApiError


@pytest.mark.parametrize("entity_id,kind", [
    ("match-m1", "match"), ("club-alpha-1", "club"), ("player-beta-2", "player"), ("cs-session-101", "costream"),
    ("team-1", None), ("match-", None), ("", None), (None, None), (42, None), ("MATCH-m1", None),
])
def test_entity_type_from_prefix(entity_id, kind):
    assert qr.entity_type(entity_id) == kind


def test_unknown_entity_is_qr_not_found():
    with pytest.raises(ApiError) as e:
        qr.target_route("team-1")
    assert (e.value.status, e.value.code, e.value.details) == (404, "QR_NOT_FOUND", {"entity_id": "team-1"})


@pytest.mark.parametrize("status,route", [
    ("upcoming", "/web/matches/match-m1/preview"),
    ("in_progress", "/web/matches/match-m1/live"),
    ("completed", "/web/matches/match-m1/vod"),
    ("postponed", "/web/matches/match-m1/notice?state=postponed"),
    ("cancelled", "/web/matches/match-m1/notice?state=cancelled"),
    ("abandoned", "/web/matches/match-m1/notice?state=abandoned"),
    (None, "/web/matches/match-m1/preview"),
])
def test_match_routes_follow_live_status(status, route):
    assert qr.target_route("match-m1", status) == route


def test_other_entity_routes():
    assert qr.target_route("player-alpha-1") == "/web/players/player-alpha-1"
    assert qr.target_route("club-alpha-1", "active") == "/web/clubs/club-alpha-1"
    assert qr.target_route("cs-session-101") == "/web/costream/cs-session-101"


def test_deep_links():
    assert qr.deep_link_uri("match-m1") == "nascon://entity/match-m1"
    assert qr.deep_link_uri("cs-session-101") == "nascon://stream/cs-session-101"


def test_seeded_short_codes_and_stable_generated_ones():
    assert qr.short_code_for("match-m1", "any") == "m1-live"
    assert qr.short_code_for("player-alpha-1", "any") == "p-alpha-1"
    assert qr.short_code_for("club-alpha-1", "any") == "c-alpha-1"
    code = qr.short_code_for("match-m2", "salt-a")
    assert code == qr.short_code_for("match-m2", "salt-a")
    assert code.startswith("m-") and len(code) == 12
    assert code != qr.short_code_for("match-m2", "salt-b")
    assert qr.short_code_for("cs-session-9", "s").startswith("cs-")


def test_spec_example_view():
    view = qr.build_view("match-m1", "in_progress", "m1-live", 1)
    assert view == {
        "entity_id": "match-m1", "entity_type": "match", "entity_status": "in_progress",
        "short_url": "http://localhost:8080/q/m1-live", "target_route": "/web/matches/match-m1/live",
        "deep_link_uri": "nascon://entity/match-m1", "scan_count": 1,
        "export_formats": {"svg": "http://localhost:8080/audit/v1/qr/match-m1/export.svg",
                           "png": "http://localhost:8080/audit/v1/qr/match-m1/export.png",
                           "pdf": "http://localhost:8080/audit/v1/qr/match-m1/export.pdf"}}


def test_mutation_after_printing_keeps_short_url_and_changes_route_and_sig_payload():
    live = qr.build_view("match-m1", "in_progress", "m1-live", 3)
    done = qr.build_view("match-m1", "completed", "m1-live", 4)
    off = qr.build_view("match-m1", "postponed", "m1-live", 5)
    assert live["short_url"] == done["short_url"] == off["short_url"]
    assert done["target_route"].endswith("/vod") and off["target_route"].endswith("/notice?state=postponed")
    assert qr.sig_payload(live) != qr.sig_payload(done) != qr.sig_payload(off)
    assert qr.sig_payload(done) == {"entity_id": "match-m1", "short_url": "http://localhost:8080/q/m1-live",
                                    "target_route": "/web/matches/match-m1/vod"}


@pytest.mark.parametrize("ua,family", [
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) Mobile Safari/537.36", "mobile"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", "mobile"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129", "desktop"),
    ("k6/0.54.0", "desktop"), ("", "desktop"), (None, "desktop"),
])
def test_device_family(ua, family):
    assert qr.device_family(ua) == family


def test_hour_bucket_is_utc_hour():
    pkt = timezone(timedelta(hours=5))
    assert qr.hour_bucket(datetime(2026, 10, 18, 11, 42, 7, tzinfo=pkt)) == "2026-10-18T06:00Z"
    assert qr.hour_bucket(datetime(2026, 10, 18, 23, 59)) == "2026-10-18T23:00Z"
