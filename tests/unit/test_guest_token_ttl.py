"""FR-4.2 short-lived guest tokens: expiry time and the usability check used before a new cart merge."""
import pytest

from app.domain import guest_cart as gc
from app.errors import ApiError

TTL = 4 * 3600
ISSUED = "2026-10-18T10:00:00Z"


def test_expires_at_adds_ttl():
    assert gc.token_expires_at(ISSUED, TTL) == "2026-10-18T14:00:00Z"
    assert gc.token_expires_at("2026-10-18T23:30:00Z", 3600) == "2026-10-19T00:30:00Z"


def test_naive_timestamp_is_treated_as_utc():
    assert gc.token_expires_at("2026-10-18T10:00:00", 60) == "2026-10-18T10:01:00Z"


@pytest.mark.parametrize("now", ["2026-10-18T10:00:00Z", "2026-10-18T13:59:59Z"])
def test_active_token_within_ttl_is_usable(now):
    gc.check_token_usable("guest_anon_tok_7721", "active", ISSUED, now, TTL)


def test_merged_status_is_not_an_expiry():
    # a merged token is handled by replay_decision (200 replay / 409 ALREADY_MERGED), not by expiry
    gc.check_token_usable("guest_anon_tok_7721", "merged", ISSUED, "2026-10-18T11:00:00Z", TTL)


@pytest.mark.parametrize("now", ["2026-10-18T14:00:00Z", "2026-10-19T09:00:00Z"])
def test_expired_token_is_rejected(now):
    with pytest.raises(ApiError) as e:
        gc.check_token_usable("guest_anon_tok_7721", "active", ISSUED, now, TTL)
    assert (e.value.status, e.value.code) == (409, "GUEST_TOKEN_EXPIRED")
    assert e.value.details == {"guest_token": "guest_anon_tok_7721", "expired_at": "2026-10-18T14:00:00Z"}


def test_wiped_token_is_rejected_even_when_fresh():
    with pytest.raises(ApiError) as e:
        gc.check_token_usable("guest_anon_tok_1", "wiped", ISSUED, ISSUED, TTL)
    assert e.value.code == "GUEST_TOKEN_EXPIRED"
