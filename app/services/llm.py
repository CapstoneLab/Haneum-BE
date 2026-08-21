import time
import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.analysis import LlmAnalyzeData, LlmAnalyzeEnvelope, LlmAnalyzeRequest


@dataclass(frozen=True)
class LlmServiceError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class LlmAnalyzer(Protocol):
    async def analyze(self, payload: LlmAnalyzeRequest) -> LlmAnalyzeData: ...

    async def health(self) -> tuple[bool, int | None]: ...


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.llm_base_url.rstrip("/") + "/"
        self.api_key = settings.internal_api_key
        self.timeout = settings.llm_timeout_seconds

    async def analyze(self, payload: LlmAnalyzeRequest) -> LlmAnalyzeData:
        headers = {
            "X-Internal-API-Key": self.api_key,
            "X-Request-ID": str(payload.request_id),
        }
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.post(
                    "analyze", headers=headers, json=payload.model_dump(mode="json")
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LlmServiceError("LLM_TIMEOUT", "LLM 분석 시간이 초과되었습니다.") from exc
        except httpx.HTTPError as exc:
            raise LlmServiceError("LLM_UNAVAILABLE", "LLM 서버에 연결할 수 없습니다.") from exc

        try:
            envelope = LlmAnalyzeEnvelope.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise LlmServiceError(
                "LLM_INVALID_RESPONSE", "LLM 응답 형식이 올바르지 않습니다."
            ) from exc
        return envelope.data

    async def health(self) -> tuple[bool, int | None]:
        started = time.perf_counter()
        headers = {"X-Internal-API-Key": self.api_key, "X-Request-ID": str(uuid.uuid4())}
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=1.0) as client:
                response = await client.get("health", headers=headers)
                response.raise_for_status()
            return True, round((time.perf_counter() - started) * 1000)
        except httpx.HTTPError:
            return False, None


def create_llm_client(settings: Settings) -> LlmAnalyzer:
    if settings.llm_provider == "claude":
        from app.services.claude import ClaudeService

        return ClaudeService(settings)
    return LlmClient(settings)
