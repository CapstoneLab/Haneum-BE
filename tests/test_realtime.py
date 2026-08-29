import asyncio
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import LlmAnalyzeData, LlmModelInfo
from app.services.llm import LlmClient


def _draft_message(sequence: int) -> dict:
    request_id = uuid.uuid4()
    return {
        "type": "draft_changed",
        "session_id": "keyboard-session-1",
        "sequence": sequence,
        "payload": {
            "request_id": str(request_id),
            "device_id": "test-device",
            "app_package": "com.example.chat",
            "input_text": "send verification code 123456 now",
            "masked_text": "send verification code ****** now",
            "context_messages": [],
            "local_detection": {
                "detected": True,
                "risk_types": ["verification_code", "urgency"],
                "local_score": 70,
            },
            "client_timestamp": datetime.now(UTC).isoformat(),
            "client_version": "0.1.0",
        },
    }


def test_realtime_sends_provisional_before_final(monkeypatch) -> None:
    async def fake_analyze(self, payload):
        return LlmAnalyzeData(
            request_id=payload.request_id,
            risk_score=90,
            risk_types=["verification_code", "urgency"],
            confidence=0.95,
            reason="Verification code and urgency signals detected.",
            model=LlmModelInfo(name="test", version="1", runtime="test"),
            processing_time_ms=10,
        )

    monkeypatch.setattr(LlmClient, "analyze", fake_analyze)

    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/v1/realtime", headers={"X-API-Key": "test-android-api-key"}
        ) as websocket:
            websocket.send_json(_draft_message(1))
            provisional = websocket.receive_json()
            final = websocket.receive_json()

    assert provisional["type"] == "provisional_result"
    assert provisional["sequence"] == 1
    assert provisional["data"]["analysis_source"]["llm_used"] is False
    assert final["type"] == "final_result"
    assert final["sequence"] == 1
    assert final["data"]["analysis_source"]["llm_used"] is True


def test_realtime_rejects_stale_sequence(monkeypatch) -> None:
    async def fake_analyze(self, payload):
        return LlmAnalyzeData(
            request_id=payload.request_id,
            risk_score=10,
            risk_types=[],
            confidence=0.9,
            reason="No risk.",
            model=LlmModelInfo(name="test", version="1", runtime="test"),
            processing_time_ms=10,
        )

    monkeypatch.setattr(LlmClient, "analyze", fake_analyze)

    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/v1/realtime", headers={"X-API-Key": "test-android-api-key"}
        ) as websocket:
            websocket.send_json(_draft_message(2))
            assert websocket.receive_json()["type"] == "provisional_result"
            websocket.send_json(_draft_message(1))
            error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "STALE_SEQUENCE"
    assert error["sequence"] == 1


def test_realtime_discards_final_result_for_superseded_draft(monkeypatch) -> None:
    async def fake_analyze(self, payload):
        if payload.input_text.endswith("first"):
            await asyncio.sleep(0.05)
        return LlmAnalyzeData(
            request_id=payload.request_id,
            risk_score=20,
            risk_types=[],
            confidence=0.9,
            reason="Current draft result.",
            model=LlmModelInfo(name="test", version="1", runtime="test"),
            processing_time_ms=10,
        )

    monkeypatch.setattr(LlmClient, "analyze", fake_analyze)
    first = _draft_message(1)
    first["payload"]["input_text"] = "first"
    first["payload"]["masked_text"] = "first"
    second = _draft_message(2)

    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/v1/realtime", headers={"X-API-Key": "test-android-api-key"}
        ) as websocket:
            websocket.send_json(first)
            assert websocket.receive_json()["sequence"] == 1
            websocket.send_json(second)
            provisional = websocket.receive_json()
            final = websocket.receive_json()

    assert provisional["type"] == "provisional_result"
    assert provisional["sequence"] == 2
    assert final["type"] == "final_result"
    assert final["sequence"] == 2
