import copy

import pytest

from app.domain.roster import check_and_apply, history
from app.errors import ApiError

NOW = "2026-09-30T08:12:44Z"


def base_state():
    return {
        "league": {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "sport_id": "football",
                   "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"}, "max_squad_size": 3,
                   "required_positions": {"gk": 1}},
        "squads": {"sq-a": {"squad_id": "sq-a", "club_id": "c1", "tenant_id": "tenant-alpha", "name": "A"},
                   "sq-b": {"squad_id": "sq-b", "club_id": "c2", "tenant_id": "tenant-alpha", "name": "B"},
                   "sq-x": {"squad_id": "sq-x", "club_id": "c9", "tenant_id": "tenant-beta", "name": "X"}},
        "players": {"p1": {"player_id": "p1", "name": "Keeper", "position": "gk", "squad_id": "sq-a", "role": "captain"},
                    "p2": {"player_id": "p2", "name": "Mid", "position": "mf", "squad_id": "sq-a", "role": "starter"},
                    "p3": {"player_id": "p3", "name": "Fwd", "position": "fw", "squad_id": "sq-b", "role": "starter"},
                    "p4": {"player_id": "p4", "name": "Fwd2", "position": "fw", "squad_id": "sq-b", "role": "starter"}},
        "matches_in_progress": [],
        "audit": [],
        "audit_seq": 0,
    }


def req(**kw):
    r = {"request_id": "tr-001", "league_id": "lg-r1", "player_id": "p2", "type": "transfer",
         "from_squad_id": "sq-a", "to_squad_id": "sq-b", "effective_date": "2026-09-30",
         "reason": "Tactical move", "requested_by": "user-77"}
    r.update(kw)
    return r


def apply(state, r):
    body, mut = check_and_apply(state, r, NOW)
    state["audit"] += mut["append_audit"]
    state["audit_seq"] = mut["audit_seq"]
    return body


def err(state, r):
    with pytest.raises(ApiError) as e:
        check_and_apply(state, r, NOW)
    return e.value.status, e.value.code


def test_transfer_response_exact():
    s = base_state()
    body = apply(s, req())
    assert body == {
        "request_id": "tr-001", "status": "accepted", "state": "active", "blocking_match_id": None,
        "registration": {"player_id": "p2", "league_id": "lg-r1", "squad_id": "sq-b", "parent_squad_id": None,
                         "registration_type": "transfer", "start_date": "2026-09-30", "loan_end_date": None,
                         "role": "substitute"},
        "audit_entry": {"audit_id": "au-0001", "action": "transfer", "player_id": "p2", "league_id": "lg-r1",
                        "from_squad_id": "sq-a", "to_squad_id": "sq-b", "effective_date": "2026-09-30",
                        "state": "active", "who": "user-77", "when": NOW, "why": "Tactical move"}}
    h, new = history(s, "p2", "2026-10-01")
    assert h["current_squad_id"] == "sq-b" and h["parent_squad_id"] is None and new == []
    assert [e["audit_id"] for e in h["history"]] == ["au-0001"]


def test_release_any_date():
    s = base_state()
    body = apply(s, req(type="release", to_squad_id=None, effective_date="2027-01-01"))
    assert body["registration"] is None and body["audit_entry"]["to_squad_id"] is None
    assert history(s, "p2", "2027-01-02")[0]["current_squad_id"] is None


def test_loan_and_auto_return_once():
    s = base_state()
    body = apply(s, req(type="loan", loan_end_date="2026-10-15", effective_date="2026-09-10"))
    reg = body["registration"]
    assert reg["registration_type"] == "loan" and reg["parent_squad_id"] == "sq-a" and reg["loan_end_date"] == "2026-10-15"
    h, new = history(s, "p2", "2026-10-15")
    assert h["current_squad_id"] == "sq-b" and h["parent_squad_id"] == "sq-a" and new == []
    h, new = history(s, "p2", "2026-10-16", NOW)
    assert h["current_squad_id"] == "sq-a" and h["parent_squad_id"] is None
    assert len(new) == 1 and new[0]["who"] == "system" and new[0]["action"] == "loan_return"
    assert [e["action"] for e in h["history"]] == ["loan", "loan_return"]
    assert all(not k.startswith("_") for e in h["history"] for k in e)
    s["audit"] += new
    s["audit_seq"] += len(new)
    h2, new2 = history(s, "p2", "2026-11-01")
    assert new2 == [] and [e["action"] for e in h2["history"]] == ["loan", "loan_return"]


