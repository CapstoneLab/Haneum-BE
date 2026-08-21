from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.analysis import AnalysisService


async def get_analysis_service(db: Session = Depends(get_db)) -> AnalysisService:
    return AnalysisService(db, get_settings())
