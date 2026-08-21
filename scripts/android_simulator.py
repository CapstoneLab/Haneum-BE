import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.analysis import ContextMessage, LlmAnalyzeRequest
from app.services.claude import ClaudeService
from app.services.llm import LlmServiceError
from app.services.masking import (
    ACCOUNT_CONTEXT_RE,
    ACCOUNT_RE,
    CARD_RE,
    OTP_CONTEXT_RE,
    OTP_RE,
    PHONE_RE,
    RESIDENT_ID_RE,
    mask_sensitive_text,
    mask_sensitive_texts,
)
from app.services.rules import URL_RE, analyze_rules
from app.services.scoring import calculate_score

LOCAL_SCORE_BY_TYPE = {
    "resident_id": 40,
    "card_number": 35,
    "account_number": 30,
    "verification_code": 30,
    "phone_number": 10,
    "suspicious_url": 10,
}


def detect_locally(text: str) -> tuple[list[str], int]:
    risk_types: list[str] = []

    def add_if(condition: bool, risk_type: str) -> None:
        if condition and risk_type not in risk_types:
            risk_types.append(risk_type)

    add_if(bool(RESIDENT_ID_RE.search(text)), "resident_id")
    add_if(bool(CARD_RE.search(text)), "card_number")
    add_if(bool(PHONE_RE.search(text)), "phone_number")
    add_if(bool(OTP_CONTEXT_RE.search(text) and OTP_RE.search(text)), "verification_code")
    add_if(
        bool(ACCOUNT_CONTEXT_RE.search(text) and ACCOUNT_RE.search(text)),
        "account_number",
    )
    add_if(bool(URL_RE.search(text)), "suspicious_url")

    score = min(sum(LOCAL_SCORE_BY_TYPE[item] for item in risk_types), 100)
    return risk_types, score


def build_payload(
    text: str,
    *,
    contexts: list[str],
    app_package: str,
) -> tuple[uuid.UUID, dict[str, Any]]:
    request_id = uuid.uuid4()
    risk_types, local_score = detect_locally(text)
    return request_id, {
        "request_id": str(request_id),
        "device_id": "terminal-android-simulator",
        "app_package": app_package,
        "input_text": text,
        "masked_text": mask_sensitive_text(text),
        "context_messages": [
            {"speaker": "other", "text": context} for context in contexts[-5:]
        ],
        "local_detection": {
            "detected": bool(risk_types),
            "risk_types": risk_types,
            "local_score": local_score,
        },
        "client_timestamp": datetime.now(UTC).isoformat(),
        "client_version": "terminal-simulator/0.1.0",
    }


def send_request(base_url: str, api_key: str, request_id: uuid.UUID, payload: dict) -> dict:
    if not api_key or api_key.startswith("replace-with"):
        raise RuntimeError("backend/.env의 ANDROID_API_KEY를 실제 테스트 값으로 변경하세요.")

    headers = {"X-API-Key": api_key, "X-Request-ID": str(request_id)}
    with httpx.Client(base_url=base_url.rstrip("/") + "/", timeout=15.0) as client:
        response = client.post("analyze", headers=headers, json=payload)
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"서버가 JSON이 아닌 응답을 반환했습니다. HTTP {response.status_code}"
        ) from exc
    if response.is_error:
        raise RuntimeError(
            f"분석 요청 실패: HTTP {response.status_code}\n"
            + json.dumps(body, ensure_ascii=False, indent=2)
        )
    return body


async def analyze_standalone(payload: dict[str, Any]) -> dict[str, Any]:
    contexts = [ContextMessage.model_validate(item) for item in payload["context_messages"]]
    rule_result = analyze_rules(payload["input_text"], contexts)
    masked_context_texts = mask_sensitive_texts([message.text for message in contexts])
    masked_contexts = [
        message.model_copy(update={"text": masked_text})
        for message, masked_text in zip(contexts, masked_context_texts, strict=True)
    ]

    llm_data = None
    llm_error = None
    try:
        llm_data = await ClaudeService(get_settings()).analyze(
            LlmAnalyzeRequest(
                request_id=uuid.UUID(payload["request_id"]),
                input_text=payload["masked_text"],
                context_messages=masked_contexts,
                local_risk_types=payload["local_detection"]["risk_types"],
                rule_risk_types=rule_result.risk_types,
            )
        )
    except LlmServiceError as exc:
        llm_error = exc.code

    risk_types = list(
        dict.fromkeys(
            payload["local_detection"]["risk_types"]
            + rule_result.risk_types
            + (llm_data.risk_types if llm_data else [])
        )
    )[:10]
    score_result = calculate_score(
        local_score=payload["local_detection"]["local_score"],
        rule_score=rule_result.score,
        llm_score=llm_data.risk_score if llm_data else None,
        llm_confidence=llm_data.confidence if llm_data else None,
        risk_types=risk_types,
    )
    reason = (
        llm_data.reason
        if llm_data
        else rule_result.reason
        if rule_result.risk_types
        else "감지된 위험 요소가 없습니다."
    )
    return {
        "request_id": payload["request_id"],
        "risk": {"score": score_result.score, "level": score_result.level.value},
        "detected": risk_types,
        "reason": reason,
        "action": score_result.recommended_action.value,
        "scores": {
            "local": payload["local_detection"]["local_score"],
            "rule": rule_result.score,
            "claude": llm_data.risk_score if llm_data else None,
            "claude_confidence": llm_data.confidence if llm_data else None,
        },
        "claude_used": llm_data is not None,
        "fallback_used": llm_data is None,
        "fallback_reason": llm_error,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Android IME 분석 요청 터미널 시뮬레이터")
    parser.add_argument("--text", help="사용자가 입력하려는 문장. 생략하면 터미널에서 입력합니다.")
    parser.add_argument(
        "--context",
        action="append",
        default=[],
        help="최근 상대방 메시지. 최대 5회 반복할 수 있습니다.",
    )
    parser.add_argument("--app-package", default="com.kakao.talk")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--dry-run", action="store_true", help="HTTP 호출 없이 요청 JSON만 출력")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="FastAPI·PostgreSQL 없이 로컬 규칙과 Claude를 직접 실행",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = args.text or input("전송하려는 문장을 입력하세요: ").strip()
    if not text:
        print("입력 문장이 비어 있습니다.", file=sys.stderr)
        return 2

    request_id, payload = build_payload(
        text,
        contexts=args.context,
        app_package=args.app_package,
    )
    print("\n[Android 로컬 탐지 결과]")
    print(json.dumps(payload["local_detection"], ensure_ascii=False, indent=2))
    print("\n[서버 전송 payload]")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    if args.standalone:
        print("\n[Standalone 분석 결과]")
        print(json.dumps(asyncio.run(analyze_standalone(payload)), ensure_ascii=False, indent=2))
        return 0

    try:
        result = send_request(
            args.base_url,
            get_settings().android_api_key,
            request_id,
            payload,
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"\n[오류]\n{exc}", file=sys.stderr)
        return 1

    print("\n[FastAPI 분석 결과]")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
