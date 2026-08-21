import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import RISK_TYPES, RecommendedAction, RiskLevel


class ContextMessage(BaseModel):
    speaker: Literal["user", "other", "unknown"]
    text: str = Field(min_length=1, max_length=300)


class LocalDetection(BaseModel):
    detected: bool
    risk_types: list[str] = Field(max_length=10)
    local_score: int = Field(ge=0, le=100)

    @field_validator("risk_types")
    @classmethod
    def validate_risk_types(cls, values: list[str]) -> list[str]:
        invalid = set(values) - RISK_TYPES
        if invalid:
            raise ValueError(f"지원하지 않는 위험 유형: {sorted(invalid)}")
        return list(dict.fromkeys(values))


class AnalyzeRequest(BaseModel):
    request_id: uuid.UUID
    device_id: str = Field(min_length=1, max_length=100)
    app_package: str | None = Field(default=None, max_length=150)
    input_text: str = Field(min_length=1, max_length=1000)
    masked_text: str = Field(min_length=1, max_length=1000)
    context_messages: list[ContextMessage] = Field(default_factory=list, max_length=5)
    local_detection: LocalDetection
    client_timestamp: datetime
    client_version: str = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_context_size(self) -> "AnalyzeRequest":
        if sum(len(item.text) for item in self.context_messages) > 1000:
            raise ValueError("전체 대화 맥락은 1,000자를 초과할 수 없습니다.")
        return self


class AnalysisSource(BaseModel):
    local_used: bool
    rule_used: bool
    llm_used: bool
    fallback_used: bool


class ScoreBreakdown(BaseModel):
    local_score: int = Field(ge=0, le=100)
    rule_score: int = Field(ge=0, le=100)
    llm_score: int | None = Field(default=None, ge=0, le=100)
    llm_confidence: float | None = Field(default=None, ge=0, le=1)


class AnalyzeResponseData(BaseModel):
    request_id: uuid.UUID
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    risk_types: list[str] = Field(max_length=10)
    reason: str = Field(max_length=150)
    recommended_action: RecommendedAction
    analysis_source: AnalysisSource
    scores: ScoreBreakdown
    processing_time_ms: int = Field(ge=0)
    server_timestamp: datetime


class LlmAnalyzeRequest(BaseModel):
    request_id: uuid.UUID
    input_text: str = Field(min_length=1, max_length=1000)
    context_messages: list[ContextMessage] = Field(default_factory=list, max_length=5)
    local_risk_types: list[str] = Field(max_length=10)
    rule_risk_types: list[str] = Field(max_length=10)
    language: str = "ko"


class LlmModelInfo(BaseModel):
    name: str
    version: str
    runtime: str


class LlmAnalyzeData(BaseModel):
    request_id: uuid.UUID
    risk_score: int = Field(ge=0, le=100)
    risk_types: list[str] = Field(max_length=10)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=150)
    model: LlmModelInfo | None = None
    processing_time_ms: int = Field(ge=0)

    @field_validator("risk_types")
    @classmethod
    def validate_risk_types(cls, values: list[str]) -> list[str]:
        invalid = set(values) - RISK_TYPES
        if invalid:
            raise ValueError(f"지원하지 않는 LLM 위험 유형: {sorted(invalid)}")
        return list(dict.fromkeys(values))


class LlmAnalyzeEnvelope(BaseModel):
    success: Literal[True]
    data: LlmAnalyzeData
