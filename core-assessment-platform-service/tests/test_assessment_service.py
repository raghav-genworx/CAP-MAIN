"""Assessment service repository integration tests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.exceptions.assessment import AssessmentNotFoundError
from core.services.assessment_service import AssessmentService
from core.services.evaluation_adapter_service import EvaluationJobResult
from data.models.postgres.assessment_template import AssessmentTemplateModel
from schemas.assessments import (
    AssessmentCreateRequest,
    AssessmentStatus,
    EvaluationBackfillRequest,
    ExecutionCaseResult,
)
from schemas.candidate_portal import CandidateSessionClaims, CandidateSubmitRequest


def test_evaluation_dashboard_requires_recruiter_owned_assessment() -> None:
    """Evaluation data must not cross recruiter ownership boundaries."""

    service = AssessmentService(MagicMock())
    service._repository = SimpleNamespace(
        get_assessment=MagicMock(return_value=None),
    )
    service._evaluation_adapter = SimpleNamespace(
        get_dashboard=MagicMock(),
    )

    with pytest.raises(AssessmentNotFoundError):
        service.get_evaluation_dashboard("recruiter-1", "assessment-other")

    service._evaluation_adapter.get_dashboard.assert_not_called()


def test_create_assessment_persists_through_repository() -> None:
    """Creating an assessment should use the repository unit of work."""

    service = AssessmentService(MagicMock())
    repository = SimpleNamespace(
        add=MagicMock(),
        commit=MagicMock(),
        refresh=MagicMock(),
        rollback=MagicMock(),
        list_assessment_questions=MagicMock(return_value=[]),
        list_slots_for_assessment=MagicMock(return_value=[]),
        candidate_assignments_for_slot_ids=MagicMock(return_value={}),
    )

    def refresh_model(model: AssessmentTemplateModel) -> None:
        model.id = "assessment-1"
        model.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        model.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

    repository.refresh.side_effect = refresh_model
    service._repository = repository

    record = service.create_assessment(
        "recruiter-1",
        AssessmentCreateRequest(
            title="Backend Engineer Round",
            description="Python and API assessment",
            instructions="Solve all questions.",
            status=AssessmentStatus.AVAILABLE,
        ),
    )

    repository.add.assert_called_once()
    repository.commit.assert_called_once()
    repository.refresh.assert_called_once()
    repository.rollback.assert_not_called()
    repository.list_assessment_questions.assert_called_once_with("assessment-1")
    repository.list_slots_for_assessment.assert_called_once_with(
        recruiter_uid="recruiter-1",
        assessment_id="assessment-1",
    )

    persisted_model = repository.add.call_args.args[0]
    assert isinstance(persisted_model, AssessmentTemplateModel)
    assert persisted_model.recruiter_uid == "recruiter-1"
    assert persisted_model.title == "Backend Engineer Round"
    assert record.id == "assessment-1"
    assert record.question_count == 0


def test_auto_submit_marks_empty_answer_not_attempted_without_execution() -> None:
    """Expired timers should finalize blank answers without calling execution."""

    service = AssessmentService(MagicMock())
    repository = SimpleNamespace(
        commit=MagicMock(),
        rollback=MagicMock(),
    )
    execution_adapter = SimpleNamespace(execute_batch=MagicMock())
    service._repository = repository
    service._execution_adapter = execution_adapter

    question = SimpleNamespace(
        id="question-1",
        hidden_test_cases=[
            {"input": "1 2\n", "expected_output": "3\n", "is_sample": False},
        ],
        supported_languages=["python"],
    )
    submission = SimpleNamespace(
        draft_code="",
        final_code="",
        source_language="python",
        final_hidden_result={},
        status="draft",
        submitted_at=None,
    )
    candidate_assessment = SimpleNamespace(
        id="candidate-assessment-1",
        status="in_progress",
        submission_tag="",
        submission_message="",
        submitted_at=None,
        last_activity_at=None,
    )
    context = SimpleNamespace(
        assessment=SimpleNamespace(id="assessment-1", supported_languages=["python"]),
        slot=SimpleNamespace(id="slot-1"),
        candidate=SimpleNamespace(id="candidate-1"),
        candidate_assessment=candidate_assessment,
        questions=[question],
        mappings=[SimpleNamespace(question_id="question-1")],
        submissions={"question-1": submission},
    )
    service._load_candidate_context_by_claims = MagicMock(return_value=context)

    response = service.submit_assessment(
        CandidateSessionClaims(
            candidate_assessment_id="candidate-assessment-1",
            assessment_id="assessment-1",
            slot_id="slot-1",
            candidate_id="candidate-1",
            exp=1,
        ),
        CandidateSubmitRequest(answers=[], auto_submit=True),
    )

    execution_adapter.execute_batch.assert_not_called()
    repository.commit.assert_called_once()
    assert response.status == "auto_submitted"
    assert "summaries" not in response.model_dump()
    assert submission.final_hidden_result["passed_count"] == 0
    assert submission.final_hidden_result["total_count"] == 1
    stored_result = submission.final_hidden_result["results"][0]
    assert stored_result["status"] == "not_attempted"
    assert stored_result["input"] == "1 2\n"
    assert stored_result["expected_output"] == "3\n"


def test_submit_assessment_retry_returns_existing_acknowledgement() -> None:
    """A client retry must not execute or evaluate an already committed submit."""

    service = AssessmentService(MagicMock())
    repository = SimpleNamespace(commit=MagicMock(), rollback=MagicMock())
    execution_adapter = SimpleNamespace(execute_batch=MagicMock())
    evaluation_adapter = SimpleNamespace(create_job=MagicMock())
    service._repository = repository
    service._execution_adapter = execution_adapter
    service._evaluation_adapter = evaluation_adapter
    submitted_at = datetime.now(UTC)
    assignment = SimpleNamespace(
        id="candidate-assessment-1",
        status="submitted",
        submitted_at=submitted_at,
        percentage=None,
        submission_tag="final",
        submission_message="Completed",
    )
    service._load_candidate_context_by_claims = MagicMock(
        return_value=SimpleNamespace(candidate_assessment=assignment)
    )

    response = service.submit_assessment(
        CandidateSessionClaims(
            candidate_assessment_id="candidate-assessment-1",
            assessment_id="assessment-1",
            slot_id="slot-1",
            candidate_id="candidate-1",
            exp=1,
        ),
        CandidateSubmitRequest(answers=[]),
    )

    assert response.status == "submitted"
    assert response.submitted_at == submitted_at
    assert response.pending_evaluation is True
    assert response.submission_tag == "final"
    execution_adapter.execute_batch.assert_not_called()
    evaluation_adapter.create_job.assert_not_called()
    repository.commit.assert_not_called()


def test_submit_assessment_updates_scores_from_evaluation_service() -> None:
    """Final submit should send hidden evidence to evaluation and store the score."""

    service = AssessmentService(MagicMock())
    repository = SimpleNamespace(
        list_submitted_assignments_for_assessment=MagicMock(),
        commit=MagicMock(),
        rollback=MagicMock(),
    )
    service._repository = repository
    service._execution_adapter = SimpleNamespace(
        execute_batch=MagicMock(
            return_value=(
                [
                    ExecutionCaseResult(
                        index=1,
                        input="1 2\n",
                        expected_output="3\n",
                        actual_output="3\n",
                        status="Accepted",
                        passed=True,
                        stderr="",
                        compile_output="",
                        message="",
                        execution_time="0.1",
                        memory_kb=32000,
                        token="token-1",
                    )
                ],
                1,
                1,
            )
        )
    )
    evaluation_job = EvaluationJobResult.model_validate(
        {
            "job_id": "eval-1",
            "assessment_id": "assessment-1",
            "candidate_assessment_id": "candidate-assessment-1",
            "status": "completed",
            "attempt_count": 1,
            "result": {
                "rank": 2,
                "scores": {
                    "test_case_score": 100,
                    "coding_score": 95,
                    "ai_score": 85,
                    "final_score": 96,
                    "percentage": 96,
                },
                "hidden_passed": 1,
                "hidden_total": 1,
                "total_execution_time_ms": 100,
                "peak_memory_kb": 32000,
                "ai_quality": {},
                "question_breakdown": [],
            },
        }
    )
    service._evaluation_adapter = SimpleNamespace(
        create_job=MagicMock(return_value=evaluation_job),
        get_leaderboard=MagicMock(
            return_value=[
                SimpleNamespace(
                    candidate_assessment_id="candidate-assessment-1",
                    rank=3,
                    scores=SimpleNamespace(final_score=91, percentage=91),
                )
            ]
        ),
    )

    now = datetime.now(UTC)
    question = SimpleNamespace(
        id="question-1",
        title="Add Two Numbers",
        hidden_test_cases=[
            {"input": "1 2\n", "expected_output": "3\n", "is_sample": False},
        ],
        supported_languages=["python"],
    )
    submission = SimpleNamespace(
        question_id="question-1",
        draft_code="print(3)",
        final_code="",
        source_language="python",
        final_hidden_result={},
        status="draft",
        submitted_at=None,
    )
    candidate_assessment = SimpleNamespace(
        id="candidate-assessment-1",
        status="in_progress",
        started_at=now,
        submission_tag="",
        submission_message="",
        submitted_at=None,
        last_activity_at=None,
        total_score=None,
        percentage=None,
        rank=None,
    )
    repository.list_submitted_assignments_for_assessment.return_value = [
        candidate_assessment
    ]
    context = SimpleNamespace(
        assessment=SimpleNamespace(
            id="assessment-1",
            recruiter_uid="recruiter-1",
            supported_languages=["python"],
            passing_score=40,
            test_case_score_weight=60,
            coding_score_weight=20,
            ai_score_weight=20,
            question_count_per_candidate=0,
            shuffle_questions=False,
        ),
        slot=SimpleNamespace(id="slot-1"),
        candidate=SimpleNamespace(
            id="candidate-1",
            full_name="Candidate One",
            email="candidate@example.com",
        ),
        candidate_assessment=candidate_assessment,
        questions=[question],
        mappings=[
            SimpleNamespace(
                question_id="question-1",
                question_order=1,
                marks=10,
                is_mandatory=True,
            )
        ],
        submissions={"question-1": submission},
    )
    service._load_candidate_context_by_claims = MagicMock(return_value=context)

    response = service.submit_assessment(
        CandidateSessionClaims(
            candidate_assessment_id="candidate-assessment-1",
            assessment_id="assessment-1",
            slot_id="slot-1",
            candidate_id="candidate-1",
            exp=1,
        ),
        CandidateSubmitRequest(
            answers=[
                {
                    "question_id": "question-1",
                    "source_code": "print(3)",
                    "language": "python",
                }
            ],
        ),
    )

    service._evaluation_adapter.create_job.assert_called_once()
    service._evaluation_adapter.get_leaderboard.assert_called_once_with("assessment-1")
    repository.list_submitted_assignments_for_assessment.assert_called_once_with(
        recruiter_uid="recruiter-1",
        assessment_id="assessment-1",
        candidate_assessment_ids=None,
    )
    assert response.pending_evaluation is True
    assert candidate_assessment.total_score == 91
    assert candidate_assessment.percentage == 91
    assert candidate_assessment.rank == 3
    assert submission.final_hidden_result["evaluation_job"]["job_id"] == "eval-1"


def test_backfill_evaluates_previous_submitted_candidate() -> None:
    """Backfill should score stored final hidden results for old submissions."""

    service = AssessmentService(MagicMock())
    now = datetime.now(UTC)
    assignment = SimpleNamespace(
        id="candidate-assessment-1",
        assessment_id="assessment-1",
        slot_id="slot-1",
        candidate_id="candidate-1",
        started_at=now - timedelta(minutes=45),
        submitted_at=now,
        total_score=None,
        percentage=None,
        rank=None,
    )
    repository = SimpleNamespace(
        get_assessment=MagicMock(return_value=SimpleNamespace(id="assessment-1")),
        list_submitted_assignments_for_assessment=MagicMock(return_value=[assignment]),
        commit=MagicMock(),
        rollback=MagicMock(),
    )
    service._repository = repository
    evaluation_job = EvaluationJobResult.model_validate(
        {
            "job_id": "eval-backfill-1",
            "assessment_id": "assessment-1",
            "candidate_assessment_id": "candidate-assessment-1",
            "status": "completed",
            "attempt_count": 1,
            "result": {
                "rank": 1,
                "scores": {
                    "test_case_score": 100,
                    "coding_score": 90,
                    "ai_score": 80,
                    "final_score": 94,
                    "percentage": 94,
                },
                "hidden_passed": 1,
                "hidden_total": 1,
                "total_execution_time_ms": 100,
                "peak_memory_kb": 32000,
                "ai_quality": {},
                "question_breakdown": [],
            },
        }
    )
    service._evaluation_adapter = SimpleNamespace(
        create_job=MagicMock(return_value=evaluation_job),
        get_leaderboard=MagicMock(
            return_value=[
                SimpleNamespace(
                    candidate_assessment_id="candidate-assessment-1",
                    rank=3,
                    scores=SimpleNamespace(final_score=91, percentage=91),
                )
            ]
        ),
    )

    submission = SimpleNamespace(
        question_id="question-1",
        draft_code="",
        final_code="print(3)",
        source_language="python",
        final_hidden_result={
            "passed_count": 1,
            "total_count": 1,
            "results": [
                ExecutionCaseResult(
                    index=1,
                    input="1 2\n",
                    expected_output="3\n",
                    actual_output="3\n",
                    status="Accepted",
                    passed=True,
                    execution_time="0.1",
                    memory_kb=32000,
                ).model_dump(mode="json")
            ],
        },
        status="submitted",
    )
    context = SimpleNamespace(
        assessment=SimpleNamespace(
            id="assessment-1",
            passing_score=40,
            test_case_score_weight=60,
            coding_score_weight=20,
            ai_score_weight=20,
            question_count_per_candidate=0,
            shuffle_questions=False,
        ),
        slot=SimpleNamespace(id="slot-1"),
        candidate=SimpleNamespace(
            id="candidate-1",
            full_name="Candidate One",
            email="candidate@example.com",
        ),
        candidate_assessment=assignment,
        questions=[
            SimpleNamespace(
                id="question-1",
                title="Add Two Numbers",
            )
        ],
        mappings=[
            SimpleNamespace(
                question_id="question-1",
                question_order=1,
                marks=10,
                is_mandatory=True,
            )
        ],
        submissions={"question-1": submission},
    )
    service._load_candidate_context_by_assignment = MagicMock(return_value=context)

    response = service.backfill_evaluations(
        "recruiter-1",
        "assessment-1",
        EvaluationBackfillRequest(),
    )

    repository.list_submitted_assignments_for_assessment.assert_called_once_with(
        recruiter_uid="recruiter-1",
        assessment_id="assessment-1",
        candidate_assessment_ids=None,
    )
    service._evaluation_adapter.create_job.assert_called_once()
    payload = service._evaluation_adapter.create_job.call_args.args[0]
    assert payload["candidate_assessment_id"] == "candidate-assessment-1"
    assert payload["hidden_results"][0]["verdict"] == "accepted"
    assert response.evaluated_count == 1
    assert response.results[0].evaluation_job_id == "eval-backfill-1"
    service._evaluation_adapter.get_leaderboard.assert_called_once_with("assessment-1")
    assert assignment.total_score == 91
    assert assignment.percentage == 91
    assert assignment.rank == 3
    assert submission.final_hidden_result["evaluation_job"]["job_id"] == (
        "eval-backfill-1"
    )
    repository.commit.assert_called_once()


def test_backfill_reruns_hidden_tests_when_previous_evidence_is_missing() -> None:
    """Backfill should produce final hidden evidence for older submitted answers."""

    service = AssessmentService(MagicMock())
    now = datetime.now(UTC)
    assignment = SimpleNamespace(
        id="candidate-assessment-1",
        assessment_id="assessment-1",
        slot_id="slot-1",
        candidate_id="candidate-1",
        started_at=now - timedelta(minutes=30),
        submitted_at=now,
        total_score=None,
        percentage=None,
        rank=None,
    )
    repository = SimpleNamespace(
        get_assessment=MagicMock(return_value=SimpleNamespace(id="assessment-1")),
        list_submitted_assignments_for_assessment=MagicMock(return_value=[assignment]),
        commit=MagicMock(),
        rollback=MagicMock(),
    )
    service._repository = repository
    service._execution_adapter = SimpleNamespace(
        execute_batch=MagicMock(
            return_value=(
                [
                    ExecutionCaseResult(
                        index=1,
                        input="1 2\n",
                        expected_output="3\n",
                        actual_output="3\n",
                        status="Accepted",
                        passed=True,
                        execution_time="0.1",
                        memory_kb=32000,
                    )
                ],
                1,
                1,
            )
        )
    )
    evaluation_job = EvaluationJobResult.model_validate(
        {
            "job_id": "eval-rerun-1",
            "assessment_id": "assessment-1",
            "candidate_assessment_id": "candidate-assessment-1",
            "status": "completed",
            "attempt_count": 1,
            "result": {
                "rank": 1,
                "scores": {
                    "test_case_score": 100,
                    "coding_score": 90,
                    "ai_score": 80,
                    "final_score": 94,
                    "percentage": 94,
                },
                "hidden_passed": 1,
                "hidden_total": 1,
                "total_execution_time_ms": 100,
                "peak_memory_kb": 32000,
                "ai_quality": {},
                "question_breakdown": [],
            },
        }
    )
    service._evaluation_adapter = SimpleNamespace(
        create_job=MagicMock(return_value=evaluation_job),
        get_leaderboard=MagicMock(
            return_value=[
                SimpleNamespace(
                    candidate_assessment_id="candidate-assessment-1",
                    rank=2,
                    scores=SimpleNamespace(final_score=93, percentage=93),
                )
            ]
        ),
    )

    submission = SimpleNamespace(
        question_id="question-1",
        draft_code="print(3)",
        final_code="",
        source_language="python",
        final_hidden_result={},
        submitted_at=None,
        status="submitted",
    )
    context = SimpleNamespace(
        assessment=SimpleNamespace(
            id="assessment-1",
            test_case_score_weight=60,
            coding_score_weight=20,
            ai_score_weight=20,
            question_count_per_candidate=0,
            shuffle_questions=False,
        ),
        slot=SimpleNamespace(id="slot-1"),
        candidate=SimpleNamespace(
            id="candidate-1",
            full_name="Candidate One",
            email="candidate@example.com",
        ),
        candidate_assessment=assignment,
        questions=[
            SimpleNamespace(
                id="question-1",
                title="Add Two Numbers",
                hidden_test_cases=[
                    {
                        "input": "1 2\n",
                        "expected_output": "3\n",
                        "is_sample": False,
                    }
                ],
            )
        ],
        mappings=[
            SimpleNamespace(
                question_id="question-1",
                question_order=1,
                marks=10,
                is_mandatory=True,
            )
        ],
        submissions={"question-1": submission},
    )
    service._load_candidate_context_by_assignment = MagicMock(return_value=context)

    response = service.backfill_evaluations(
        "recruiter-1",
        "assessment-1",
        EvaluationBackfillRequest(),
    )

    service._execution_adapter.execute_batch.assert_called_once()
    service._evaluation_adapter.create_job.assert_called_once()
    assert response.evaluated_count == 1
    assert response.results[0].evaluation_job_id == "eval-rerun-1"
    service._evaluation_adapter.get_leaderboard.assert_called_once_with("assessment-1")
    assert assignment.total_score == 93
    assert assignment.percentage == 93
    assert assignment.rank == 2
    assert submission.final_code == "print(3)"
    assert submission.final_hidden_result["passed_count"] == 1
    assert submission.final_hidden_result["evaluation_job"]["job_id"] == "eval-rerun-1"


def test_slot_candidates_include_evaluation_scores() -> None:
    """Recruiter candidate rows should expose stored evaluation score fields."""

    service = AssessmentService(MagicMock())
    assignment = SimpleNamespace(
        id="candidate-assessment-1",
        candidate_id="candidate-1",
        email_status="sent",
        status="submitted",
        hidden_checks_used=2,
        submission_tag="",
        submission_message="",
        started_at=None,
        submitted_at=datetime.now(UTC),
        last_activity_at=None,
        total_score=94,
        percentage=94,
        rank=1,
    )
    service._repository = SimpleNamespace(
        list_slot_assignments=MagicMock(return_value=[assignment]),
        candidates_by_ids=MagicMock(
            return_value={
                "candidate-1": SimpleNamespace(
                    full_name="Candidate One",
                    email="candidate@example.com",
                    external_id="EXT-1",
                )
            }
        ),
    )

    response = service.list_slot_candidates("recruiter-1", "slot-1")

    candidate = response.items[0]
    assert candidate.total_score == 94
    assert candidate.percentage == 94
    assert candidate.rank == 1


def test_start_candidate_session_refreshes_stale_not_started_deadline() -> None:
    """A stale not-started assignment should not begin with an expired timer."""

    service = AssessmentService(MagicMock())
    now = datetime.now(UTC)
    repository = SimpleNamespace(
        commit=MagicMock(),
        rollback=MagicMock(),
    )
    assignment = SimpleNamespace(
        id="candidate-assessment-1",
        started_at=now - timedelta(days=1),
        deadline_at=now - timedelta(hours=23),
        status="not_started",
        last_activity_at=None,
    )
    context = SimpleNamespace(
        assessment=SimpleNamespace(
            id="assessment-1",
            duration_minutes=60,
            allow_resume=True,
        ),
        slot=SimpleNamespace(
            id="slot-1",
            end_at=now + timedelta(hours=2),
        ),
        candidate=SimpleNamespace(id="candidate-1"),
        candidate_assessment=assignment,
    )
    service._repository = repository
    service._load_candidate_context_by_invite = MagicMock(return_value=context)
    service._candidate_can_start = MagicMock(return_value=True)
    service._ensure_submission_rows = MagicMock()
    service._candidate_session_service = SimpleNamespace(
        expires_at_from_deadline=MagicMock(return_value=now + timedelta(minutes=60)),
        issue_session=MagicMock(return_value="session-token"),
    )

    response = service.start_candidate_session("invite-token")

    assert response.session_token == "session-token"
    assert assignment.status == "in_progress"
    assert assignment.deadline_at > now
    assert assignment.deadline_at <= now + timedelta(minutes=60, seconds=1)
    repository.commit.assert_called_once()
