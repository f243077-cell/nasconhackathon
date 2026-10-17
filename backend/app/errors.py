from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "", details: dict | None = None):
        super().__init__(message or code)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def validation_error(fields: list[str], message: str = "Invalid request") -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": fields})
