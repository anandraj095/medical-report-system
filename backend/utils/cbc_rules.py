from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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

GENDER_MAP = {
    "m": "M",
    "male": "M",
    "f": "F",
    "female": "F",
}

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
)

REFERENCE_RANGES = {
    "hemoglobin": {"M": (13.0, 17.0), "F": (12.0, 15.0)},
    "wbc": (4000.0, 11000.0),
    "platelets": (150000.0, 450000.0),
    "age_reference_max": 100,
}

HARD_LIMITS = {
    "age_max": 120,
    "hemoglobin_max": 25.0,
    "wbc_max": 500000.0,
    "platelets_max": 5000000.0,
}


@dataclass
class RowValidationResult:
    normalized: dict[str, Any] | None
    errors: list[dict[str, str]]


@dataclass
class SuspiciousFlagInput:
    code: str
    severity: str
    message: str
    details: dict[str, Any]


def sha256_bytes(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def normalize_header(header: str) -> str:
    header = (header or "").strip().lower()
    header = re.sub(r"[^a-z0-9]+", "_", header)
    return header.strip("_")


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_row_keys(row: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[normalize_header(str(key))] = compact_whitespace(str(value)) if value is not None else ""
    return normalized


def parse_decimal(value: str, field_name: str, errors: list[dict[str, str]]) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(
            {
                "code": f"INVALID_{field_name.upper()}_FORMAT",
                "field": field_name,
                "message": f"'{field_name}' must be numeric.",
            }
        )
        return None


def parse_int_like(value: str, field_name: str, errors: list[dict[str, str]]) -> int | None:
    number = parse_decimal(value, field_name, errors)
    if number is None:
        return None
    if number != number.to_integral_value():
        errors.append(
            {
                "code": f"INVALID_{field_name.upper()}_FORMAT",
                "field": field_name,
                "message": f"'{field_name}' must be a whole number.",
            }
        )
        return None
    return int(number)


def parse_test_date(value: str, errors: list[dict[str, str]]) -> date | None:
    cleaned = compact_whitespace(value)
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
            if parsed > date.today():
                errors.append(
                    {
                        "code": "TEST_DATE_IN_FUTURE",
                        "field": "test_date",
                        "message": "'test_date' cannot be in the future.",
                    }
                )
                return None
            return parsed
        except ValueError:
            continue

    errors.append(
        {
            "code": "INVALID_TEST_DATE_FORMAT",
            "field": "test_date",
            "message": "'test_date' must match one of the supported date formats.",
        }
    )
    return None


def validate_and_normalize_row(raw_row: dict[str, Any], row_number: int) -> RowValidationResult:
    row = normalize_row_keys(raw_row)
    errors: list[dict[str, str]] = []

    for column in REQUIRED_COLUMNS:
        if compact_whitespace(row.get(column, "")) == "":
            errors.append(
                {
                    "code": "REQUIRED_FIELD_MISSING",
                    "field": column,
                    "message": f"Row {row_number}: '{column}' is required.",
                }
            )

    if errors:
        return RowValidationResult(normalized=None, errors=errors)

    patient_id = compact_whitespace(row["patient_id"]).upper()
    patient_name = compact_whitespace(row["patient_name"])
    machine_id = compact_whitespace(row["machine_id"]).upper()

    if len(patient_id) > 100:
        errors.append(
            {
                "code": "PATIENT_ID_TOO_LONG",
                "field": "patient_id",
                "message": "'patient_id' cannot exceed 100 characters.",
            }
        )

    if len(patient_name) > 255:
        errors.append(
            {
                "code": "PATIENT_NAME_TOO_LONG",
                "field": "patient_name",
                "message": "'patient_name' cannot exceed 255 characters.",
            }
        )

    if len(machine_id) > 100:
        errors.append(
            {
                "code": "MACHINE_ID_TOO_LONG",
                "field": "machine_id",
                "message": "'machine_id' cannot exceed 100 characters.",
            }
        )

    age = parse_int_like(row["age"], "age", errors)
    hemoglobin = parse_decimal(row["hemoglobin"], "hemoglobin", errors)
    wbc = parse_decimal(row["wbc"], "wbc", errors)
    platelets = parse_decimal(row["platelets"], "platelets", errors)
    test_date = parse_test_date(row["test_date"], errors)

    gender_input = compact_whitespace(row["gender"]).lower()
    gender = GENDER_MAP.get(gender_input)
    if gender is None:
        errors.append(
            {
                "code": "INVALID_GENDER",
                "field": "gender",
                "message": "'gender' must be one of: M, F, Male, Female.",
            }
        )

    if age is not None:
        if age < 0:
            errors.append(
                {
                    "code": "AGE_NEGATIVE",
                    "field": "age",
                    "message": "'age' cannot be negative.",
                }
            )
        elif age > HARD_LIMITS["age_max"]:
            errors.append(
                {
                    "code": "AGE_IMPOSSIBLE_HIGH",
                    "field": "age",
                    "message": f"'age' cannot exceed {HARD_LIMITS['age_max']}.",
                }
            )

    if hemoglobin is not None:
        if hemoglobin <= 0:
            errors.append(
                {
                    "code": "HEMOGLOBIN_NON_POSITIVE",
                    "field": "hemoglobin",
                    "message": "'hemoglobin' must be greater than 0.",
                }
            )
        elif hemoglobin > Decimal(str(HARD_LIMITS["hemoglobin_max"])):
            errors.append(
                {
                    "code": "HEMOGLOBIN_IMPOSSIBLE_HIGH",
                    "field": "hemoglobin",
                    "message": f"'hemoglobin' cannot exceed {HARD_LIMITS['hemoglobin_max']}.",
                }
            )

    if wbc is not None:
        if wbc <= 0:
            errors.append(
                {
                    "code": "WBC_NON_POSITIVE",
                    "field": "wbc",
                    "message": "'wbc' must be greater than 0.",
                }
            )
        elif wbc > Decimal(str(HARD_LIMITS["wbc_max"])):
            errors.append(
                {
                    "code": "WBC_IMPOSSIBLE_HIGH",
                    "field": "wbc",
                    "message": f"'wbc' cannot exceed {HARD_LIMITS['wbc_max']}.",
                }
            )

    if platelets is not None:
        if platelets <= 0:
            errors.append(
                {
                    "code": "PLATELETS_NON_POSITIVE",
                    "field": "platelets",
                    "message": "'platelets' must be greater than 0.",
                }
            )
        elif platelets > Decimal(str(HARD_LIMITS["platelets_max"])):
            errors.append(
                {
                    "code": "PLATELETS_IMPOSSIBLE_HIGH",
                    "field": "platelets",
                    "message": f"'platelets' cannot exceed {HARD_LIMITS['platelets_max']}.",
                }
            )

    if errors:
        return RowValidationResult(normalized=None, errors=errors)

    normalized = {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "age": age,
        "gender": gender,
        "hemoglobin": round(float(hemoglobin), 2),
        "wbc": round(float(wbc), 2),
        "platelets": round(float(platelets), 2),
        "test_date": test_date,
        "machine_id": machine_id,
    }
    return RowValidationResult(normalized=normalized, errors=[])


def serialize_normalized_row(normalized: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(normalized)
    if isinstance(serialized.get("test_date"), date):
        serialized["test_date"] = serialized["test_date"].isoformat()
    return serialized


def build_row_fingerprint(normalized: dict[str, Any]) -> str:
    fingerprint_source = "|".join(
        [
            str(normalized["patient_id"]),
            str(normalized["test_date"]),
            str(normalized["machine_id"]),
            f"{float(normalized['hemoglobin']):.2f}",
            f"{float(normalized['wbc']):.2f}",
            f"{float(normalized['platelets']):.2f}",
        ]
    )
    return hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()


def safe_percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)
