from typing import Any

from fastapi import Request


def ok(data: Any = None, message: str = "success", request: Request | None = None) -> dict[str, Any]:
    return {
        "code": "OK",
        "message": message,
        "data": data,
        "errors": [],
        "request_id": getattr(request.state, "request_id", "") if request else "",
    }


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.errors = errors or []


def error_payload(exc: ApiError, request: Request) -> dict[str, Any]:
    return {
        "code": exc.code,
        "message": exc.message,
        "data": None,
        "errors": exc.errors,
        "request_id": request.state.request_id,
    }

