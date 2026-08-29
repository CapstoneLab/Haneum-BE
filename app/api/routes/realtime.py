import asyncio
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
                if latest.get(message.session_id) == message.sequence:
                    await _send_event(
                        websocket,
                        send_lock,
                        RealtimeAnalysisEvent(
                            type="final_result",
                            session_id=message.session_id,
                            sequence=message.sequence,
                            data=result,
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
