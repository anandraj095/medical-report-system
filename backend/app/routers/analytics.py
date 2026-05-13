from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.common import AnalyticsOut
from services.report_pipeline import AnalyticsService

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsOut)
def get_analytics(db: Session = Depends(get_db)) -> AnalyticsOut:
    return AnalyticsOut(**AnalyticsService.get_analytics(db))
