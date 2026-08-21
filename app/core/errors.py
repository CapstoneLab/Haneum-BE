from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        details: Any = None,
        fallback_used: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.fallback_used = fallback_used


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "request_id": request_id,
            "fallback_used": exc.fallback_used,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": {
                "code": "INVALID_REQUEST",
                "message": "요청 데이터 형식이 올바르지 않습니다.",
                "details": jsonable_encoder(exc.errors()),
            },
            "request_id": request.headers.get("X-Request-ID"),
            "fallback_used": False,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
