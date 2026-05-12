import csv
import io
from typing import Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cbc_report import CBCReport

router = APIRouter(prefix="/cbc", tags=["CBC Upload"])

REQUIRED_COLUMNS = [
    "patient_id",
    "patient_name",
    "age",
    "gender",
    "hemoglobin",
    "wbc",
    "platelets",
    "test_date",
    "machine_id",
]


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def normalize_row_keys(row: Dict[str, str]) -> Dict[str, str]:
    normalized = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[normalize_header(key)] = value.strip() if isinstance(value, str) else value
    return normalized


def parse_int(value: str, field_name: str, row_number: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Row {row_number}: '{field_name}' must be a valid integer.",
        )


def parse_float(value: str, field_name: str, row_number: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Row {row_number}: '{field_name}' must be a valid number.",
        )


@router.get("/template")
def cbc_template():
    return {
        "required_columns": REQUIRED_COLUMNS,
        "example": {
            "patient_id": "P001",
            "patient_name": "John Doe",
            "age": 35,
            "gender": "Male",
            "hemoglobin": 13.6,
            "wbc": 5600,
            "platelets": 250000,
            "test_date": "2026-05-12",
            "machine_id": "MACHINE-01",
        },
    }


@router.post("/upload-csv")
async def upload_cbc_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")

    try:
        decoded = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="CSV must be UTF-8 encoded.",
        )

    csv_reader = csv.DictReader(io.StringIO(decoded))
    if not csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV header row is missing.")

    normalized_headers = [normalize_header(header) for header in csv_reader.fieldnames if header]
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in normalized_headers]
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing_columns)}",
        )

    records = []
    for row_number, row in enumerate(csv_reader, start=2):
        normalized_row = normalize_row_keys(row)
        if not any(normalized_row.values()):
            continue

        for column in REQUIRED_COLUMNS:
            value = normalized_row.get(column)
            if value in (None, ""):
                raise HTTPException(
                    status_code=400,
                    detail=f"Row {row_number}: '{column}' cannot be empty.",
                )

        record = CBCReport(
            patient_id=normalized_row["patient_id"],
            patient_name=normalized_row["patient_name"],
            age=parse_int(normalized_row["age"], "age", row_number),
            gender=normalized_row["gender"],
            hemoglobin=parse_float(normalized_row["hemoglobin"], "hemoglobin", row_number),
            wbc=parse_float(normalized_row["wbc"], "wbc", row_number),
            platelets=parse_float(normalized_row["platelets"], "platelets", row_number),
            test_date=normalized_row["test_date"],
            machine_id=normalized_row["machine_id"],
        )
        records.append(record)

    if not records:
        raise HTTPException(status_code=400, detail="CSV has no valid data rows.")

    try:
        db.add_all(records)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    return {
        "message": "CBC reports uploaded successfully.",
        "inserted_rows": len(records),
    }
