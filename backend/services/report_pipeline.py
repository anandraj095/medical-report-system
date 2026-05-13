from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime
from math import ceil
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from app.models import CBCReport, RawReportRow, RejectedReport, SuspiciousFlag, Upload
from utils.cbc_rules import (
    REFERENCE_RANGES,
    REQUIRED_COLUMNS,
    build_row_fingerprint,
    normalize_header,
    safe_percent,
    serialize_normalized_row,
    sha256_bytes,
    validate_and_normalize_row,
)


class UploadProcessingService:
    @staticmethod
    def create_upload_stub(db: Session, file: UploadFile, contents: bytes) -> Upload:
        upload = Upload(
            filename=file.filename or "uploaded.csv",
            content_type=file.content_type,
            file_size_bytes=len(contents),
            status="RECEIVED",
        )
        db.add(upload)
        db.commit()
        db.refresh(upload)
        return upload

    @staticmethod
    def fail_upload(db: Session, upload: Upload, message: str, status_code: int = 400) -> None:
        upload.status = "FAILED"
        upload.summary_json = {"message": message}
        upload.processed_at = datetime.utcnow()
        db.add(upload)
        db.commit()
        raise HTTPException(status_code=status_code, detail={"upload_id": upload.id, "message": message})

    @staticmethod
    def process_upload(db: Session, file: UploadFile, contents: bytes) -> dict[str, Any]:
        upload = UploadProcessingService.create_upload_stub(db, file, contents)

        file_hash = sha256_bytes(contents)
        upload.file_hash = file_hash
        db.add(upload)
        db.commit()
        db.refresh(upload)

        duplicate_upload = (
            db.query(Upload)
            .filter(Upload.file_hash == file_hash, Upload.id != upload.id)
            .order_by(Upload.id.asc())
            .first()
        )
        if duplicate_upload:
            upload.status = "DUPLICATE"
            upload.duplicate_of_upload_id = duplicate_upload.id
            upload.summary_json = {
                "message": "Duplicate file upload skipped because the same file hash already exists.",
                "duplicate_of_upload_id": duplicate_upload.id,
            }
            upload.processed_at = datetime.utcnow()
            db.add(upload)
            db.commit()
            return UploadProcessingService.build_summary_response(upload, duplicate=True)

        try:
            decoded = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            UploadProcessingService.fail_upload(db, upload, "CSV must be UTF-8 encoded.")

        csv_reader = csv.DictReader(io.StringIO(decoded))
        if not csv_reader.fieldnames:
            UploadProcessingService.fail_upload(db, upload, "CSV header row is missing.")

        original_headers = [header for header in (csv_reader.fieldnames or []) if header is not None]
        normalized_headers = [normalize_header(header) for header in original_headers]
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in normalized_headers]
        if missing_columns:
            UploadProcessingService.fail_upload(
                db,
                upload,
                f"Missing required columns: {', '.join(missing_columns)}",
            )

        upload.original_headers = original_headers
        db.add(upload)
        db.commit()
        db.refresh(upload)

        parsed_rows: list[dict[str, Any]] = []
        raw_models: list[RawReportRow] = []
        for row_number, row in enumerate(csv_reader, start=2):
            cleaned_raw = {
                key: (str(value).strip() if value is not None else "")
                for key, value in row.items()
                if key is not None
            }
            if not any(str(value).strip() for value in cleaned_raw.values()):
                continue
            parsed_rows.append({"row_number": row_number, "raw_data": cleaned_raw})
            raw_models.append(
                RawReportRow(
                    upload_id=upload.id,
                    row_number=row_number,
                    raw_data=cleaned_raw,
                    validation_status="PENDING",
                )
            )

        upload.total_rows = len(parsed_rows)
        upload.raw_rows_stored = len(parsed_rows)
        db.add(upload)
        db.add_all(raw_models)
        db.commit()

        if not parsed_rows:
            UploadProcessingService.fail_upload(db, upload, "CSV has no data rows.")

        db.refresh(upload)
        raw_models = (
            db.query(RawReportRow)
            .filter(RawReportRow.upload_id == upload.id)
            .order_by(RawReportRow.row_number.asc())
            .all()
        )

        valid_candidates: list[tuple[RawReportRow, dict[str, Any]]] = []
        rejected_counter: Counter[str] = Counter()
        rejected_rows_count = 0

        for raw_model, parsed in zip(raw_models, parsed_rows):
            result = validate_and_normalize_row(parsed["raw_data"], parsed["row_number"])
            if result.errors:
                raw_model.validation_status = "REJECTED"
                raw_model.rejection_reason_codes = [error["code"] for error in result.errors]
                db.add(
                    RejectedReport(
                        upload_id=upload.id,
                        raw_row_id=raw_model.id,
                        row_number=parsed["row_number"],
                        raw_data=parsed["raw_data"],
                        normalized_data=None,
                        reason_codes=[error["code"] for error in result.errors],
                        reason_details=result.errors,
                    )
                )
                rejected_counter.update(error["code"] for error in result.errors)
                rejected_rows_count += 1
                continue

            raw_model.validation_status = "VALID"
            raw_model.normalized_data = serialize_normalized_row(result.normalized or {})
            valid_candidates.append((raw_model, result.normalized or {}))

        db.commit()

        dedupe_counter = 0
        seen_fingerprints: set[str] = set()
        candidate_fingerprints = [build_row_fingerprint(normalized) for _, normalized in valid_candidates]
        existing_fingerprints = {
            value
            for (value,) in db.query(CBCReport.row_fingerprint)
            .filter(CBCReport.row_fingerprint.in_(candidate_fingerprints))
            .all()
        }

        reports_to_insert: list[CBCReport] = []
        for raw_model, normalized in valid_candidates:
            row_fingerprint = build_row_fingerprint(normalized)
            if row_fingerprint in seen_fingerprints or row_fingerprint in existing_fingerprints:
                raw_model.validation_status = "DEDUPLICATED"
                raw_model.rejection_reason_codes = ["EXACT_DUPLICATE_ROW"]
                dedupe_counter += 1
                continue

            seen_fingerprints.add(row_fingerprint)
            reports_to_insert.append(
                CBCReport(
                    upload_id=upload.id,
                    source_row_id=raw_model.id,
                    row_fingerprint=row_fingerprint,
                    patient_id=normalized["patient_id"],
                    patient_name=normalized["patient_name"],
                    age=normalized["age"],
                    gender=normalized["gender"],
                    hemoglobin=normalized["hemoglobin"],
                    wbc=normalized["wbc"],
                    platelets=normalized["platelets"],
                    test_date=normalized["test_date"],
                    machine_id=normalized["machine_id"],
                )
            )

        if reports_to_insert:
            db.add_all(reports_to_insert)
            db.commit()
            for report in reports_to_insert:
                db.refresh(report)
        else:
            db.commit()

        flag_counter = UploadProcessingService.run_suspicious_detection(
            db=db,
            upload_id=upload.id,
            inserted_reports=reports_to_insert,
        )

        upload.accepted_rows = len(reports_to_insert)
        upload.rejected_rows = rejected_rows_count
        upload.deduplicated_rows = dedupe_counter
        upload.suspicious_reports_count = len({report_id for report_id, _ in flag_counter.keys()})
        upload.status = "PROCESSED_WITH_ERRORS" if upload.rejected_rows or upload.deduplicated_rows else "PROCESSED"
        upload.processed_at = datetime.utcnow()
        upload.summary_json = {
            "message": "Upload processed successfully.",
            "rejected_breakdown": dict(rejected_counter),
            "flags_breakdown": UploadProcessingService.flatten_flag_counter(flag_counter),
        }
        db.add(upload)
        db.commit()
        db.refresh(upload)

        return UploadProcessingService.build_summary_response(upload)

    @staticmethod
    def flatten_flag_counter(flag_counter: Counter[tuple[int, str]]) -> dict[str, int]:
        flattened: Counter[str] = Counter()
        for (_, code), count in flag_counter.items():
            flattened[code] += count
        return dict(flattened)

    @staticmethod
    def create_flag(
        db: Session,
        upload_id: int,
        report: CBCReport,
        code: str,
        severity: str,
        message: str,
        details: dict[str, Any],
        flag_counter: Counter[tuple[int, str]],
        created_keys: set[tuple[int, str, str]],
    ) -> None:
        key = (report.id, code, message)
        if key in created_keys:
            return
        created_keys.add(key)
        db.add(
            SuspiciousFlag(
                upload_id=upload_id,
                report_id=report.id,
                code=code,
                severity=severity,
                message=message,
                details=details,
            )
        )
        flag_counter[(report.id, code)] += 1

    @staticmethod
    def run_suspicious_detection(db: Session, upload_id: int, inserted_reports: list[CBCReport]) -> Counter[tuple[int, str]]:
        flag_counter: Counter[tuple[int, str]] = Counter()
        created_keys: set[tuple[int, str, str]] = set()

        for report in inserted_reports:
            hb_low, hb_high = REFERENCE_RANGES["hemoglobin"][report.gender]
            if report.hemoglobin < hb_low:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "ABNORMAL_HEMOGLOBIN_LOW",
                    "high",
                    f"Hemoglobin {report.hemoglobin} is below the {report.gender}-specific reference range.",
                    {"reference_min": hb_low, "reference_max": hb_high},
                    flag_counter,
                    created_keys,
                )
            elif report.hemoglobin > hb_high:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "ABNORMAL_HEMOGLOBIN_HIGH",
                    "medium",
                    f"Hemoglobin {report.hemoglobin} is above the {report.gender}-specific reference range.",
                    {"reference_min": hb_low, "reference_max": hb_high},
                    flag_counter,
                    created_keys,
                )

            wbc_low, wbc_high = REFERENCE_RANGES["wbc"]
            if report.wbc < wbc_low:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "ABNORMAL_WBC_LOW",
                    "medium",
                    f"WBC {report.wbc} is below the reference range.",
                    {"reference_min": wbc_low, "reference_max": wbc_high},
                    flag_counter,
                    created_keys,
                )
            elif report.wbc > wbc_high:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "ABNORMAL_WBC_HIGH",
                    "high",
                    f"WBC {report.wbc} is above the reference range.",
                    {"reference_min": wbc_low, "reference_max": wbc_high},
                    flag_counter,
                    created_keys,
                )

            platelet_low, platelet_high = REFERENCE_RANGES["platelets"]
            if report.platelets < platelet_low:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "ABNORMAL_PLATELETS_LOW",
                    "high",
                    f"Platelets {report.platelets} are below the reference range.",
                    {"reference_min": platelet_low, "reference_max": platelet_high},
                    flag_counter,
                    created_keys,
                )
            elif report.platelets > platelet_high:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "ABNORMAL_PLATELETS_HIGH",
                    "medium",
                    f"Platelets {report.platelets} are above the reference range.",
                    {"reference_min": platelet_low, "reference_max": platelet_high},
                    flag_counter,
                    created_keys,
                )

            if report.age > REFERENCE_RANGES["age_reference_max"]:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "AGE_OUTSIDE_REFERENCE_RANGE",
                    "low",
                    f"Age {report.age} is above the default CBC reference guidance range.",
                    {"reference_max": REFERENCE_RANGES["age_reference_max"]},
                    flag_counter,
                    created_keys,
                )

        grouped_pairs = {(report.patient_id, report.test_date) for report in inserted_reports}
        if grouped_pairs:
            pair_filters = [
                and_(CBCReport.patient_id == patient_id, CBCReport.test_date == test_date)
                for patient_id, test_date in grouped_pairs
            ]
            same_day_reports = db.query(CBCReport).filter(or_(*pair_filters)).all()
            grouped_reports: dict[tuple[str, Any], list[CBCReport]] = defaultdict(list)
            for report in same_day_reports:
                grouped_reports[(report.patient_id, report.test_date)].append(report)

            for group in grouped_reports.values():
                for index, left_report in enumerate(group):
                    for right_report in group[index + 1 :]:
                        if left_report.machine_id == right_report.machine_id:
                            continue
                        hb_delta = abs(left_report.hemoglobin - right_report.hemoglobin)
                        wbc_delta = abs(left_report.wbc - right_report.wbc)
                        platelets_delta = abs(left_report.platelets - right_report.platelets)
                        wbc_relative = wbc_delta / max(min(left_report.wbc, right_report.wbc), 1)
                        platelets_relative = platelets_delta / max(min(left_report.platelets, right_report.platelets), 1)

                        if not (
                            hb_delta >= 2.0
                            or wbc_delta >= 3000
                            or wbc_relative >= 0.30
                            or platelets_delta >= 50000
                            or platelets_relative >= 0.30
                        ):
                            continue

                        message = (
                            f"Same-day results conflict across machines {left_report.machine_id} and {right_report.machine_id}."
                        )
                        details = {
                            "compared_report_id": right_report.id,
                            "hb_delta": round(hb_delta, 2),
                            "wbc_delta": round(wbc_delta, 2),
                            "platelets_delta": round(platelets_delta, 2),
                        }
                        UploadProcessingService.create_flag(
                            db,
                            upload_id,
                            left_report,
                            "CONFLICTING_SAME_DAY_RESULT",
                            "high",
                            message,
                            details,
                            flag_counter,
                            created_keys,
                        )
                        details_for_right = {
                            "compared_report_id": left_report.id,
                            "hb_delta": round(hb_delta, 2),
                            "wbc_delta": round(wbc_delta, 2),
                            "platelets_delta": round(platelets_delta, 2),
                        }
                        UploadProcessingService.create_flag(
                            db,
                            upload_id,
                            right_report,
                            "CONFLICTING_SAME_DAY_RESULT",
                            "high",
                            message,
                            details_for_right,
                            flag_counter,
                            created_keys,
                        )

        for report in inserted_reports:
            previous_report = (
                db.query(CBCReport)
                .filter(CBCReport.patient_id == report.patient_id, CBCReport.test_date < report.test_date)
                .order_by(CBCReport.test_date.desc(), CBCReport.id.desc())
                .first()
            )
            if not previous_report:
                continue

            hb_delta = abs(report.hemoglobin - previous_report.hemoglobin)
            if hb_delta >= 2.5:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "SUDDEN_CHANGE_HEMOGLOBIN",
                    "high",
                    f"Hemoglobin changed by {hb_delta:.2f} since the previous result.",
                    {"previous_report_id": previous_report.id, "delta": round(hb_delta, 2)},
                    flag_counter,
                    created_keys,
                )

            wbc_delta = abs(report.wbc - previous_report.wbc)
            if wbc_delta >= 3000 and (wbc_delta / max(previous_report.wbc, 1)) >= 0.50:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "SUDDEN_CHANGE_WBC",
                    "high",
                    f"WBC changed by {wbc_delta:.2f} since the previous result.",
                    {"previous_report_id": previous_report.id, "delta": round(wbc_delta, 2)},
                    flag_counter,
                    created_keys,
                )

            platelets_delta = abs(report.platelets - previous_report.platelets)
            if platelets_delta >= 75000 and (platelets_delta / max(previous_report.platelets, 1)) >= 0.50:
                UploadProcessingService.create_flag(
                    db,
                    upload_id,
                    report,
                    "SUDDEN_CHANGE_PLATELETS",
                    "high",
                    f"Platelets changed by {platelets_delta:.2f} since the previous result.",
                    {"previous_report_id": previous_report.id, "delta": round(platelets_delta, 2)},
                    flag_counter,
                    created_keys,
                )

        db.commit()
        return flag_counter

    @staticmethod
    def build_summary_response(upload: Upload, duplicate: bool = False) -> dict[str, Any]:
        summary_json = upload.summary_json or {}
        return {
            "upload_id": upload.id,
            "file_name": upload.filename,
            "file_hash": upload.file_hash,
            "status": upload.status,
            "duplicate": duplicate,
            "duplicate_of_upload_id": upload.duplicate_of_upload_id,
            "total_rows": upload.total_rows,
            "raw_rows_stored": upload.raw_rows_stored,
            "accepted_rows": upload.accepted_rows,
            "rejected_rows": upload.rejected_rows,
            "deduplicated_rows": upload.deduplicated_rows,
            "suspicious_reports_count": upload.suspicious_reports_count,
            "rejected_breakdown": summary_json.get("rejected_breakdown", {}),
            "flags_breakdown": summary_json.get("flags_breakdown", {}),
            "message": summary_json.get("message", "Upload processed."),
        }


