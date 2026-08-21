import secrets

from fastapi import Header

from app.core.config import get_settings
from app.core.errors import ApiError


async def require_android_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().android_api_key
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise ApiError("UNAUTHORIZED", "API 인증에 실패했습니다.", 401)
