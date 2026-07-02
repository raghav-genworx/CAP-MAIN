"""Pure formatting helpers shared by printable evaluation reports."""

from datetime import datetime
from textwrap import wrap
from typing import TypedDict

from schemas.evaluation import (
    AssessmentEvaluationOverview,
    CandidateEvaluationSummary,
    EvaluationScores,
    ScoringWeights,
)


class QuestionAnalyticsRow(TypedDict):
    """Aggregated question metrics used by assessment and test reports."""

    title: str
    candidates: int
    average_score: float
    pass_rate: float


class Recommendation(TypedDict):
    """Recruiter-facing recommendation label and explanation."""

    label: str
    explanation: str
    color: str


class ScoreBreakdownRow(TypedDict):
    """Display row for transparent score composition."""

    component: str
    weight: float
    raw_score: float
    weighted_score: float


def numbered_code(source_code: str, *, line_width: int = 94) -> str:
    """Add stable line numbers and wrap long source lines for A4 rendering."""

    output: list[str] = []
    lines = source_code.expandtabs(4).splitlines() or [""]
    for line_number, line in enumerate(lines, start=1):
        chunks = wrap(
            line,
            width=line_width,
            replace_whitespace=False,
            drop_whitespace=False,
        ) or [""]
        output.append(f"{line_number:>4}  {chunks[0]}")
        output.extend(f"      {chunk}" for chunk in chunks[1:])
    return "\n".join(output)


def safe_text(value: object, fallback: str = "Not available") -> str:
    """Return a clean report label for optional values."""

    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def hidden_case_label(index: int) -> str:
    """Format hidden cases without exposing internal identifiers."""

    return f"Case {max(index, 1)}"


def score_breakdown_rows(
    scores: EvaluationScores,
    weights: ScoringWeights,
) -> list[ScoreBreakdownRow]:
    """Format existing score math as raw and weighted display rows."""

    components = [
        ("Hidden test correctness", weights.test_case_weight, scores.test_case_score),
        ("Coding/runtime metrics", weights.coding_weight, scores.coding_score),
        ("AI code quality", weights.ai_weight, scores.ai_score),
    ]
    return [
        {
            "component": label,
            "weight": weight,
            "raw_score": raw_score,
            "weighted_score": raw_score * weight / 100,
        }
        for label, weight, raw_score in components
    ]


def recruiter_recommendation(
    candidate: CandidateEvaluationSummary,
) -> Recommendation:
    """Derive a decision-ready recommendation from stored score signals."""

    final_score = candidate.scores.final_score
    hidden_rate = (
        candidate.hidden_passed / candidate.hidden_total * 100
        if candidate.hidden_total
        else 0
    )
    ai_score = candidate.scores.ai_score
    integrity = candidate.integrity
    suspicious_count = (
        len(integrity.suspicious_activity)
        if integrity is not None and integrity.suspicious_activity
        else 0
    )
    similarity = (
        integrity.plagiarism_similarity_score
        if integrity is not None
        else None
    )
    if not candidate.hidden_total or suspicious_count or (
        similarity is not None and similarity >= 70
    ):
        return {
            "label": "Manual Review Required",
            "color": "amber",
            "explanation": (
                "The automated score needs recruiter validation before a hiring "
                "decision. This is due to missing hidden-test evidence or integrity "
                "signals that should be reviewed manually."
            ),
        }
    if final_score >= 85 and hidden_rate >= 85 and ai_score >= 75:
        return {
            "label": "Strong Hire",
            "color": "green",
            "explanation": (
                "The candidate demonstrates strong correctness, stable execution, "
                "and healthy code-quality signals. The score is reliable because "
                "hidden tests and AI review are both strongly aligned."
            ),
        }
    if final_score >= 70 and hidden_rate >= 70 and ai_score >= 60:
        return {
            "label": "Hire",
            "color": "green",
            "explanation": (
                "The candidate solved most of the assessed requirements and shows "
                "acceptable implementation quality. Minor review may still be useful "
                "for edge cases or maintainability."
            ),
        }
    if final_score < 40 or hidden_rate < 40:
        return {
            "label": "Reject",
            "color": "red",
            "explanation": (
                "The submission did not meet the expected correctness threshold. "
                "Hidden test failures indicate the solution is not reliable enough "
                "to move forward without a materially stronger follow-up."
            ),
        }
    return {
        "label": "Further Review",
        "color": "amber",
        "explanation": (
            "The candidate has partial evidence of fit, but the score profile is "
            "mixed. Review the question evidence and code-quality notes before "
            "deciding whether to continue."
        ),
    }


def question_analytics(
    leaderboard: list[CandidateEvaluationSummary],
) -> list[QuestionAnalyticsRow]:
    """Aggregate score and hidden-case pass rates by question."""

    grouped: dict[str, dict[str, float | int | str]] = {}
    for candidate in leaderboard:
        for question in candidate.question_breakdown:
            row = grouped.setdefault(
                question.question_id,
                {
                    "title": question.question_title,
                    "candidates": 0,
                    "score_total": 0.0,
                    "passed": 0,
                    "total": 0,
                },
            )
            row["candidates"] = int(row["candidates"]) + 1
            row["score_total"] = float(row["score_total"]) + question.score
            row["passed"] = int(row["passed"]) + question.passed_count
            row["total"] = int(row["total"]) + question.total_count

    rows: list[QuestionAnalyticsRow] = []
    for row in grouped.values():
        candidates = int(row["candidates"])
        total = int(row["total"])
        rows.append(
            {
                "title": str(row["title"]),
                "candidates": candidates,
                "average_score": (
                    float(row["score_total"]) / candidates if candidates else 0.0
                ),
                "pass_rate": (int(row["passed"]) / total * 100) if total else 0.0,
            }
        )
    return sorted(rows, key=lambda item: item["title"].lower())


def assessment_summary(
    overview: AssessmentEvaluationOverview,
    leaderboard: list[CandidateEvaluationSummary],
) -> str:
    """Create a concise executive assessment summary."""

    if not leaderboard:
        return (
            "No completed evaluations are available yet. This report will populate "
            "automatically as submitted candidates finish evaluation."
        )
    return (
        f"{overview.completed_candidates} of {overview.total_candidates} candidates "
        "have completed evaluation. The cohort average is "
        f"{overview.average_score:.1f}% "
        f"with a {overview.pass_rate:.1f}% pass rate; the highest final score is "
        f"{overview.highest_score:.1f}%. Review the question analytics for difficulty "
        "signals and use individual scorecards for source-level evidence."
    )


def schedule_label(
    start: datetime | None,
    end: datetime | None,
    timezone_name: str,
) -> str:
    """Format a scheduled test window without guessing missing bounds."""

    if start is None and end is None:
        return "Schedule not specified"
    start_text = start.strftime("%d %b %Y %H:%M") if start else "Open"
    end_text = end.strftime("%d %b %Y %H:%M") if end else "Open"
    return f"{start_text} to {end_text} ({timezone_name})"


def duration_label(seconds: int | None) -> str:
    """Format a non-negative candidate duration for report display."""

    if seconds is None:
        return "Not recorded"
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    return f"{minutes}m {remaining_seconds}s"


def memory_label(memory_kb: int) -> str:
    """Format execution memory using the report's KB/MB convention."""

    normalized = max(memory_kb, 0)
    if normalized >= 1024:
        return f"{normalized / 1024:.1f} MB"
    return f"{normalized} KB"


def safe_report_slug(value: str) -> str:
    """Return a path-safe, deterministic report filename component."""

    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in normalized.split("-") if part) or "report"
