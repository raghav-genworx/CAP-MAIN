"""Regression coverage for the consolidated lifecycle and validation fixes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase

from pydantic import ValidationError

from core.exceptions.assessment import (
    AssessmentValidationError,
    CandidateInviteError,
)
from core.services.assessment_lifecycle import effective_slot_status
from core.services.assessment_service import (
    AssessmentService,
    CandidateAssessmentContext,
)
from data.models.postgres.assessment_slot import AssessmentSlotModel
from data.models.postgres.submission import SubmissionModel
from schemas.assessments import AssessmentCreateRequest, SlotStatus
from schemas.candidate_portal import CandidateCheckpointRequest


class ConsolidatedFixesTests(TestCase):
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
