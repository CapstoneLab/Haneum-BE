import argparse
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

from websockets.asyncio.client import connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the realtime analysis WebSocket.")
    parser.add_argument("--url", default="ws://127.0.0.1:8000/api/v1/realtime")
    parser.add_argument("--api-key", default=os.getenv("ANDROID_API_KEY"))
    return parser.parse_args()


async def run(url: str, api_key: str) -> None:
    request_id = str(uuid.uuid4())
    message = {
        "type": "draft_changed",
        "session_id": f"smoke-{uuid.uuid4()}",
        "sequence": 1,
        "payload": {
            "request_id": request_id,
            "device_id": "realtime-smoke-test",
            "app_package": "com.example.test",
            "input_text": "verification code requested urgently",
            "masked_text": "verification code requested urgently",
            "context_messages": [],
            "local_detection": {
                "detected": True,
                "risk_types": ["verification_code", "urgency"],
                "local_score": 80,
            },
            "client_timestamp": datetime.now(UTC).isoformat(),
            "client_version": "smoke-test",
        },
    }

    async with connect(url, additional_headers={"X-API-Key": api_key}) as websocket:
        started = asyncio.get_running_loop().time()
        await websocket.send(json.dumps(message))
        provisional = json.loads(await websocket.recv())
        provisional_ms = round((asyncio.get_running_loop().time() - started) * 1000)
        final = json.loads(await websocket.recv())
        final_ms = round((asyncio.get_running_loop().time() - started) * 1000)

    if provisional.get("type") != "provisional_result":
        raise RuntimeError(f"Expected provisional_result, received: {provisional}")
    if final.get("type") != "final_result":
        raise RuntimeError(f"Expected final_result, received: {final}")
    if provisional.get("sequence") != 1 or final.get("sequence") != 1:
        raise RuntimeError("The response sequence did not match the request.")

    print(
        json.dumps(
            {
                "provisional_ms": provisional_ms,
                "final_ms": final_ms,
                "provisional_risk_level": provisional["data"]["risk_level"],
                "final_risk_level": final["data"]["risk_level"],
                "llm_used": final["data"]["analysis_source"]["llm_used"],
                "fallback_used": final["data"]["analysis_source"]["fallback_used"],
            },
            indent=2,
        )
    )


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit("Set ANDROID_API_KEY or pass --api-key.")
    asyncio.run(run(args.url, args.api_key))


if __name__ == "__main__":
    main()
