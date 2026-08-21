from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import UserSettings
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.settings import SettingsResponseData, SettingsUpdate

router = APIRouter(tags=["settings"])


def _to_response(row: UserSettings) -> SettingsResponseData:
    return SettingsResponseData(
        device_id=row.device_id,
        risk_sensitivity=row.risk_sensitivity,
        tts_enabled=row.tts_enabled,
        vibration_enabled=row.vibration_enabled,
        large_text_enabled=row.large_text_enabled,
        high_contrast_enabled=row.high_contrast_enabled,
        updated_at=row.updated_at,
    )


@router.get("/settings/{device_id}", response_model=ApiResponse[SettingsResponseData])
async def get_user_settings(
    device_id: str = Path(min_length=1, max_length=100), db: Session = Depends(get_db)
) -> ApiResponse[SettingsResponseData]:
    try:
        row = db.scalar(select(UserSettings).where(UserSettings.device_id == device_id))
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApiError("DATABASE_UNAVAILABLE", "설정을 조회하지 못했습니다.", 503) from exc

    if row is None:
        now = datetime.now(UTC)
        return ApiResponse(data=SettingsResponseData(device_id=device_id, updated_at=now))
    return ApiResponse(data=_to_response(row))


@router.put("/settings/{device_id}", response_model=ApiResponse[SettingsResponseData])
async def update_user_settings(
    payload: SettingsUpdate,
    device_id: str = Path(min_length=1, max_length=100),
    db: Session = Depends(get_db),
) -> ApiResponse[SettingsResponseData]:
    try:
        row = db.scalar(select(UserSettings).where(UserSettings.device_id == device_id))
        if row is None:
            row = UserSettings(device_id=device_id)
            db.add(row)
        for field, value in payload.model_dump().items():
            setattr(row, field, value)
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApiError("DB_WRITE_FAILED", "설정을 저장하지 못했습니다.", 500) from exc
    return ApiResponse(data=_to_response(row))
