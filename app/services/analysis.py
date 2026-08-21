import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import AnalysisStatus, RiskLevel
from app.core.errors import ApiError
from app.db.models import AnalysisRequest as AnalysisRequestModel
from app.db.models import RiskLog, UserSettings
from app.schemas.analysis import (
    AnalysisSource,
    AnalyzeRequest,
    AnalyzeResponseData,
    LlmAnalyzeRequest,
    ScoreBreakdown,
)
from app.services.llm import LlmServiceError, create_llm_client
from app.services.masking import MaskingError, mask_sensitive_texts, verify_and_mask
from app.services.rules import analyze_rules
from app.services.scoring import calculate_score

logger = logging.getLogger(__name__)


def _merge_types(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged[:10]


class AnalysisService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.llm = create_llm_client(settings)

    def _find_existing(self, payload: AnalyzeRequest) -> AnalyzeResponseData | None:
        try:
            existing = self.db.get(AnalysisRequestModel, payload.request_id)
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Could not check analyze request idempotency")
            return None
        if existing is None:
            return None
        if existing.device_id != payload.device_id:
            raise ApiError(
                "DUPLICATE_REQUEST",
                "동일한 request_id가 다른 단말에서 이미 사용되었습니다.",
                409,
            )
        if existing.result_payload is None:
            raise ApiError(
                "DUPLICATE_REQUEST",
                "동일한 요청이 아직 처리 중이거나 완료 결과가 없습니다.",
                409,
            )
        return AnalyzeResponseData.model_validate(existing.result_payload)

    def _get_sensitivity(self, device_id: str) -> str:
        try:
            settings = self.db.scalar(
                select(UserSettings).where(UserSettings.device_id == device_id)
            )
            return settings.risk_sensitivity if settings else "normal"
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Could not load user sensitivity; using normal")
            return "normal"

    async def analyze(self, payload: AnalyzeRequest) -> AnalyzeResponseData:
        started = time.perf_counter()
        existing = self._find_existing(payload)
        if existing is not None:
            return existing

        try:
            masked_text = verify_and_mask(payload.input_text, payload.masked_text)
        except MaskingError as exc:
            raise ApiError("MASKING_FAILED", str(exc), 422) from exc

        request_row = AnalysisRequestModel(
            id=payload.request_id,
            device_id=payload.device_id,
            app_name=payload.app_package,
            masked_text=masked_text,
            local_score=payload.local_detection.local_score,
            status=AnalysisStatus.PROCESSING,
        )
        row_persisted = False
        try:
            self.db.add(request_row)
            self.db.commit()
            row_persisted = True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Could not persist initial analysis request")

        rule_result = analyze_rules(payload.input_text, payload.context_messages)
        sensitivity = self._get_sensitivity(payload.device_id)
        masked_context_texts = mask_sensitive_texts(
            [message.text for message in payload.context_messages]
        )
        masked_context = [
            message.model_copy(update={"text": masked_context_text})
            for message, masked_context_text in zip(
                payload.context_messages, masked_context_texts, strict=True
            )
        ]
        llm_data = None
        llm_error: LlmServiceError | None = None
        try:
            llm_data = await self.llm.analyze(
                LlmAnalyzeRequest(
                    request_id=payload.request_id,
                    input_text=masked_text,
                    context_messages=masked_context,
                    local_risk_types=payload.local_detection.risk_types,
                    rule_risk_types=rule_result.risk_types,
                )
            )
        except LlmServiceError as exc:
            llm_error = exc
            logger.warning("LLM fallback for %s: %s", payload.request_id, exc.code)

        risk_types = _merge_types(
            payload.local_detection.risk_types,
            rule_result.risk_types,
            llm_data.risk_types if llm_data else [],
        )
        score_result = calculate_score(
            local_score=payload.local_detection.local_score,
            rule_score=rule_result.score,
            llm_score=llm_data.risk_score if llm_data else None,
            llm_confidence=llm_data.confidence if llm_data else None,
            risk_types=risk_types,
            sensitivity=sensitivity,
        )

        if llm_data:
            reason = llm_data.reason
        elif rule_result.risk_types:
            reason = rule_result.reason
        elif payload.local_detection.risk_types:
            reason = "단말에서 개인정보 또는 금융정보 위험 요소가 감지되었습니다."
        else:
            reason = "감지된 위험 요소가 없습니다."

        completed_at = datetime.now(UTC)
        response = AnalyzeResponseData(
            request_id=payload.request_id,
            risk_score=score_result.score,
            risk_level=score_result.level,
            risk_types=risk_types,
            reason=reason[:150],
            recommended_action=score_result.recommended_action,
            analysis_source=AnalysisSource(
                local_used=True,
                rule_used=True,
                llm_used=llm_data is not None,
                fallback_used=llm_data is None,
            ),
            scores=ScoreBreakdown(
                local_score=payload.local_detection.local_score,
                rule_score=rule_result.score,
                llm_score=llm_data.risk_score if llm_data else None,
                llm_confidence=llm_data.confidence if llm_data else None,
            ),
            processing_time_ms=round((time.perf_counter() - started) * 1000),
            server_timestamp=completed_at,
        )

        try:
            if not row_persisted:
                self.db.add(request_row)
            request_row.rule_score = rule_result.score
            request_row.llm_score = llm_data.risk_score if llm_data else None
            request_row.llm_confidence = llm_data.confidence if llm_data else None
            request_row.llm_used = llm_data is not None
            request_row.fallback_used = llm_data is None
            request_row.status = AnalysisStatus.COMPLETED if llm_data else AnalysisStatus.FALLBACK
            request_row.error_code = llm_error.code if llm_error else None
            request_row.completed_at = completed_at
            request_row.result_payload = response.model_dump(mode="json")

            if score_result.level in {RiskLevel.WARNING, RiskLevel.DANGER}:
                self.db.add(
                    RiskLog(
                        analysis_request_id=payload.request_id,
                        device_id=payload.device_id,
                        app_name=payload.app_package,
                        risk_score=score_result.score,
                        risk_level=score_result.level,
                        risk_types=risk_types,
                        reason=reason[:150],
                        masked_text=masked_text,
                        llm_used=llm_data is not None,
                        fallback_used=llm_data is None,
                    )
                )
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Analysis succeeded but database write failed")

        return response
