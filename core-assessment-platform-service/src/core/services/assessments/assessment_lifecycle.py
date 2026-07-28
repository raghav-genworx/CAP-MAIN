"""Pure assessment and slot lifecycle projections."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from data.models.postgres.core.assessment_slot import AssessmentSlotModel
from data.models.postgres.core.assessment_template import AssessmentTemplateModel
from data.models.postgres.core.candidate_assessment import CandidateAssessmentModel
from schemas.assessments import (
    AssessmentSlotRecord,
    AssessmentSlotSummaryRecord,
    AssessmentStatus,
    CandidateAssessmentStatus,
    SlotStatus,
)


def effective_slot_status(
    model: AssessmentSlotModel,
    *,
    now: datetime | None = None,
) -> SlotStatus:
    """Resolve a slot's operational status at a specific instant."""

    if model.status == SlotStatus.PAUSED.value:
        return SlotStatus.PAUSED
    if model.status == SlotStatus.CLOSED.value:
        return SlotStatus.CLOSED
    if model.status == SlotStatus.DRAFT.value:
        return SlotStatus.DRAFT

    current = _utc_instant(now)
    start_at = model.start_at.astimezone(UTC)
    end_at = model.end_at.astimezone(UTC)
    if current < start_at:
        return SlotStatus.SCHEDULED
    if current <= end_at:
        return SlotStatus.ACTIVE
    return SlotStatus.CLOSED


def slot_record_from_model(
    model: AssessmentSlotModel,
    *,
    candidate_count: int,
    submitted_count: int,
    now: datetime | None = None,
) -> AssessmentSlotRecord:
    """Build the detailed API projection for a slot."""

    current = _utc_instant(now)
    status = effective_slot_status(model, now=current)
    if not getattr(model, "duration_minutes", None):
        model.duration_minutes = 60
    record = AssessmentSlotRecord.model_validate(model)
    return record.model_copy(
        update={
            "effective_status": status,
            "seconds_until_start": _seconds_remaining(model.start_at, current),
            "accepting_closes_in_seconds": _seconds_remaining(
                model.end_at,
                current,
            ),
            "is_accepting_responses": status == SlotStatus.ACTIVE,
            "candidate_count": candidate_count,
            "submitted_count": submitted_count,
        }
    )


def slot_summary_from_model(
    model: AssessmentSlotModel,
    *,
    candidate_count: int,
    submitted_count: int,
    now: datetime | None = None,
) -> AssessmentSlotSummaryRecord:
    """Build the compact assessment-library projection for a slot."""

    current = _utc_instant(now)
    return AssessmentSlotSummaryRecord(
        id=model.id,
        title=model.title,
        start_at=model.start_at,
        end_at=model.end_at,
        duration_minutes=model.duration_minutes or 60,
        timezone_name=model.timezone_name,
        timezone_offset_minutes=model.timezone_offset_minutes,
        status=SlotStatus(model.status),
        effective_status=effective_slot_status(model, now=current),
        seconds_until_start=_seconds_remaining(model.start_at, current),
        accepting_closes_in_seconds=_seconds_remaining(model.end_at, current),
        candidate_count=candidate_count,
        submitted_count=submitted_count,
    )


def assessment_status_from_slots(
    model: AssessmentTemplateModel,
    slots: Iterable[AssessmentSlotSummaryRecord],
) -> AssessmentStatus:
    """Derive the assessment status exposed in recruiter views."""

    if model.status == AssessmentStatus.ARCHIVED.value:
        return AssessmentStatus.ARCHIVED

    statuses = {slot.effective_status for slot in slots}
    if statuses & {SlotStatus.ACTIVE, SlotStatus.PAUSED}:
        return AssessmentStatus.LIVE
    if SlotStatus.SCHEDULED in statuses:
        return AssessmentStatus.SCHEDULED
    return AssessmentStatus.AVAILABLE


def submitted_assignment_count(
    assignments: Iterable[CandidateAssessmentModel],
) -> int:
    """Count final candidate assignments without treating drafts as submitted."""

    submitted_statuses = {
        CandidateAssessmentStatus.SUBMITTED.value,
        CandidateAssessmentStatus.AUTO_SUBMITTED.value,
    }
    return sum(1 for item in assignments if item.status in submitted_statuses)


def _seconds_remaining(target: datetime, now: datetime) -> int:
    return max(0, int((target.astimezone(UTC) - now).total_seconds()))


def _utc_instant(value: datetime | None) -> datetime:
    instant = value or datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Lifecycle timestamps must include an explicit UTC offset")
    return instant.astimezone(UTC)
