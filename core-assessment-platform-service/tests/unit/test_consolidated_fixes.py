"""Regression coverage for the consolidated lifecycle and validation fixes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase

import pytest
from pydantic import ValidationError

from core.exceptions.assessment import (
    AssessmentValidationError,
    CandidateInviteError,
)
from core.services.assessments.assessment_lifecycle import effective_slot_status
from core.services.assessments.assessment_schedule import normalize_assessment_schedule
from core.services.assessments.assessment_service import (
    AssessmentService,
    CandidateAssessmentContext,
)
from data.models.postgres.core.assessment_slot import AssessmentSlotModel
from data.models.postgres.core.submission import SubmissionModel
from schemas.assessments import (
    AssessmentCreateRequest,
    SlotStatus,
    SubmissionExecutionSummary,
)
from schemas.candidate_portal import CandidateCheckpointRequest

pytestmark = pytest.mark.unit


class ConsolidatedFixesTests(TestCase):
    def test_new_slot_rejects_a_past_start(self) -> None:
        now = datetime.now(UTC)
        with self.assertRaisesRegex(
            AssessmentValidationError,
            "start time cannot be in the past",
        ):
            normalize_assessment_schedule(
                start_at=now - timedelta(hours=2),
                end_at=now - timedelta(hours=1),
                timezone_name="UTC",
                duration_minutes=60,
                reject_past_start=True,
            )

    def test_existing_slot_allows_a_past_start(self) -> None:
        now = datetime.now(UTC)
        schedule = normalize_assessment_schedule(
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(hours=1),
            timezone_name="UTC",
            duration_minutes=60,
            reject_past_start=False,
        )
        self.assertLess(schedule.start_at, now)

    def test_passing_score_must_be_above_zero(self) -> None:
        with self.assertRaises(ValidationError):
            AssessmentCreateRequest(title="Backend test", passing_score=0)

    def test_closed_status_wins_over_future_schedule(self) -> None:
        now = datetime.now(UTC)
        slot = AssessmentSlotModel(
            assessment_id="assessment",
            recruiter_uid="recruiter",
            title="Future slot",
            start_at=now + timedelta(days=1),
            end_at=now + timedelta(days=1, hours=1),
            duration_minutes=60,
            timezone_name="UTC",
            timezone_offset_minutes=0,
            status=SlotStatus.CLOSED.value,
        )
        self.assertEqual(effective_slot_status(slot, now=now), SlotStatus.CLOSED)
        with self.assertRaisesRegex(CandidateInviteError, "Invites"):
            AssessmentService._assert_slot_accepts_invites(slot)

    def test_paused_candidate_time_is_frozen_at_pause_instant(self) -> None:
        now = datetime.now(UTC)
        paused_at = now - timedelta(minutes=10)
        deadline = paused_at + timedelta(minutes=25)
        slot = AssessmentSlotModel(
            assessment_id="assessment",
            recruiter_uid="recruiter",
            title="Paused slot",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            duration_minutes=60,
            timezone_name="UTC",
            timezone_offset_minutes=0,
            status=SlotStatus.PAUSED.value,
            paused_at=paused_at,
        )
        context = CandidateAssessmentContext(
            assessment=SimpleNamespace(),
            slot=slot,
            candidate=SimpleNamespace(),
            candidate_assessment=SimpleNamespace(deadline_at=deadline),
            questions=[],
            mappings=[],
            submissions={},
        )
        self.assertEqual(
            AssessmentService._candidate_time_remaining_seconds(context),
            25 * 60,
        )

    def test_stale_draft_version_is_rejected(self) -> None:
        submission = SubmissionModel(
            candidate_assessment_id="candidate-assessment",
            assessment_id="assessment",
            question_id="question",
            version=4,
        )
        with self.assertRaisesRegex(AssessmentValidationError, "another tab"):
            AssessmentService._assert_draft_version(submission, 3)

    def test_checkpoint_totals_cannot_replace_server_proctor_counts(self) -> None:
        assignment = SimpleNamespace(
            tab_switch_count=5,
            copy_paste_count=6,
            fullscreen_exit_count=7,
            question_time_seconds={},
        )
        payload = CandidateCheckpointRequest(
            question_id="question",
            source_code="print(1)",
            language="python",
            current_question_order=1,
            tab_switch_count=999,
            copy_paste_count=999,
            fullscreen_exit_count=999,
            question_time_seconds={"question": 10},
        )
        AssessmentService._merge_candidate_activity_evidence(assignment, payload)
        self.assertEqual(assignment.tab_switch_count, 5)
        self.assertEqual(assignment.copy_paste_count, 6)
        self.assertEqual(assignment.fullscreen_exit_count, 7)
        self.assertEqual(assignment.question_time_seconds, {"question": 10})

    def test_every_assessment_language_must_exist_on_every_question(self) -> None:
        questions = [
            SimpleNamespace(title="Python only", supported_languages=["python"])
        ]
        with self.assertRaisesRegex(AssessmentValidationError, "missing java"):
            AssessmentService._assert_assessment_language_coverage(
                ["python", "java"],
                questions,
            )

    def test_initial_screen_score_is_weighted_by_question_marks(self) -> None:
        earned_score, percentage = AssessmentService._initial_screen_score(
            [
                SimpleNamespace(question_id="easy", marks=20),
                SimpleNamespace(question_id="hard", marks=80),
            ],
            [
                SubmissionExecutionSummary(
                    question_id="easy",
                    passed_count=2,
                    total_count=2,
                    results=[],
                ),
                SubmissionExecutionSummary(
                    question_id="hard",
                    passed_count=2,
                    total_count=4,
                    results=[],
                ),
            ],
        )

        self.assertEqual(earned_score, 60)
        self.assertEqual(percentage, 60)
