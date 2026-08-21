from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import AnalysisRequest, RiskLog
from app.db.session import get_db
from app.schemas.actions import ActionRequest, ActionResponseData
from app.schemas.common import ApiResponse

router = APIRouter(tags=["actions"])


@router.post("/actions", response_model=ApiResponse[ActionResponseData])
async def save_action(
    payload: ActionRequest, db: Session = Depends(get_db)
) -> ApiResponse[ActionResponseData]:
    try:
        request_row = db.get(AnalysisRequest, payload.request_id)
        if request_row is None or request_row.device_id != payload.device_id:
            raise ApiError("REQUEST_NOT_FOUND", "분석 요청을 찾을 수 없습니다.", 404)
        risk_log = db.scalar(
            select(RiskLog).where(RiskLog.analysis_request_id == payload.request_id)
        )
        if risk_log is None:
            raise ApiError("REQUEST_NOT_FOUND", "저장된 위험 로그를 찾을 수 없습니다.", 404)
        risk_log.user_action = payload.user_action
        db.commit()
    except ApiError:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApiError("DB_WRITE_FAILED", "사용자 조치를 저장하지 못했습니다.", 500) from exc

    return ApiResponse(
        data=ActionResponseData(
            request_id=payload.request_id,
            user_action=payload.user_action,
            updated=True,
        )
    )
