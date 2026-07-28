"""Build evaluation-service payloads from persisted submission evidence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from data.models.postgres.core.assessment_template import AssessmentTemplateModel
from data.models.postgres.core.candidate import CandidateModel
from data.models.postgres.core.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.core.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.core.submission import SubmissionModel
from schemas.assessments import SubmissionExecutionSummary


def build_evaluation_payload(
    *,
    assessment: AssessmentTemplateModel,
    candidate: CandidateModel,
    candidate_assessment: CandidateAssessmentModel,
    mappings: Sequence[Any],
    questions: list[QuestionBankQuestionModel],
    submissions: list[SubmissionModel],
    summaries: list[SubmissionExecutionSummary],
    submitted_at: datetime,
) -> dict[str, Any]:
    """Create the trusted internal contract sent to code-evaluation-service."""

    mapping_by_question = {mapping.question_id: mapping for mapping in mappings}
    question_by_id = {question.id: question for question in questions}
    submission_by_question = {
        submission.question_id: submission for submission in submissions
    }
    hidden_results: list[dict[str, Any]] = []

    for summary in summaries:
        question = question_by_id.get(summary.question_id)
        mapping = mapping_by_question.get(summary.question_id)
        points = _points_per_hidden_case(mapping, summary.total_count)
        case_categories = _hidden_case_categories(question)
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
                    "case_category": case_categories.get(result.index, ""),
                }
            )

    answered_submissions = [
        submission
        for submission in submissions
        if submission.question_id in mapping_by_question
        and (submission.final_code or submission.draft_code).strip()
    ]
    source_code = "\n\n".join(
        _source_code_block(question_by_id.get(submission.question_id), submission)
        for submission in answered_submissions
    )
    question_submissions = []
    for mapping in sorted(mappings, key=lambda item: item.question_order):
        question = question_by_id.get(mapping.question_id)
        submission = submission_by_question.get(mapping.question_id)
        question_submissions.append(
            {
                "question_id": mapping.question_id,
                "question_title": getattr(question, "title", "Question"),
                "language": (
                    submission.source_language.strip()
                    if submission is not None and submission.source_language.strip()
                    else "unknown"
                ),
                "source_code": (
                    (submission.final_code or submission.draft_code).strip()
                    if submission is not None
                    else ""
                ),
                "marks": float(getattr(mapping, "marks", 1) or 1),
                "difficulty": getattr(question, "difficulty", "") or "",
                "tags": list(getattr(question, "tags", []) or []),
                "problem_statement": getattr(question, "problem_statement", "") or "",
                "input_format": getattr(question, "input_format", "") or "",
                "output_format": getattr(question, "output_format", "") or "",
                "constraints": getattr(question, "constraints", "") or "",
                "suggested_solution": "",
                "suggested_improvement_notes": _suggested_improvement_notes(question),
            }
        )
    return {
        "assessment_id": assessment.id,
        "candidate_assessment_id": candidate_assessment.id,
        "candidate_id": candidate.id,
        "candidate_name": candidate.full_name,
        "candidate_email": candidate.email,
        "submission_id": candidate_assessment.id,
        "language": _dominant_submission_language(answered_submissions),
        "source_code": source_code or "No submitted source code.",
        "question_submissions": question_submissions,
        "hidden_results": hidden_results,
        "weights": {
            "test_case_weight": assessment.test_case_score_weight,
            "coding_weight": assessment.coding_score_weight,
            "ai_weight": assessment.ai_score_weight,
        },
        "activity": {
            "started_at": (
                candidate_assessment.started_at.isoformat()
                if candidate_assessment.started_at is not None
                else None
            ),
            "submitted_at": submitted_at.isoformat(),
            "total_time_seconds": _time_taken_seconds(
                candidate_assessment,
                submitted_at,
            ),
            "question_time_seconds": dict(
                candidate_assessment.question_time_seconds or {}
            ),
        },
        "integrity": {
            "proctoring_mode": getattr(assessment, "proctoring_mode", "") or "",
            "tab_switches": candidate_assessment.tab_switch_count,
            "copy_paste_count": candidate_assessment.copy_paste_count,
            "fullscreen_exits": candidate_assessment.fullscreen_exit_count,
            "suspicious_activity": _integrity_activity(candidate_assessment),
            "plagiarism_similarity_score": None,
        },
        "submitted_at": submitted_at.isoformat(),
        "time_taken_seconds": _time_taken_seconds(
            candidate_assessment,
            submitted_at,
        ),
    }


def _integrity_activity(
    candidate_assessment: CandidateAssessmentModel,
) -> list[str]:
    activity: list[str] = []
    if candidate_assessment.tab_switch_count:
        activity.append(
            f"{candidate_assessment.tab_switch_count} tab switch(es) detected"
        )
    if candidate_assessment.copy_paste_count:
        activity.append(
            f"{candidate_assessment.copy_paste_count} clipboard action(s) detected"
        )
    if candidate_assessment.fullscreen_exit_count:
        activity.append(
            f"{candidate_assessment.fullscreen_exit_count} fullscreen exit(s) detected"
        )
    if candidate_assessment.submission_tag:
        activity.append(
            candidate_assessment.submission_message
            or candidate_assessment.submission_tag.replace("_", " ")
        )
    return activity


def _points_per_hidden_case(
    mapping: Any | None,
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


def _hidden_case_categories(
    question: QuestionBankQuestionModel | None,
) -> dict[int, str]:
    categories: dict[int, str] = {}
    for index, test_case in enumerate(
        getattr(question, "hidden_test_cases", []) or [],
        start=1,
    ):
        if not isinstance(test_case, dict):
            continue
        category = (
            test_case.get("category")
            or test_case.get("case_type")
            or test_case.get("type")
            or test_case.get("label")
            or ""
        )
        if isinstance(category, str) and category.strip():
            categories[index] = category.strip()
    return categories


def _suggested_improvement_notes(
    question: QuestionBankQuestionModel | None,
) -> list[str]:
    notes: list[str] = []
    approach = getattr(question, "solution_approach", "") or ""
    if approach.strip():
        notes.append(approach.strip())
    time_complexity = getattr(question, "time_complexity", "") or ""
    space_complexity = getattr(question, "space_complexity", "") or ""
    if time_complexity.strip() or space_complexity.strip():
        notes.append(
            "Expected complexity: "
            f"time {time_complexity.strip() or 'not specified'}, "
            f"space {space_complexity.strip() or 'not specified'}."
        )
    return notes[:8]


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
