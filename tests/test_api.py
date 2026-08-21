import uuid
from datetime import UTC, datetime

import pytest

from app.schemas.analysis import LlmAnalyzeData, LlmModelInfo
from app.services.llm import LlmClient, LlmServiceError

pytestmark = pytest.mark.anyio


def _request_payload(request_id: uuid.UUID, *, dangerous: bool = False) -> dict:
    if dangerous:
        input_text = "지금 받은 인증번호 123456 보내줘"
        masked_text = "지금 받은 인증번호 ****** 보내줘"
        local_detection = {
            "detected": True,
            "risk_types": ["verification_code"],
            "local_score": 30,
        }
    else:
        input_text = "오늘 날씨가 어때?"
        masked_text = input_text
        local_detection = {"detected": False, "risk_types": [], "local_score": 0}
    return {
        "request_id": str(request_id),
        "device_id": "test-device",
        "app_package": "com.example.chat",
        "input_text": input_text,
        "masked_text": masked_text,
        "context_messages": [],
        "local_detection": local_detection,
        "client_timestamp": datetime.now(UTC).isoformat(),
        "client_version": "0.1.0",
    }


async def test_analyze_is_idempotent(client, auth_headers, monkeypatch) -> None:
    calls = 0

    async def fake_analyze(self, payload):
        nonlocal calls
        calls += 1
        return LlmAnalyzeData(
            request_id=payload.request_id,
            risk_score=5,
            risk_types=[],
            confidence=0.9,
            reason="감지된 위험 요소가 없습니다.",
            model=LlmModelInfo(name="test", version="1", runtime="test"),
            processing_time_ms=10,
        )

    monkeypatch.setattr(LlmClient, "analyze", fake_analyze)
    request_id = uuid.uuid4()
    headers = {**auth_headers, "X-Request-ID": str(request_id)}
    payload = _request_payload(request_id)

    first = await client.post("/api/v1/analyze", headers=headers, json=payload)
    second = await client.post("/api/v1/analyze", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert calls == 1


async def test_analyze_sends_only_masked_text_to_llm(client, auth_headers, monkeypatch) -> None:
    captured_payloads = []

    async def fake_analyze(self, payload):
        captured_payloads.append(payload)
        return LlmAnalyzeData(
            request_id=payload.request_id,
            risk_score=10,
            risk_types=[],
            confidence=0.9,
            reason="감지된 위험 요소가 없습니다.",
            model=LlmModelInfo(name="test", version="1", runtime="test"),
            processing_time_ms=10,
        )

    monkeypatch.setattr(LlmClient, "analyze", fake_analyze)
    request_id = uuid.uuid4()
    headers = {**auth_headers, "X-Request-ID": str(request_id)}
    payload = _request_payload(request_id)
    payload["input_text"] = "인증번호 123456 보내줘"
    payload["masked_text"] = "인증번호 ****** 보내줘"
    payload["context_messages"] = [
        {"speaker": "other", "text": "인증번호를 알려주세요"},
        {"speaker": "user", "text": "받은 번호는 654321입니다"},
    ]

    response = await client.post("/api/v1/analyze", headers=headers, json=payload)

    assert response.status_code == 200
    sent = captured_payloads[0]
    assert "123456" not in sent.input_text
    assert "654321" not in sent.context_messages[1].text
    assert sent.input_text == "인증번호 ****** 보내줘"
    assert sent.context_messages[1].text == "받은 번호는 ******입니다"


async def test_danger_log_and_action_flow(client, auth_headers, monkeypatch) -> None:
    async def fake_analyze(self, payload):
        return LlmAnalyzeData(
            request_id=payload.request_id,
            risk_score=88,
            risk_types=["verification_code", "urgency", "social_engineering"],
            confidence=0.93,
            reason="인증번호 공유 요구와 긴급성 표현이 함께 감지되었습니다.",
            model=LlmModelInfo(name="test", version="1", runtime="test"),
            processing_time_ms=10,
        )

    monkeypatch.setattr(LlmClient, "analyze", fake_analyze)
    request_id = uuid.uuid4()
    headers = {**auth_headers, "X-Request-ID": str(request_id)}
    response = await client.post(
        "/api/v1/analyze", headers=headers, json=_request_payload(request_id, dangerous=True)
    )

    assert response.status_code == 200
    assert response.json()["data"]["risk_level"] == "danger"

    logs = await client.get(
        "/api/v1/risk-logs", headers=auth_headers, params={"device_id": "test-device"}
    )
    assert logs.status_code == 200
    assert len(logs.json()["data"]["items"]) == 1
    assert "123456" not in logs.json()["data"]["items"][0]["masked_text"]

    action = await client.post(
        "/api/v1/actions",
        headers=auth_headers,
        json={
            "request_id": str(request_id),
            "device_id": "test-device",
            "user_action": "cancel",
            "action_timestamp": datetime.now(UTC).isoformat(),
        },
    )
    assert action.status_code == 200
    assert action.json()["data"]["user_action"] == "cancel"


async def test_api_key_is_required(client) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_llm_failure_uses_rule_fallback(client, auth_headers, monkeypatch) -> None:
    async def unavailable(self, payload):
        raise LlmServiceError("LLM_UNAVAILABLE", "LLM 서버에 연결할 수 없습니다.")

    monkeypatch.setattr(LlmClient, "analyze", unavailable)
    request_id = uuid.uuid4()
    headers = {**auth_headers, "X-Request-ID": str(request_id)}
    response = await client.post(
        "/api/v1/analyze", headers=headers, json=_request_payload(request_id, dangerous=True)
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["analysis_source"]["llm_used"] is False
    assert data["analysis_source"]["fallback_used"] is True
    assert data["risk_level"] == "danger"


async def test_settings_round_trip(client, auth_headers) -> None:
    default_response = await client.get("/api/v1/settings/test-device", headers=auth_headers)
    assert default_response.status_code == 200
    assert default_response.json()["data"]["risk_sensitivity"] == "normal"

    updated = await client.put(
        "/api/v1/settings/test-device",
        headers=auth_headers,
        json={
            "risk_sensitivity": "high",
            "tts_enabled": True,
            "vibration_enabled": True,
            "large_text_enabled": True,
            "high_contrast_enabled": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["risk_sensitivity"] == "high"
    assert updated.json()["data"]["tts_enabled"] is True


async def test_validation_error_uses_common_envelope(client, auth_headers) -> None:
    request_id = uuid.uuid4()
    headers = {**auth_headers, "X-Request-ID": str(request_id)}
    payload = _request_payload(request_id)
    payload["local_detection"]["risk_types"] = ["not-supported"]

    response = await client.post("/api/v1/analyze", headers=headers, json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
