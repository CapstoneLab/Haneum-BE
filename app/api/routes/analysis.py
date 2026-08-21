import uuid

from fastapi import APIRouter, Depends, Header

from app.api.dependencies import get_analysis_service
from app.core.errors import ApiError
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponseData
from app.schemas.common import ApiResponse
from app.services.analysis import AnalysisService

router = APIRouter(tags=["analysis"])


@router.post("/analyze", response_model=ApiResponse[AnalyzeResponseData])
async def analyze(
    payload: AnalyzeRequest,
    x_request_id: uuid.UUID = Header(alias="X-Request-ID"),
    service: AnalysisService = Depends(get_analysis_service),
) -> ApiResponse[AnalyzeResponseData]:
    if x_request_id != payload.request_id:
        raise ApiError(
            "INVALID_REQUEST", "X-Request-ID와 본문의 request_id가 일치하지 않습니다.", 400
        )
    return ApiResponse(data=await service.analyze(payload))
