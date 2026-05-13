from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RejectedReport, Upload
from app.schemas.common import UploadDetailOut, UploadSummaryOut
from services.report_pipeline import UploadProcessingService
from utils.cbc_rules import REQUIRED_COLUMNS

router = APIRouter(tags=["uploads"])


@router.get("/upload/template")
def get_upload_template() -> dict:
    return {
        "required_columns": REQUIRED_COLUMNS,
        "example": {
            "patient_id": "P001",
            "patient_name": "Alice",
            "age": 32,
            "gender": "F",
            "hemoglobin": 13.2,
            "wbc": 7200,
            "platelets": 250000,
            "test_date": "2026-05-01",
            "machine_id": "M1",
        },
    }


@router.post("/upload", response_model=UploadSummaryOut)
async def upload_reports(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadSummaryOut:
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")

    summary = UploadProcessingService.process_upload(db=db, file=file, contents=contents)
    return UploadSummaryOut(**summary)


@router.get("/uploads/{upload_id}", response_model=UploadDetailOut)
def get_upload_details(upload_id: int, db: Session = Depends(get_db)) -> UploadDetailOut:
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")

    rejected_reports = (
        db.query(RejectedReport)
        .filter(RejectedReport.upload_id == upload_id)
        .order_by(RejectedReport.row_number.asc())
        .all()
    )

    return UploadDetailOut(
        upload_id=upload.id,
        filename=upload.filename,
        status=upload.status,
        created_at=upload.created_at,
        processed_at=upload.processed_at,
        summary=upload.summary_json,
        rejected_reports=rejected_reports,
    )
