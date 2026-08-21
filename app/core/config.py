from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_name: str = "KeyBack API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    android_api_key: str = Field(default="development-key-change-me", min_length=12)
    internal_api_key: str = Field(default="internal-development-key-change-me", min_length=12)
    database_url: str = "postgresql+psycopg://keyback:keyback@localhost:5432/keyback"
    llm_provider: Literal["local", "claude"] = "claude"
    llm_base_url: str = "http://127.0.0.1:8001/internal/v1"
    llm_timeout_seconds: float = Field(default=8.0, gt=0, le=10)
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_version: str = "2023-06-01"
    claude_max_tokens: int = Field(default=700, ge=256, le=4096)
    prompt_version: str = "fraud-analysis-v1"
    db_write_timeout_seconds: float = Field(default=0.5, gt=0, le=5)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
