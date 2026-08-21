from fastapi import APIRouter, Depends

from app.api.routes import actions, analysis, health, risk_logs, settings
from app.core.security import require_android_api_key

api_router = APIRouter(dependencies=[Depends(require_android_api_key)])
api_router.include_router(analysis.router)
api_router.include_router(actions.router)
api_router.include_router(health.router)
api_router.include_router(risk_logs.router)
api_router.include_router(settings.router)
