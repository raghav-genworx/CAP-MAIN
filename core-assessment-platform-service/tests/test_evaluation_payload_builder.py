"""Unit coverage for the core-to-evaluation payload boundary."""

from datetime import UTC, datetime, timedelta

import pytest

from core.services.evaluation_payload_builder import build_evaluation_payload
from data.models.postgres.assessment_question import AssessmentQuestionModel
from data.models.postgres.assessment_template import AssessmentTemplateModel
from data.models.postgres.candidate import CandidateModel
from data.models.postgres.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.submission import SubmissionModel
from schemas.assessments import ExecutionCaseResult, SubmissionExecutionSummary


def test_build_evaluation_payload_preserves_scoring_and_execution_evidence() -> None:
    submitted_at = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    assessment = AssessmentTemplateModel(
        id="assessment-1",
        test_case_score_weight=60,
        coding_score_weight=25,
        ai_score_weight=15,
    )
    candidate = CandidateModel(
        id="candidate-1",
        full_name="Candidate One",
        email="candidate@example.com",
    )
    assignment = CandidateAssessmentModel(
        id="candidate-assessment-1",
        started_at=submitted_at - timedelta(minutes=42),
    )
    mapping = AssessmentQuestionModel(
        question_id="question-1",
        marks=12,
        is_mandatory=True,
    )
    question = QuestionBankQuestionModel(
        id="question-1",
        title="Add two numbers",
        difficulty="easy",
        tags=["math", "io"],
        problem_statement="Read two integers and print their sum.",
        input_format="Two integers on one line.",
        output_format="The sum.",
        constraints="0 <= a,b <= 100",
        hidden_test_cases=[
            {"category": "Small numbers"},
            {"case_type": "Compile guard"},
        ],
        solution_approach="Parse and add directly.",
        time_complexity="O(1)",
        space_complexity="O(1)",
    )
    submissions = [
        SubmissionModel(
            question_id="question-1",
            source_language="python",
            final_code="print(sum(map(int, input().split())))",
            draft_code="",
        ),
        SubmissionModel(
            question_id="question-2",
            source_language="java",
            final_code="class Main {}",
            draft_code="",
        ),
    ]
    statuses = [
        "Accepted",
        "Compilation Error",
        "Runtime Error",
        "Time Limit Exceeded",
        "Memory Limit Exceeded",
        "Execution Failed",
    ]
    summary = SubmissionExecutionSummary(
        question_id="question-1",
        passed_count=1,
        total_count=len(statuses),
        results=[
            ExecutionCaseResult(
                index=index,
                input=f"input-{index}",
                expected_output=f"expected-{index}",
                actual_output=f"actual-{index}",
                status=status,
                passed=status == "Accepted",
                execution_time="0.125" if index == 1 else "invalid",
                memory_kb=32000,
                message="",
                stderr="runtime details" if status == "Runtime Error" else "",
            )
            for index, status in enumerate(statuses, start=1)
        ],
    )

    payload = build_evaluation_payload(
        assessment=assessment,
        candidate=candidate,
        candidate_assessment=assignment,
        mappings=[mapping],
        questions=[question],
        submissions=submissions,
        summaries=[summary],
        submitted_at=submitted_at,
    )

    assert payload["assessment_id"] == "assessment-1"
    assert payload["candidate_assessment_id"] == "candidate-assessment-1"
    assert payload["candidate_name"] == "Candidate One"
    assert payload["language"] == "python"
    assert payload["time_taken_seconds"] == 42 * 60
    assert payload["weights"] == {
        "test_case_weight": 60,
        "coding_weight": 25,
        "ai_weight": 15,
    }
    assert "# Question: Add two numbers" in str(payload["source_code"])
    assert "class Main {}" not in str(payload["source_code"])
    assert payload["question_submissions"] == [
        {
            "question_id": "question-1",
            "question_title": "Add two numbers",
            "language": "python",
            "source_code": "print(sum(map(int, input().split())))",
            "marks": 12.0,
            "difficulty": "easy",
            "tags": ["math", "io"],
            "problem_statement": "Read two integers and print their sum.",
            "input_format": "Two integers on one line.",
            "output_format": "The sum.",
            "constraints": "0 <= a,b <= 100",
            "suggested_solution": "",
            "suggested_improvement_notes": [
                "Parse and add directly.",
                "Expected complexity: time O(1), space O(1).",
            ],
        }
    ]

    hidden_results = payload["hidden_results"]
    assert isinstance(hidden_results, list)
    assert [item["verdict"] for item in hidden_results] == [
        "accepted",
        "compile_error",
        "runtime_error",
        "time_limit_exceeded",
        "memory_limit_exceeded",
        "execution_failure",
    ]
    assert hidden_results[0]["execution_time_ms"] == pytest.approx(125)
    assert hidden_results[1]["execution_time_ms"] is None
    assert hidden_results[0]["points"] == pytest.approx(2)
    assert hidden_results[0]["mandatory"] is True
    assert hidden_results[0]["case_category"] == "Small numbers"
    assert hidden_results[1]["case_category"] == "Compile guard"
    assert hidden_results[2]["message"] == "runtime details"
    assert payload["activity"] == {
        "started_at": (submitted_at - timedelta(minutes=42)).isoformat(),
        "submitted_at": submitted_at.isoformat(),
        "total_time_seconds": 42 * 60,
        "question_time_seconds": {},
    }
    assert payload["integrity"]["proctoring_mode"] == ""
    assert payload["integrity"]["tab_switches"] is None


def test_build_evaluation_payload_handles_no_source_or_start_time() -> None:
    submitted_at = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    payload = build_evaluation_payload(
        assessment=AssessmentTemplateModel(
            id="assessment-1",
            test_case_score_weight=60,
            coding_score_weight=20,
            ai_score_weight=20,
        ),
        candidate=CandidateModel(
            id="candidate-1",
            full_name="Candidate One",
            email="candidate@example.com",
        ),
        candidate_assessment=CandidateAssessmentModel(
            id="candidate-assessment-1",
            started_at=None,
        ),
        mappings=[],
        questions=[],
        submissions=[],
        summaries=[],
        submitted_at=submitted_at,
    )

    assert payload["source_code"] == "No submitted source code."
    assert payload["language"] == "unknown"
    assert payload["time_taken_seconds"] is None
    assert payload["hidden_results"] == []
    assert payload["question_submissions"] == []
    assert payload["activity"]["started_at"] is None
    assert payload["activity"]["total_time_seconds"] is None
