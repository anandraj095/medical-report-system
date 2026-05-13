from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    severity: str
    message: str
    details: dict[str, Any] | None = None
    created_at: datetime


class UploadSummaryOut(BaseModel):
    upload_id: int
    file_name: str
    file_hash: str | None = None
    status: str
    duplicate: bool = False
    duplicate_of_upload_id: int | None = None
    total_rows: int
    raw_rows_stored: int
    accepted_rows: int
    rejected_rows: int
    deduplicated_rows: int
    suspicious_reports_count: int
    rejected_breakdown: dict[str, int]
    flags_breakdown: dict[str, int]
    message: str


class RejectedReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    row_number: int
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any] | None = None
    reason_codes: list[str]
    reason_details: list[dict[str, Any]]
    created_at: datetime


class UploadDetailOut(BaseModel):
    upload_id: int
    filename: str
    status: str
    created_at: datetime
    processed_at: datetime | None
    summary: dict[str, Any] | None = None
    rejected_reports: list[RejectedReportOut]


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    upload_id: int
    patient_id: str
    patient_name: str
    age: int
    gender: str
    hemoglobin: float
    wbc: float
    platelets: float
    test_date: date
    machine_id: str
    created_at: datetime
    flags: list[FlagOut] = []


class ReportsPageOut(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    items: list[ReportOut]


class AnalyticsOut(BaseModel):
    total_uploads: int
    processed_uploads: int
    failed_uploads: int
    duplicate_uploads: int
    upload_success_ratio_percent: float
    total_reports: int
    suspicious_reports: int
    abnormal_reports: int
    conflict_reports: int
    sudden_change_reports: int
    total_rejected_rows: int
    total_deduplicated_rows: int
    top_abnormality_reasons: list[dict[str, Any]]
    top_rejection_reasons: list[dict[str, Any]]
