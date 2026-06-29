"""Pure formatting helpers shared by printable evaluation reports."""

from datetime import datetime
from textwrap import wrap
from typing import TypedDict

from schemas.evaluation import (
    AssessmentEvaluationOverview,
    CandidateEvaluationSummary,
)


class QuestionAnalyticsRow(TypedDict):
    """Aggregated question metrics used by assessment and test reports."""

    title: str
    candidates: int
    average_score: float
    pass_rate: float


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
