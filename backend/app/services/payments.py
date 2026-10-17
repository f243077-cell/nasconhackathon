"""Mock payment gateway (spec 5.12). Self-built; no external provider."""
import uuid

SUCCESS = "tok_success"
DECLINED = "tok_declined"
CAPTURE_FAIL = "tok_capture_fail"


class PaymentError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def authorize(token: str, amount_minor: int) -> str:
    if token not in (SUCCESS, CAPTURE_FAIL):
        raise PaymentError("PAYMENT_DECLINED", "Payment authorization was declined")
    return "auth_" + uuid.uuid4().hex[:12]


def capture(token: str, authorization_id: str) -> str:
    if token == CAPTURE_FAIL:
        void(authorization_id)
        raise PaymentError("PAYMENT_CAPTURE_FAILED", "Payment capture failed; authorization voided")
    return "cap_" + uuid.uuid4().hex[:12]


def void(authorization_id: str) -> None:
    return None


def refund(capture_id: str, amount_minor: int) -> str:
    return "ref_" + uuid.uuid4().hex[:12]
