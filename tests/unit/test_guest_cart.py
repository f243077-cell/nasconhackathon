import pytest

from app.domain import guest_cart as gc
from app.errors import ApiError

SPEC = {"guest_token": "guest_anon_tok_7721", "registered_user_id": "player-alpha-1",
        "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "test_write_block": True}
STOCK = {"var-jersey-001-L": 5, "var-jersey-001-M": 1, "var-scarf": 2}
PRICES = {"var-jersey-001-L": 450000, "var-jersey-001-M": 450000, "var-scarf": 150000}


def guard(token):
    if gc.is_guest_token(token):
        raise gc.guest_write_forbidden(token)


def run(body, existing=(), stored_key=None):
    """The route's call order, minus the DB."""
    req = gc.validate_request(body)
    gc.check_existence(req, {"player-alpha-1", "player-alpha-2"}.__contains__, PRICES.__contains__)
    decision = gc.replay_decision(req, stored_key)
    if req["test_write_block"]:
        assert gc.verify_write_block(req["guest_token"], guard) == 403
    items = gc.merge_items(list(existing), req["guest_cart"], STOCK, PRICES)
    return decision, gc.build_response(req, items)


def test_spec_example():
    decision, resp = run(SPEC)
    assert decision == "new"
    assert resp == {"guest_token": "guest_anon_tok_7721", "write_block_verified": True, "write_rejection_code": 403,
                    "cart_merged": True,
                    "active_cart": {"user_id": "player-alpha-1", "currency": "PKR", "total_items": 1,
                                    "subtotal_minor": 450000,
                                    "items": [{"variant_id": "var-jersey-001-L", "quantity": 1,
                                               "unit_price_minor": 450000}]}}
    assert gc.sig_payload(resp) == {"cart_merged": True, "guest_token": "guest_anon_tok_7721",
                                    "registered_user_id": "player-alpha-1", "total_items": 1,
                                    "write_rejection_code": 403}


def test_identical_replay_is_replay_and_never_doubles():
    key = gc.request_key(gc.validate_request(SPEC))
    assert gc.replay_decision(gc.validate_request(SPEC), key) == "replay"
    # the route returns the stored body on replay; recomputing over the merged cart must not be done
    assert gc.request_key(gc.validate_request({**SPEC, "test_write_block": True})) == key


def test_default_test_write_block_counts_as_identical():
    explicit = gc.request_key(gc.validate_request(SPEC))
    implied = gc.request_key(gc.validate_request({k: v for k, v in SPEC.items() if k != "test_write_block"}))
    assert explicit == implied


@pytest.mark.parametrize("patch", [
    {"registered_user_id": "player-alpha-2"},
    {"guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 2}]},
    {"test_write_block": False},
])
def test_merged_token_with_other_user_or_payload_is_409(patch):
    key = gc.request_key(gc.validate_request(SPEC))
    with pytest.raises(ApiError) as e:
        gc.replay_decision(gc.validate_request({**SPEC, **patch}), key)
    assert (e.value.status, e.value.code, e.value.details) == (409, "GUEST_TOKEN_ALREADY_MERGED",
                                                               {"guest_token": "guest_anon_tok_7721"})


def test_sums_with_existing_cart_and_guest_duplicates():
    existing = [{"variant_id": "var-scarf", "quantity": 1, "unit_price_minor": 150000},
                {"variant_id": "var-jersey-001-L", "quantity": 2, "unit_price_minor": 450000}]
    body = {**SPEC, "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1},
                                   {"variant_id": "var-jersey-001-M", "quantity": 1},
                                   {"variant_id": "var-jersey-001-L", "quantity": 1}]}
    _, resp = run(body, existing)
    cart = resp["active_cart"]
    assert [(i["variant_id"], i["quantity"]) for i in cart["items"]] == [
        ("var-scarf", 1), ("var-jersey-001-L", 4), ("var-jersey-001-M", 1)]
    assert cart["total_items"] == 6
    assert cart["subtotal_minor"] == 150000 + 4 * 450000 + 450000


def test_merged_quantity_above_stock_is_409_with_variant():
    existing = [{"variant_id": "var-jersey-001-M", "quantity": 1, "unit_price_minor": 450000}]
    body = {**SPEC, "guest_cart": [{"variant_id": "var-jersey-001-M", "quantity": 1}]}
    with pytest.raises(ApiError) as e:
        run(body, existing)
    assert (e.value.status, e.value.code) == (409, "OUT_OF_STOCK")
    assert e.value.details == {"variant_id": "var-jersey-001-M", "requested": 2, "available": 1}


def test_exactly_stock_is_fine():
    _, resp = run({**SPEC, "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 5}]})
    assert resp["active_cart"]["total_items"] == 5


def test_no_write_block_check():
    _, resp = run({**SPEC, "test_write_block": False})
    assert resp["write_block_verified"] is False and resp["write_rejection_code"] is None
    assert gc.sig_payload(resp)["write_rejection_code"] is None


def test_unknown_user_404_before_unknown_variant():
    body = {**SPEC, "registered_user_id": "ghost", "guest_cart": [{"variant_id": "var-nope", "quantity": 1}]}
    with pytest.raises(ApiError) as e:
        run(body)
    assert (e.value.status, e.value.code, e.value.details) == (404, "PLAYER_NOT_FOUND", {"registered_user_id": "ghost"})


def test_unknown_variant_404():
    body = {**SPEC, "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}, {"variant_id": "var-nope", "quantity": 1}]}
    with pytest.raises(ApiError) as e:
        run(body)
    assert (e.value.status, e.value.code, e.value.details) == (404, "VARIANT_NOT_FOUND", {"variant_id": "var-nope"})


@pytest.mark.parametrize("patch,field", [
    ({"guest_token": ""}, "guest_token"),
    ({"guest_token": "anon_tok_7721"}, "guest_token"),
    ({"guest_token": 7721}, "guest_token"),
    ({"registered_user_id": ""}, "registered_user_id"),
    ({"guest_cart": []}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "v", "quantity": 1}] * 11}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "v", "quantity": 0}]}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "v", "quantity": 1.0}]}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "v", "quantity": True}]}, "guest_cart"),
    ({"guest_cart": [{"variant_id": "", "quantity": 1}]}, "guest_cart"),
    ({"guest_cart": ["v"]}, "guest_cart"),
    ({"test_write_block": "true"}, "test_write_block"),
])
def test_schema_errors(patch, field):
    with pytest.raises(ApiError) as e:
        gc.validate_request({**SPEC, **patch})
    assert (e.value.status, e.value.code) == (400, "VALIDATION_ERROR") and field in e.value.details["fields"]


def test_non_object_body():
    with pytest.raises(ApiError):
        gc.validate_request("x")


@pytest.mark.parametrize("token,guest", [
    ("guest_anon_tok_7721", True), ("guest_anon_tok_", True), ("guest_other", False), ("eyJhbGci", False), (None, False),
])
def test_is_guest_token(token, guest):
    assert gc.is_guest_token(token) is guest


def test_verify_write_block_requires_a_real_403():
    def open_guard(_):
        return None

    def wrong_guard(_):
        raise ApiError(401, "UNAUTHENTICATED")

    with pytest.raises(RuntimeError):
        gc.verify_write_block("guest_anon_tok_1", open_guard)
    with pytest.raises(ApiError):
        gc.verify_write_block("guest_anon_tok_1", wrong_guard)


def test_guest_write_forbidden_shape():
    e = gc.guest_write_forbidden("guest_anon_tok_7721")
    assert (e.status, e.code, e.details) == (403, "GUEST_WRITE_FORBIDDEN", {"guest_token": "guest_anon_tok_7721"})
