import pytest

from app.schemas.analysis import LlmAnalyzeData, LlmModelInfo
from app.services.claude import ClaudeService
from scripts.android_simulator import analyze_standalone, build_payload, detect_locally


def test_detects_and_masks_android_local_sensitive_data() -> None:
    text = "인증번호 123456을 지금 보내주세요"

    risk_types, score = detect_locally(text)
    _, payload = build_payload(text, contexts=["검찰 수사관입니다"], app_package="test.app")

    assert risk_types == ["verification_code"]
    assert score == 30
    assert payload["masked_text"] == "인증번호 ******을 지금 보내주세요"
    assert payload["local_detection"]["detected"] is True
    assert payload["context_messages"][0]["text"] == "검찰 수사관입니다"


@pytest.mark.anyio
async def test_standalone_analyzes_without_api_or_database(monkeypatch) -> None:
    async def fake_analyze(self, payload):
        return LlmAnalyzeData(
            request_id=payload.request_id,
            risk_score=82,
            risk_types=["money_transfer", "institution_impersonation", "urgency"],
            confidence=0.9,
            reason="기관을 사칭하며 긴급 송금을 요구합니다.",
            model=LlmModelInfo(name="test", version="1", runtime="anthropic"),
            processing_time_ms=10,
        )

    monkeypatch.setattr(ClaudeService, "analyze", fake_analyze)
    _, payload = build_payload(
        "지금 계좌로 300만원 보내주세요",
        contexts=["검찰 수사관입니다"],
        app_package="test.app",
    )

    result = await analyze_standalone(payload)

    assert result["risk"]["level"] == "danger"
    assert result["claude_used"] is True
    assert result["fallback_used"] is False
