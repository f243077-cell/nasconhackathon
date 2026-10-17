from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "", details: dict | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code
        self.details = details or {}


def validation_error(fields: list[str], message: str = "Invalid request") -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": list(dict.fromkeys(fields))})


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error_response(status: int, code: str, message: str, details: dict | None = None, headers: dict | None = None):
    return JSONResponse(status_code=status, content=error_body(code, message, details), headers=headers)
