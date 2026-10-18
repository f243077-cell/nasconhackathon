"""Part II autograder routes for co-stream sessions (5.5), guest cart merge (5.7) and moderation + DLQ (5.8)."""
from fastapi import APIRouter, Depends

from ..repo import social as social_repo
from .common import json_body, respond, run_tx

router = APIRouter()


@router.post("/audit/v1/costream/session")
def costream_session(body=Depends(json_body)):
    status, resp = run_tx(social_repo.costream_session, body)
    return respond(status, resp)


@router.post("/audit/v1/guest/cart-merge")
def guest_cart_merge(body=Depends(json_body)):
    status, resp = run_tx(social_repo.cart_merge, body)
    return respond(status, resp)


@router.post("/audit/v1/moderation/test")
def moderation_test(body=Depends(json_body)):
    return respond(200, run_tx(social_repo.moderation_test, body))
