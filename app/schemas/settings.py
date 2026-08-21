from datetime import datetime

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    risk_sensitivity: str = Field(default="normal", pattern="^(low|normal|high)$")
    tts_enabled: bool = False
    vibration_enabled: bool = True
    large_text_enabled: bool = False
    high_contrast_enabled: bool = False


class SettingsResponseData(SettingsUpdate):
    device_id: str
    updated_at: datetime
