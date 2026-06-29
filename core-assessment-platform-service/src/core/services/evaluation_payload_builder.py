"""Build evaluation-service payloads from persisted submission evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data.models.postgres.assessment_question import AssessmentQuestionModel
from data.models.postgres.assessment_template import AssessmentTemplateModel
from data.models.postgres.candidate import CandidateModel
from data.models.postgres.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.submission import SubmissionModel
from schemas.assessments import SubmissionExecutionSummary


def build_evaluation_payload(
    *,
    assessment: AssessmentTemplateModel,
    candidate: CandidateModel,
    candidate_assessment: CandidateAssessmentModel,
    mappings: list[AssessmentQuestionModel],
    questions: list[QuestionBankQuestionModel],
    submissions: list[SubmissionModel],
    summaries: list[SubmissionExecutionSummary],
    submitted_at: datetime,
) -> dict[str, Any]:
    """Create the trusted internal contract sent to code-evaluation-service."""

    mapping_by_question = {mapping.question_id: mapping for mapping in mappings}
    question_by_id = {question.id: question for question in questions}
    hidden_results: list[dict[str, Any]] = []

    for summary in summaries:
        question = question_by_id.get(summary.question_id)
        mapping = mapping_by_question.get(summary.question_id)
        points = _points_per_hidden_case(mapping, summary.total_count)
        for result in summary.results:
            hidden_results.append(
                {
                    "question_id": summary.question_id,
                    "question_title": getattr(question, "title", "Question"),
                    "test_case_id": f"{summary.question_id}:{result.index}",
                    "passed": result.passed,
                    "verdict": _evaluation_verdict(result.status),
                    "execution_time_ms": _execution_time_ms(result.execution_time),
                    "memory_kb": result.memory_kb,
                    "points": points,
                    "mandatory": bool(getattr(mapping, "is_mandatory", False)),
                    "input": result.input,
                    "expected_output": result.expected_output,
                    "actual_output": result.actual_output,
                    "message": result.message or result.stderr or result.compile_output,
                }
            )

    source_code = "\n\n".join(
        _source_code_block(question_by_id.get(submission.question_id), submission)
        for submission in submissions
        if (submission.final_code or submission.draft_code).strip()
    )
    return {
        "assessment_id": assessment.id,
        "candidate_assessment_id": candidate_assessment.id,
        "candidate_id": candidate.id,
        "candidate_name": candidate.full_name,
        "candidate_email": candidate.email,
        "submission_id": candidate_assessment.id,
        "language": _dominant_submission_language(submissions),
        "source_code": source_code or "No submitted source code.",
        "hidden_results": hidden_results,
        "weights": {
            "test_case_weight": assessment.test_case_score_weight,
            "coding_weight": assessment.coding_score_weight,
            "ai_weight": assessment.ai_score_weight,
        },
        "submitted_at": submitted_at.isoformat(),
        "time_taken_seconds": _time_taken_seconds(
            candidate_assessment,
            submitted_at,
        ),
    }


def _points_per_hidden_case(
    mapping: AssessmentQuestionModel | None,
    total_count: int,
) -> float:
    marks = float(getattr(mapping, "marks", 1) or 1)
    return marks / total_count if total_count > 0 else marks


def _evaluation_verdict(status: str) -> str:
    normalized = status.strip().lower().replace(" ", "_")
    if "accepted" in normalized:
        return "accepted"
    if "compil" in normalized:
        return "compile_error"
    if "runtime" in normalized:
        return "runtime_error"
    if "time_limit" in normalized or "timeout" in normalized:
        return "time_limit_exceeded"
    if "memory" in normalized:
        return "memory_limit_exceeded"
    if "execution" in normalized and "failed" in normalized:
        return "execution_failure"
    return "wrong_answer"


def _execution_time_ms(execution_time: str) -> float | None:
    value = execution_time.strip()
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed * 1000 if parsed < 100 else parsed


def _source_code_block(
    question: QuestionBankQuestionModel | None,
    submission: SubmissionModel,
) -> str:
    title = getattr(question, "title", submission.question_id)
    code = (submission.final_code or submission.draft_code).strip()
    return f"# Question ID: {submission.question_id}\n# Question: {title}\n{code}"


def _dominant_submission_language(submissions: list[SubmissionModel]) -> str:
    languages = [
        submission.source_language.strip()
        for submission in submissions
        if submission.source_language.strip()
    ]
    if not languages:
        return "unknown"
    first = languages[0]
    return first if all(language == first for language in languages) else "multiple"


def _time_taken_seconds(
    candidate_assessment: CandidateAssessmentModel,
    submitted_at: datetime,
) -> int | None:
    started_at = candidate_assessment.started_at
    if started_at is None:
        return None
    return max(0, int((submitted_at - started_at).total_seconds()))
