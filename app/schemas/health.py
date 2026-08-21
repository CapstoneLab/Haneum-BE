from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BackendHealth(BaseModel):
    status: Literal["up"] = "up"


class DependencyHealth(BaseModel):
    status: Literal["up", "down"]
    response_time_ms: int | None = None


class HealthResponseData(BaseModel):
    status: Literal["ok", "degraded", "down"]
    backend: BackendHealth
    database: DependencyHealth
    llm: DependencyHealth
    version: str
    timestamp: datetime
