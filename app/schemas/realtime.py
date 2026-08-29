from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import AnalyzeRequest, AnalyzeResponseData


class RealtimeDraftMessage(BaseModel):
    type: Literal["draft_changed"]
    session_id: str = Field(min_length=1, max_length=150)
    sequence: int = Field(ge=0)
    payload: AnalyzeRequest


class RealtimeAnalysisEvent(BaseModel):
    type: Literal["provisional_result", "final_result"]
    session_id: str
    sequence: int
    data: AnalyzeResponseData


class RealtimeErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    session_id: str | None = None
    sequence: int | None = None
