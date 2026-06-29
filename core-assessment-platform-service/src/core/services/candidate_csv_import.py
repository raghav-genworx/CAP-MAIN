"""Pure parsing and validation for recruiter candidate CSV uploads."""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass
from io import StringIO

from core.exceptions.assessment import AssessmentValidationError
from schemas.assessments import CandidateImportRowError

CANDIDATE_REQUIRED_HEADERS = frozenset({"name", "email"})
MAX_CANDIDATE_IMPORT_ROWS = 5_000
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CONTROL_CHARACTERS = frozenset({"\x00", "\r", "\n", "\t"})


@dataclass(frozen=True)
class CandidateImportRow:
    """One validated candidate row ready for persistence."""

    row_number: int
    name: str
    email: str
    external_id: str


@dataclass(frozen=True)
class CandidateCSVParseResult:
    """Validated rows and recruiter-readable row errors."""

    total_rows: int
    valid_rows: list[CandidateImportRow]
    errors: list[CandidateImportRowError]


def parse_candidate_csv(
    csv_text: str,
    *,
    existing_emails: set[str] | None = None,
) -> CandidateCSVParseResult:
    """Parse candidate CSV text without mutating persistence state."""

    normalized_existing_emails = {
        email.strip().lower() for email in (existing_emails or set())
    }
    try:
        reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")), strict=True)
        header_map = _header_map(reader.fieldnames)
        return _parse_rows(reader, header_map, normalized_existing_emails)
    except csv.Error as exc:
        raise AssessmentValidationError(f"CSV is malformed: {exc}") from exc


def _header_map(fieldnames: Sequence[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise AssessmentValidationError("CSV file does not contain a header row.")

    normalized_headers = [
        header.strip().lower() for header in fieldnames if header and header.strip()
    ]
    duplicate_headers = sorted(
        {
            header
            for header in normalized_headers
            if normalized_headers.count(header) > 1
        }
    )
    if duplicate_headers:
        raise AssessmentValidationError(
            "CSV contains duplicate column(s): " + ", ".join(duplicate_headers)
        )

    header_map = {
        header.strip().lower(): header
        for header in fieldnames
        if header and header.strip()
    }
    missing_headers = sorted(CANDIDATE_REQUIRED_HEADERS - set(header_map))
    if missing_headers:
        raise AssessmentValidationError(
            "CSV is missing required column(s): " + ", ".join(missing_headers)
        )
    return header_map


def _parse_rows(
    reader: csv.DictReader[str],
    header_map: dict[str, str],
    existing_emails: set[str],
) -> CandidateCSVParseResult:
    seen_upload_emails: set[str] = set()
    valid_rows: list[CandidateImportRow] = []
    errors: list[CandidateImportRowError] = []
    total_rows = 0

    for row_number, row in enumerate(reader, start=2):
        if _row_is_empty(row):
            continue
        total_rows += 1
        if total_rows > MAX_CANDIDATE_IMPORT_ROWS:
            raise AssessmentValidationError(
                f"CSV cannot contain more than {MAX_CANDIDATE_IMPORT_ROWS} candidates."
            )

        name = _csv_value(row, header_map, "name")
        email = _csv_value(row, header_map, "email").lower()
        external_id = _csv_value(row, header_map, "external_id")
        row_errors = _row_errors(
            row=row,
            name=name,
            email=email,
            external_id=external_id,
            seen_upload_emails=seen_upload_emails,
            existing_emails=existing_emails,
        )
        if row_errors:
            errors.append(
                CandidateImportRowError(
                    row_number=row_number,
                    email=email,
                    errors=row_errors,
                )
            )
            continue

        seen_upload_emails.add(email)
        valid_rows.append(
            CandidateImportRow(
                row_number=row_number,
                name=name,
                email=email,
                external_id=external_id,
            )
        )

    return CandidateCSVParseResult(
        total_rows=total_rows,
        valid_rows=valid_rows,
        errors=errors,
    )


def _row_errors(
    *,
    row: dict[str | None, str | list[str] | None],
    name: str,
    email: str,
    external_id: str,
    seen_upload_emails: set[str],
    existing_emails: set[str],
) -> list[str]:
    errors: list[str] = []
    if not name:
        errors.append("name is required")
    elif len(name) > 180:
        errors.append("name cannot exceed 180 characters")
    elif _has_control_characters(name):
        errors.append("name cannot contain control characters")

    if not email or not _EMAIL_PATTERN.fullmatch(email):
        errors.append("email must be a valid email address")
    elif len(email) > 320:
        errors.append("email cannot exceed 320 characters")
    if email in seen_upload_emails:
        errors.append("duplicate email in this upload")
    if email in existing_emails:
        errors.append("candidate is already assigned to this slot")

    if len(external_id) > 120:
        errors.append("external_id cannot exceed 120 characters")
    elif _has_control_characters(external_id):
        errors.append("external_id cannot contain control characters")
    if row.get(None):
        errors.append(
            "row has extra CSV values. Wrap fields containing commas in quotes."
        )
    return errors


def _csv_value(
    row: dict[str | None, str | list[str] | None],
    header_map: dict[str, str],
    key: str,
) -> str:
    header = header_map.get(key)
    value = row.get(header) if header else None
    return value.strip() if isinstance(value, str) else ""


def _row_is_empty(row: dict[str | None, str | list[str] | None]) -> bool:
    return not any(
        isinstance(value, str) and value.strip()
        for key, value in row.items()
        if key is not None
    )


def _has_control_characters(value: str) -> bool:
    return any(character in value for character in _CONTROL_CHARACTERS)