class ReportsQueryService:
    ALLOWED_SORT_FIELDS = {
        "id": CBCReport.id,
        "patient_id": CBCReport.patient_id,
        "patient_name": CBCReport.patient_name,
        "age": CBCReport.age,
        "hemoglobin": CBCReport.hemoglobin,
        "wbc": CBCReport.wbc,
        "platelets": CBCReport.platelets,
        "test_date": CBCReport.test_date,
        "machine_id": CBCReport.machine_id,
        "created_at": CBCReport.created_at,
    }

    @staticmethod
    def list_reports(
        db: Session,
        page: int,
        page_size: int,
        search: str | None,
        patient_id: str | None,
        machine_id: str | None,
        suspicious_only: bool,
        flag_code: str | None,
        date_from: Any | None,
        date_to: Any | None,
        sort_by: str,
        sort_order: str,
    ) -> dict[str, Any]:
        query = db.query(CBCReport).options(selectinload(CBCReport.flags))

        if suspicious_only or flag_code:
            query = query.join(SuspiciousFlag, SuspiciousFlag.report_id == CBCReport.id)

        if search:
            like_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    CBCReport.patient_id.ilike(like_term),
                    CBCReport.patient_name.ilike(like_term),
                    CBCReport.machine_id.ilike(like_term),
                )
            )
        if patient_id:
            query = query.filter(CBCReport.patient_id == patient_id.strip().upper())
        if machine_id:
            query = query.filter(CBCReport.machine_id == machine_id.strip().upper())
        if flag_code:
            query = query.filter(SuspiciousFlag.code == flag_code)
        if date_from:
            query = query.filter(CBCReport.test_date >= date_from)
        if date_to:
            query = query.filter(CBCReport.test_date <= date_to)

        total = query.distinct(CBCReport.id).count() if (suspicious_only or flag_code) else query.count()

        sort_column = ReportsQueryService.ALLOWED_SORT_FIELDS.get(sort_by, CBCReport.test_date)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_column.asc(), CBCReport.id.asc())
        else:
            query = query.order_by(sort_column.desc(), CBCReport.id.desc())

        if suspicious_only or flag_code:
            query = query.distinct(CBCReport.id)

        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
            "items": items,
        }


