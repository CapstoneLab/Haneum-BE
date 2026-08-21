import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import UserAction


class ActionRequest(BaseModel):
    request_id: uuid.UUID
    device_id: str = Field(min_length=1, max_length=100)
    user_action: UserAction
    action_timestamp: datetime


class ActionResponseData(BaseModel):
    request_id: uuid.UUID
    user_action: UserAction
    updated: bool
