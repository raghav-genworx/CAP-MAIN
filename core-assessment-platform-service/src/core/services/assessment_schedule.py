"""Server-authoritative normalization for assessment test schedules."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.exceptions.assessment import AssessmentValidationError

DEFAULT_TIMEZONE_NAME = "Asia/Kolkata"


@dataclass(frozen=True)
class NormalizedAssessmentSchedule:
    """Validated UTC window with its effective IANA timezone metadata."""

    start_at: datetime
    end_at: datetime
    timezone_name: str
    timezone_offset_minutes: int


def normalize_assessment_schedule(
    *,
    start_at: datetime,
    end_at: datetime,
    timezone_name: str,
    duration_minutes: int = 1,
    reject_past_start: bool = False,
) -> NormalizedAssessmentSchedule:
    """Validate and normalize an assessment slot schedule."""

    _require_aware_datetime(start_at, "start_at")
    _require_aware_datetime(end_at, "end_at")
    start_utc = start_at.astimezone(UTC)
    end_utc = end_at.astimezone(UTC)
    now = datetime.now(UTC)
    if reject_past_start and start_utc < now:
        raise AssessmentValidationError("Test start time cannot be in the past")
    minimum_end = start_utc + timedelta(minutes=duration_minutes)
    if end_utc < minimum_end:
        raise AssessmentValidationError(
            f"Test end time must be at least {duration_minutes} minutes "
            "after the start time"
        )

    normalized_timezone_name = timezone_name.strip() or DEFAULT_TIMEZONE_NAME
    try:
        timezone = ZoneInfo(normalized_timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AssessmentValidationError(
            f"Unknown assessment timezone: {normalized_timezone_name}"
        ) from exc

    start_offset = start_utc.astimezone(timezone).utcoffset()
    if start_offset is None:
        raise AssessmentValidationError(
            f"Unable to resolve assessment timezone: {normalized_timezone_name}"
        )
    offset_minutes = round(start_offset.total_seconds() / 60)
    return NormalizedAssessmentSchedule(
        start_at=start_utc,
        end_at=end_utc,
        timezone_name=normalized_timezone_name,
        timezone_offset_minutes=offset_minutes,
    )


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AssessmentValidationError(
            f"{field_name} must include an explicit UTC offset"
        )