class AnalyticsService:
    @staticmethod
    def get_analytics(db: Session) -> dict[str, Any]:
        total_uploads = db.query(func.count(Upload.id)).scalar() or 0
        processed_uploads = (
            db.query(func.count(Upload.id))
            .filter(Upload.status.in_(["PROCESSED", "PROCESSED_WITH_ERRORS"]))
            .scalar()
            or 0
        )
        failed_uploads = db.query(func.count(Upload.id)).filter(Upload.status == "FAILED").scalar() or 0
        duplicate_uploads = db.query(func.count(Upload.id)).filter(Upload.status == "DUPLICATE").scalar() or 0

        total_reports = db.query(func.count(CBCReport.id)).scalar() or 0
        suspicious_reports = db.query(func.count(func.distinct(SuspiciousFlag.report_id))).scalar() or 0
        abnormal_reports = (
            db.query(func.count(func.distinct(SuspiciousFlag.report_id)))
            .filter(SuspiciousFlag.code.like("ABNORMAL_%"))
            .scalar()
            or 0
        )
        conflict_reports = (
            db.query(func.count(func.distinct(SuspiciousFlag.report_id)))
            .filter(SuspiciousFlag.code == "CONFLICTING_SAME_DAY_RESULT")
            .scalar()
            or 0
        )
        sudden_change_reports = (
            db.query(func.count(func.distinct(SuspiciousFlag.report_id)))
            .filter(SuspiciousFlag.code.like("SUDDEN_CHANGE_%"))
            .scalar()
            or 0
        )
        total_rejected_rows = db.query(func.coalesce(func.sum(Upload.rejected_rows), 0)).scalar() or 0
        total_deduplicated_rows = db.query(func.coalesce(func.sum(Upload.deduplicated_rows), 0)).scalar() or 0

        flag_codes = [code for (code,) in db.query(SuspiciousFlag.code).all()]
        top_abnormality_reasons = [
            {"reason": reason, "count": count}
            for reason, count in Counter(flag_codes).most_common(10)
        ]

        rejection_codes: list[str] = []
        for rejected in db.query(RejectedReport.reason_codes).all():
            reason_codes = rejected[0] or []
            rejection_codes.extend(reason_codes)
        top_rejection_reasons = [
            {"reason": reason, "count": count}
            for reason, count in Counter(rejection_codes).most_common(10)
        ]

        return {
            "total_uploads": total_uploads,
            "processed_uploads": processed_uploads,
            "failed_uploads": failed_uploads,
            "duplicate_uploads": duplicate_uploads,
            "upload_success_ratio_percent": safe_percent(processed_uploads, total_uploads),
            "total_reports": total_reports,
            "suspicious_reports": suspicious_reports,
            "abnormal_reports": abnormal_reports,
            "conflict_reports": conflict_reports,
            "sudden_change_reports": sudden_change_reports,
            "total_rejected_rows": int(total_rejected_rows),
            "total_deduplicated_rows": int(total_deduplicated_rows),
            "top_abnormality_reasons": top_abnormality_reasons,
            "top_rejection_reasons": top_rejection_reasons,
        }
