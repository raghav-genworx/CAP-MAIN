"""Tests for deterministic assessment and slot lifecycle projections."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest

from core.services.assessment_lifecycle import (
    assessment_status_from_slots,
    effective_slot_status,
    slot_record_from_model,
    submitted_assignment_count,
)
from data.models.postgres.assessment_slot import AssessmentSlotModel
from data.models.postgres.assessment_template import AssessmentTemplateModel
from data.models.postgres.candidate_assessment import CandidateAssessmentModel
from schemas.assessments import (
    AssessmentSlotSummaryRecord,
    AssessmentStatus,
    CandidateAssessmentStatus,
    SlotStatus,
)

NOW = datetime(2026, 6, 28, 9, 30, tzinfo=UTC)


def _slot(
    *,
    status: SlotStatus = SlotStatus.SCHEDULED,
    start_at: datetime = NOW - timedelta(minutes=30),
    end_at: datetime = NOW + timedelta(minutes=30),
) -> AssessmentSlotModel:
    return AssessmentSlotModel(
        id="slot-1",
        assessment_id="assessment-1",
        recruiter_uid="recruiter-1",
        title="Backend test",
        instructions_override="",
        start_at=start_at,
        end_at=end_at,
        timezone_name="Etc/UTC",
        timezone_offset_minutes=0,
        status=status.value,
        paused_at=None,
        total_paused_seconds=0,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )


@pytest.mark.parametrize(
    ("status", "start_at", "end_at", "expected"),
    [
        (
            SlotStatus.SCHEDULED,
            NOW + timedelta(seconds=1),
            NOW + timedelta(hours=1),
            SlotStatus.SCHEDULED,
        ),
        (SlotStatus.SCHEDULED, NOW, NOW + timedelta(hours=1), SlotStatus.ACTIVE),
        (SlotStatus.SCHEDULED, NOW - timedelta(hours=1), NOW, SlotStatus.ACTIVE),
        (
            SlotStatus.SCHEDULED,
            NOW - timedelta(hours=1),
            NOW - timedelta(seconds=1),
            SlotStatus.CLOSED,
        ),
        (
            SlotStatus.PAUSED,
            NOW - timedelta(hours=1),
            NOW - timedelta(seconds=1),
            SlotStatus.PAUSED,
        ),
        (
            SlotStatus.CLOSED,
            NOW + timedelta(hours=1),
            NOW + timedelta(hours=2),
            SlotStatus.CLOSED,
        ),
        (
            SlotStatus.DRAFT,
            NOW - timedelta(hours=1),
            NOW + timedelta(hours=1),
            SlotStatus.DRAFT,
        ),
    ],
)
def test_effective_slot_status_covers_boundaries_and_manual_overrides(
    status: SlotStatus,
    start_at: datetime,
    end_at: datetime,
    expected: SlotStatus,
) -> None:
    assert (
        effective_slot_status(
            _slot(status=status, start_at=start_at, end_at=end_at),
            now=NOW,
        )
        == expected
    )


def test_slot_record_uses_one_clock_for_status_and_countdowns() -> None:
    model = _slot(
        start_at=NOW + timedelta(seconds=10),
        end_at=NOW + timedelta(seconds=70),
    )

    record = slot_record_from_model(
        model,
        candidate_count=12,
        submitted_count=4,
        now=NOW,
    )

    assert record.effective_status == SlotStatus.SCHEDULED
    assert record.seconds_until_start == 10
    assert record.accepting_closes_in_seconds == 70
    assert record.is_accepting_responses is False
    assert record.candidate_count == 12
    assert record.submitted_count == 4


def test_assessment_status_prioritizes_archive_then_live_then_schedule() -> None:
    model = cast(
        AssessmentTemplateModel,
        SimpleNamespace(status=AssessmentStatus.AVAILABLE.value),
    )
    archived = cast(
        AssessmentTemplateModel,
        SimpleNamespace(status=AssessmentStatus.ARCHIVED.value),
    )

    def summary(status: SlotStatus) -> AssessmentSlotSummaryRecord:
        return AssessmentSlotSummaryRecord(
            id=status.value,
            title=status.value,
            start_at=NOW,
            end_at=NOW,
            status=status,
            effective_status=status,
        )

    assert (
        assessment_status_from_slots(archived, [summary(SlotStatus.ACTIVE)])
        == AssessmentStatus.ARCHIVED
    )
    assert (
        assessment_status_from_slots(
            model, [summary(SlotStatus.SCHEDULED), summary(SlotStatus.PAUSED)]
        )
        == AssessmentStatus.LIVE
    )
    assert (
        assessment_status_from_slots(model, [summary(SlotStatus.SCHEDULED)])
        == AssessmentStatus.SCHEDULED
    )
    assert (
        assessment_status_from_slots(model, [summary(SlotStatus.CLOSED)])
        == AssessmentStatus.AVAILABLE
    )


def test_submitted_count_accepts_only_final_states() -> None:
    assignments = [
        cast(CandidateAssessmentModel, SimpleNamespace(status=status.value))
        for status in CandidateAssessmentStatus
    ]

    assert submitted_assignment_count(assignments) == 2


def test_lifecycle_rejects_naive_reference_clock() -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        effective_slot_status(_slot(), now=datetime(2026, 6, 28, 9, 30))
