import asyncio
import hashlib
import json
import logging
import secrets
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import SessionLocal
from app.schemas.analysis import AnalyzeResponseData
from app.schemas.realtime import (
    RealtimeAnalysisEvent,
    RealtimeDraftMessage,
    RealtimeErrorEvent,
)
from app.services.analysis import AnalysisService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


async def _send_event(websocket: WebSocket, lock: asyncio.Lock, event: object) -> None:
    async with lock:
        await websocket.send_json(event.model_dump(mode="json"))


def _run_final_analysis(message: RealtimeDraftMessage) -> AnalyzeResponseData:
    """Keep the existing synchronous ORM work away from the WebSocket event loop."""

    async def run() -> AnalyzeResponseData:
        with SessionLocal() as db:
            return await AnalysisService(db, get_settings()).analyze(message.payload)

    return asyncio.run(run())


def _analysis_signature(message: RealtimeDraftMessage) -> str:
    """Hash analysis inputs while ignoring per-send metadata."""

    payload = message.payload.model_dump(
        mode="json",
        exclude={"request_id", "client_timestamp"},
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _for_request(result: AnalyzeResponseData, message: RealtimeDraftMessage) -> AnalyzeResponseData:
    """Reuse an analysis result with the request id of the latest equivalent draft."""

    return result.model_copy(update={"request_id": message.payload.request_id})


@router.websocket("/realtime")
async def realtime_analysis(websocket: WebSocket) -> None:
    settings = get_settings()
    supplied_key = websocket.headers.get("x-api-key")
    if supplied_key is None or not secrets.compare_digest(
        supplied_key, settings.android_api_key
    ):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    send_lock = asyncio.Lock()
    queue: asyncio.Queue[RealtimeDraftMessage] = asyncio.Queue(maxsize=1)
    latest: dict[str, int] = {}
    latest_message: dict[str, RealtimeDraftMessage] = {}
    latest_signature: dict[str, str] = {}
    provisional_cache: dict[str, tuple[str, AnalyzeResponseData]] = {}
    final_cache: dict[str, tuple[str, AnalyzeResponseData]] = {}

    async def send_error(
        code: str,
        message: str,
        *,
        session_id: str | None = None,
        sequence: int | None = None,
    ) -> None:
        await _send_event(
            websocket,
            send_lock,
            RealtimeErrorEvent(
                code=code,
                message=message,
                session_id=session_id,
                sequence=sequence,
            ),
        )

    async def final_worker() -> None:
        while True:
            message = await queue.get()
            try:
                result = await asyncio.to_thread(_run_final_analysis, message)
                signature = _analysis_signature(message)
                final_cache[message.session_id] = (signature, result)
                current = latest_message.get(message.session_id)
                if current is not None and latest_signature.get(message.session_id) == signature:
                    await _send_event(
                        websocket,
                        send_lock,
                        RealtimeAnalysisEvent(
                            type="final_result",
                            session_id=current.session_id,
                            sequence=current.sequence,
                            data=_for_request(result, current),
                        ),
                    )
            except ApiError as exc:
                await send_error(
                    exc.code,
                    exc.message,
                    session_id=message.session_id,
                    sequence=message.sequence,
                )
            except Exception:
                logger.exception("Realtime final analysis failed")
                await send_error(
                    "ANALYSIS_FAILED",
                    "Final analysis failed.",
                    session_id=message.session_id,
                    sequence=message.sequence,
                )
            finally:
                queue.task_done()

    worker = asyncio.create_task(final_worker())
    try:
        while True:
            try:
                message = RealtimeDraftMessage.model_validate(await websocket.receive_json())
            except (ValidationError, ValueError) as exc:
                await send_error("INVALID_REQUEST", str(exc))
                continue

            previous_sequence = latest.get(message.session_id, -1)
            if message.sequence <= previous_sequence:
                await send_error(
                    "STALE_SEQUENCE",
                    "The sequence must be newer than the last accepted draft.",
                    session_id=message.session_id,
                    sequence=message.sequence,
                )
                continue

            signature = _analysis_signature(message)
            cached_provisional = provisional_cache.get(message.session_id)
            if (
                latest_signature.get(message.session_id) == signature
                and cached_provisional is not None
                and cached_provisional[0] == signature
            ):
                latest[message.session_id] = message.sequence
                latest_message[message.session_id] = message
                await _send_event(
                    websocket,
                    send_lock,
                    RealtimeAnalysisEvent(
                        type="provisional_result",
                        session_id=message.session_id,
                        sequence=message.sequence,
                        data=_for_request(cached_provisional[1], message),
                    ),
                )

                cached_final = final_cache.get(message.session_id)
                if cached_final is not None and cached_final[0] == signature:
                    await _send_event(
                        websocket,
                        send_lock,
                        RealtimeAnalysisEvent(
                            type="final_result",
                            session_id=message.session_id,
                            sequence=message.sequence,
                            data=_for_request(cached_final[1], message),
                        ),
                    )
                continue

            try:
                with SessionLocal() as db:
                    provisional = AnalysisService(db, settings).analyze_provisional(
                        message.payload
                    )
            except ApiError as exc:
                await send_error(
                    exc.code,
                    exc.message,
                    session_id=message.session_id,
                    sequence=message.sequence,
                )
                continue

            latest[message.session_id] = message.sequence
            latest_message[message.session_id] = message
            latest_signature[message.session_id] = signature
            provisional_cache[message.session_id] = (signature, provisional)
            await _send_event(
                websocket,
                send_lock,
                RealtimeAnalysisEvent(
                    type="provisional_result",
                    session_id=message.session_id,
                    sequence=message.sequence,
                    data=provisional,
                ),
            )

            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                    queue.task_done()
            queue.put_nowait(message)
    except WebSocketDisconnect:
        pass
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
