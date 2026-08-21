import json
import uuid

import httpx
import pytest

from app.core.config import Settings
from app.schemas.analysis import ContextMessage, LlmAnalyzeRequest
from app.services.claude import ClaudeService
from app.services.llm import LlmServiceError

pytestmark = pytest.mark.anyio


def _payload() -> LlmAnalyzeRequest:
    return LlmAnalyzeRequest(
        request_id=uuid.uuid4(),
        input_text="[ACCOUNT_NUMBER]로 지금 300만원 보내주세요",
        context_messages=[ContextMessage(speaker="other", text="검찰 수사관입니다")],
        local_risk_types=["account_number"],
        rule_risk_types=["money_transfer", "institution_impersonation"],
    )


async def test_claude_uses_structured_output_and_maps_categories() -> None:
    captured_request: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_request.update(json.loads(request.content))
        result = {
            "fraud_detected": True,
            "categories": ["TRANSFER_REQUEST", "IMPERSONATION", "URGENCY"],
            "risk_score": 82,
            "confidence": 0.94,
            "signals": ["기관 사칭 가능성이 있습니다.", "긴급 송금을 요구합니다."],
            "recommended_action": "BLOCK",
        }
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-test",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": json.dumps(result)}],
            },
        )

    settings = Settings(
        llm_provider="claude",
        anthropic_api_key="test-anthropic-key",
        anthropic_base_url="https://api.anthropic.test/v1",
    )
    service = ClaudeService(settings, transport=httpx.MockTransport(handler))

    result = await service.analyze(_payload())

    assert captured_request["output_config"]["format"]["type"] == "json_schema"
    assert captured_request["model"] == settings.anthropic_model
    assert result.risk_score == 82
    assert result.risk_types == ["money_transfer", "institution_impersonation", "urgency"]
    assert result.model is not None
    assert result.model.runtime == "anthropic"


async def test_claude_rejects_invalid_structured_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-test",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": '{"risk_score": 82}'}],
            },
        )

    settings = Settings(
        llm_provider="claude",
        anthropic_api_key="test-anthropic-key",
        anthropic_base_url="https://api.anthropic.test/v1",
    )
    service = ClaudeService(settings, transport=httpx.MockTransport(handler))

    with pytest.raises(LlmServiceError) as exc_info:
        await service.analyze(_payload())

    assert exc_info.value.code == "CLAUDE_INVALID_RESPONSE"


async def test_claude_limits_excess_signals() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        result = {
            "fraud_detected": True,
            "categories": ["transfer_request"],
            "risk_score": 70,
            "confidence": 0.8,
            "signals": ["가" * 110, *[f"위험 신호 {index}" for index in range(6)]],
            "recommended_action": "block",
        }
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-test",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": json.dumps(result)}],
            },
        )

    settings = Settings(
        llm_provider="claude",
        anthropic_api_key="test-anthropic-key",
        anthropic_base_url="https://api.anthropic.test/v1",
    )
    service = ClaudeService(settings, transport=httpx.MockTransport(handler))

    result = await service.analyze(_payload())

    assert "가" * 100 in result.reason
    assert "가" * 101 not in result.reason
    assert "위험 신호 3" in result.reason
    assert "위험 신호 4" not in result.reason