def test_loan_counts_toward_borrower_not_lender():
    s = base_state()
    s["league"]["max_squad_size"] = 3
    apply(s, req(type="loan", player_id="p3", from_squad_id="sq-b", to_squad_id="sq-a",
                 loan_end_date="2026-12-01", effective_date="2026-09-05"))
    # sq-a now has 3 (p1, p2, p3) -> full
    assert err(s, req(request_id="tr-2", player_id="p4", from_squad_id="sq-b", to_squad_id="sq-a",
                      effective_date="2026-09-06")) == (409, "SQUAD_FULL")


def test_deferred_until_match_end():
    s = base_state()
    s["matches_in_progress"] = [{"match_id": "m-live", "home_squad_id": "sq-a", "away_squad_id": "sq-z"}]
    body = apply(s, req())
    assert body["state"] == "deferred_until_match_end" and body["blocking_match_id"] == "m-live"
    assert body["audit_entry"]["state"] == "deferred_until_match_end"


@pytest.mark.parametrize("bad", [
    {"request_id": None}, {"league_id": 5}, {"player_id": "a|b"}, {"type": "swap"}, {"from_squad_id": None},
    {"to_squad_id": None}, {"effective_date": "2026-13-01"}, {"effective_date": "30-09-2026"},
    {"type": "loan", "loan_end_date": "2026-09-30"}, {"type": "loan"}, {"reason": 3}, {"requested_by": None},
])
def test_validation_error(bad):
    assert err(base_state(), req(**bad)) == (400, "VALIDATION_ERROR")


def test_validation_body_not_dict():
    assert err(base_state(), []) == (400, "VALIDATION_ERROR")


def test_not_found_codes():
    assert err(None, req()) == (404, "LEAGUE_NOT_FOUND")
    assert err(base_state(), req(league_id="lg-zz")) == (404, "LEAGUE_NOT_FOUND")
    assert err(base_state(), req(player_id="p99")) == (404, "PLAYER_NOT_FOUND")
    assert err(base_state(), req(to_squad_id="sq-nope")) == (404, "SQUAD_NOT_FOUND")
    assert err(base_state(), req(from_squad_id="sq-nope")) == (404, "SQUAD_NOT_FOUND")


def test_business_codes_in_order():
    s = base_state()
    assert err(s, req(to_squad_id="sq-x")) == (409, "CROSS_TENANT_TRANSFER")
    assert err(s, req(from_squad_id="sq-b")) == (409, "NOT_IN_SQUAD")
    assert err(s, req(effective_date="2026-10-01")) == (409, "TRANSFER_WINDOW_CLOSED")
    assert err(s, req(effective_date="2026-08-31")) == (409, "TRANSFER_WINDOW_CLOSED")
    assert err(s, req(player_id="p1")) == (409, "MIN_POSITION_VIOLATION")
    s2 = base_state()
    s2["league"]["max_squad_size"] = 2
    assert err(s2, req()) == (409, "SQUAD_FULL")
    # cross-tenant beats not-in-squad; not-in-squad beats window
    assert err(s, req(from_squad_id="sq-b", to_squad_id="sq-x")) == (409, "CROSS_TENANT_TRANSFER")
    assert err(s, req(from_squad_id="sq-b", effective_date="2027-01-01")) == (409, "NOT_IN_SQUAD")


def test_player_on_loan():
    s = base_state()
    apply(s, req(type="loan", loan_end_date="2026-10-15", effective_date="2026-09-10"))
    assert err(s, req(request_id="tr-2", from_squad_id="sq-b", to_squad_id="sq-a",
                      effective_date="2026-09-20")) == (409, "PLAYER_ON_LOAN")
    assert err(s, req(request_id="tr-3", type="release", from_squad_id="sq-b", to_squad_id=None,
                      effective_date="2026-09-20")) == (409, "PLAYER_ON_LOAN")


def test_window_inclusive_and_rejection_writes_nothing():
    s = base_state()
    before = copy.deepcopy(s)
    with pytest.raises(ApiError):
        check_and_apply(s, req(effective_date="2026-10-01"), NOW)
    assert s == before
    apply(s, req(effective_date="2026-09-01"))


def test_history_errors():
    assert pytest.raises(ApiError, history, base_state(), "p99", "2026-10-01").value.code == "PLAYER_NOT_FOUND"
    assert pytest.raises(ApiError, history, None, "p1", "2026-10-01").value.code == "PLAYER_NOT_FOUND"
    assert pytest.raises(ApiError, history, base_state(), "p1", "bad").value.code == "VALIDATION_ERROR"
