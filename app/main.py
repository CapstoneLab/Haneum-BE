import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.routes.realtime import router as realtime_router
from app.core.config import get_settings
from app.core.errors import ApiError, api_error_handler, validation_error_handler

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


@app.middleware("http")
async def enforce_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > 32 * 1024
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "전체 요청 크기는 32KB를 초과할 수 없습니다.",
                        "details": None,
                    },
                    "request_id": request.headers.get("X-Request-ID"),
                    "fallback_used": False,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
    return await call_next(request)


app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(realtime_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "version": settings.app_version}
