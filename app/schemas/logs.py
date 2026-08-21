import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import RiskLevel, UserAction


class RiskLogItem(BaseModel):
    id: int
    request_id: uuid.UUID | None
    app_package: str | None
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    risk_types: list[str]
    reason: str | None
    masked_text: str | None
    user_action: UserAction
    llm_used: bool
    fallback_used: bool
    created_at: datetime


class RiskLogListData(BaseModel):
    items: list[RiskLogItem]
    next_cursor: str | None


class RiskLogDeleteData(BaseModel):
    deleted: bool
    log_id: int
