import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.health import BackendHealth, DependencyHealth, HealthResponseData
from app.services.llm import create_llm_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthResponseData])
async def health(
    db: Session = Depends(get_db),
) -> ApiResponse[HealthResponseData]:
    settings = get_settings()
    db_started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        db_ms = round((time.perf_counter() - db_started) * 1000)
    except SQLAlchemyError:
        db.rollback()
        db_ok = False
        db_ms = None

    llm_ok, llm_ms = await create_llm_client(settings).health()
    if not db_ok:
        overall = "down"
    elif not llm_ok:
        overall = "degraded"
    else:
        overall = "ok"

    return ApiResponse(
        data=HealthResponseData(
            status=overall,
            backend=BackendHealth(),
            database=DependencyHealth(status="up" if db_ok else "down", response_time_ms=db_ms),
            llm=DependencyHealth(status="up" if llm_ok else "down", response_time_ms=llm_ms),
            version=settings.app_version,
            timestamp=datetime.now(UTC),
        )
    )
