"""Tests for server-authoritative assessment schedule normalization."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from core.exceptions.assessment import AssessmentValidationError
from core.services.assessment_schedule import normalize_assessment_schedule


@pytest.mark.parametrize(
    ("start_at", "timezone_name", "expected_offset"),
    [
        (datetime(2026, 6, 15, 8, tzinfo=UTC), "Europe/London", 60),
        (datetime(2026, 12, 15, 9, tzinfo=UTC), "Europe/London", 0),
        (datetime(2026, 6, 15, 13, tzinfo=UTC), "America/New_York", -240),
        (datetime(2026, 12, 15, 14, tzinfo=UTC), "America/New_York", -300),
    ],
)
def test_schedule_derives_date_aware_timezone_offset(
    start_at: datetime,
    timezone_name: str,
    expected_offset: int,
) -> None:
    schedule = normalize_assessment_schedule(
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        timezone_name=timezone_name,
    )

    assert schedule.start_at == start_at
    assert schedule.end_at == start_at + timedelta(hours=1)
    assert schedule.timezone_offset_minutes == expected_offset


def test_schedule_normalizes_instants_to_utc_and_defaults_blank_zone() -> None:
    india = timezone(timedelta(hours=5, minutes=30))
    schedule = normalize_assessment_schedule(
        start_at=datetime(2026, 6, 15, 9, tzinfo=india),
        end_at=datetime(2026, 6, 15, 10, tzinfo=india),
        timezone_name="  ",
    )

    assert schedule.start_at == datetime(2026, 6, 15, 3, 30, tzinfo=UTC)
    assert schedule.end_at == datetime(2026, 6, 15, 4, 30, tzinfo=UTC)
    assert schedule.timezone_name == "Asia/Kolkata"
    assert schedule.timezone_offset_minutes == 330


def test_schedule_rejects_unknown_zone_naive_instants_and_reversed_window() -> None:
    start_at = datetime(2026, 6, 15, 9, tzinfo=UTC)

    with pytest.raises(AssessmentValidationError, match="Unknown assessment timezone"):
        normalize_assessment_schedule(
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            timezone_name="Invalid/Zone",
        )
    with pytest.raises(AssessmentValidationError, match="explicit UTC offset"):
        normalize_assessment_schedule(
            start_at=datetime(2026, 6, 15, 9),
            end_at=datetime(2026, 6, 15, 10),
            timezone_name="Etc/UTC",
        )
    with pytest.raises(AssessmentValidationError, match="after the start time"):
        normalize_assessment_schedule(
            start_at=start_at,
            end_at=start_at,
            timezone_name="Etc/UTC",
        )


def test_schedule_rejects_past_start_and_window_shorter_than_test() -> None:
    future_start = datetime.now(UTC) + timedelta(hours=2)
    with pytest.raises(AssessmentValidationError, match="cannot be in the past"):
        normalize_assessment_schedule(
            start_at=datetime.now(UTC) - timedelta(minutes=1),
            end_at=datetime.now(UTC) + timedelta(hours=1),
            timezone_name="Etc/UTC",
            duration_minutes=60,
            reject_past_start=True,
        )
    with pytest.raises(AssessmentValidationError, match="at least 60 minutes"):
        normalize_assessment_schedule(
            start_at=future_start,
            end_at=future_start + timedelta(minutes=59),
            timezone_name="Etc/UTC",
            duration_minutes=60,
            reject_past_start=True,
        )
