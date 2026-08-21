from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.constants import RiskLevel
from app.core.errors import ApiError
from app.db.models import RiskLog
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.logs import RiskLogDeleteData, RiskLogItem, RiskLogListData

router = APIRouter(tags=["risk-logs"])


@router.get("/risk-logs", response_model=ApiResponse[RiskLogListData])
async def list_risk_logs(
    device_id: str = Query(min_length=1, max_length=100),
    risk_level: RiskLevel | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[RiskLogListData]:
    cursor_id: int | None = None
    if cursor is not None:
        try:
            cursor_id = int(cursor)
        except ValueError as exc:
            raise ApiError("INVALID_REQUEST", "cursor 값이 올바르지 않습니다.", 400) from exc

    query = select(RiskLog).where(RiskLog.device_id == device_id)
    if risk_level is not None:
        query = query.where(RiskLog.risk_level == risk_level)
    if cursor_id is not None:
        query = query.where(RiskLog.id < cursor_id)
    query = query.order_by(RiskLog.id.desc()).limit(limit + 1)

    try:
        rows = list(db.scalars(query))
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApiError("DATABASE_UNAVAILABLE", "위험 기록을 조회하지 못했습니다.", 503) from exc

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        RiskLogItem(
            id=row.id,
            request_id=row.analysis_request_id,
            app_package=row.app_name,
            risk_score=row.risk_score,
            risk_level=row.risk_level,
            risk_types=row.risk_types,
            reason=row.reason,
            masked_text=row.masked_text,
            user_action=row.user_action,
            llm_used=row.llm_used,
            fallback_used=row.fallback_used,
            created_at=row.created_at,
        )
        for row in rows
    ]
    next_cursor = str(rows[-1].id) if has_more and rows else None
    return ApiResponse(data=RiskLogListData(items=items, next_cursor=next_cursor))


@router.delete("/risk-logs/{log_id}", response_model=ApiResponse[RiskLogDeleteData])
async def delete_risk_log(
    log_id: int,
    device_id: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
) -> ApiResponse[RiskLogDeleteData]:
    try:
        row = db.scalar(select(RiskLog).where(RiskLog.id == log_id, RiskLog.device_id == device_id))
        if row is not None:
            db.delete(row)
            db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApiError("DB_WRITE_FAILED", "위험 기록을 삭제하지 못했습니다.", 500) from exc
    return ApiResponse(data=RiskLogDeleteData(deleted=True, log_id=log_id))
