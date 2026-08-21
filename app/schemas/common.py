from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampedResponse(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
