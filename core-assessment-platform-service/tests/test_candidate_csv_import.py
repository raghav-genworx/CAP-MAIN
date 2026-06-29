"""Tests for strict candidate CSV parsing and validation."""

import pytest

from core.exceptions.assessment import AssessmentValidationError
from core.services.candidate_csv_import import (
    MAX_CANDIDATE_IMPORT_ROWS,
    parse_candidate_csv,
)


def test_candidate_csv_normalizes_headers_values_and_email() -> None:
    result = parse_candidate_csv(
        "\ufeff Name , EMAIL , External_ID \n Ada Lovelace , ADA@Example.COM , ENG-1 \n"
    )

    assert result.total_rows == 1
    assert result.errors == []
    assert result.valid_rows[0].name == "Ada Lovelace"
    assert result.valid_rows[0].email == "ada@example.com"
    assert result.valid_rows[0].external_id == "ENG-1"
    assert result.valid_rows[0].row_number == 2


def test_candidate_csv_reports_invalid_duplicate_and_existing_rows() -> None:
    result = parse_candidate_csv(
        "name,email,external_id\n"
        "Invalid,not-an-email,\n"
        "Existing,EXISTING@example.com,\n"
        "First,duplicate@example.com,\n"
        "Second,DUPLICATE@example.com,\n",
        existing_emails={"existing@example.com"},
    )

    assert result.total_rows == 4
    assert [row.email for row in result.valid_rows] == ["duplicate@example.com"]
    assert result.errors[0].errors == ["email must be a valid email address"]
    assert result.errors[1].errors == ["candidate is already assigned to this slot"]
    assert result.errors[2].errors == ["duplicate email in this upload"]


def test_candidate_csv_rejects_duplicate_or_missing_headers() -> None:
    with pytest.raises(AssessmentValidationError, match="duplicate column.*email"):
        parse_candidate_csv("name,email, EMAIL \nAda,a@example.com,b@example.com\n")

    with pytest.raises(AssessmentValidationError, match="missing required.*email"):
        parse_candidate_csv("name,external_id\nAda,ENG-1\n")


def test_candidate_csv_reports_field_limits_controls_and_extra_values() -> None:
    long_name = "N" * 181
    long_external_id = "E" * 121
    result = parse_candidate_csv(
        "name,email,external_id\n"
        f"{long_name},long-name@example.com,\n"
        f'"Bad\nName",control@example.com,{long_external_id}\n'
        "Comma,comma@example.com,ENG-1,unexpected\n"
    )

    assert result.total_rows == 3
    assert result.valid_rows == []
    assert result.errors[0].errors == ["name cannot exceed 180 characters"]
    assert result.errors[1].errors == [
        "name cannot contain control characters",
        "external_id cannot exceed 120 characters",
    ]
    assert result.errors[2].errors == [
        "row has extra CSV values. Wrap fields containing commas in quotes."
    ]


def test_candidate_csv_rejects_malformed_and_oversized_uploads() -> None:
    with pytest.raises(AssessmentValidationError, match="CSV is malformed"):
        parse_candidate_csv('name,email\n"Unclosed,candidate@example.com\n')

    rows = "".join(
        f"Candidate {index},candidate-{index}@example.com\n"
        for index in range(MAX_CANDIDATE_IMPORT_ROWS + 1)
    )
    with pytest.raises(AssessmentValidationError, match="more than 5000 candidates"):
        parse_candidate_csv("name,email\n" + rows)
