from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.common import ReportsPageOut
from services.report_pipeline import ReportsQueryService

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=ReportsPageOut)
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    patient_id: str | None = None,
    machine_id: str | None = None,
    suspicious_only: bool = False,
    flag_code: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: str = Query("test_date"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> ReportsPageOut:
    return ReportsPageOut(
        **ReportsQueryService.list_reports(
            db=db,
            page=page,
            page_size=page_size,
            search=search,
            patient_id=patient_id,
            machine_id=machine_id,
            suspicious_only=suspicious_only,
            flag_code=flag_code,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    )
