"""Professional printable evaluation reports built with ReportLab."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from html import escape
from importlib.resources import files
from pathlib import Path
from typing import Any

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import (  # type: ignore[import-untyped]
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    HRFlowable,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.services.report_formatting import (
    assessment_summary,
    duration_label,
    hidden_case_label,
    memory_label,
    numbered_code,
    question_analytics,
    recruiter_recommendation,
    safe_report_slug,
    safe_text,
    schedule_label,
    score_breakdown_rows,
)
from schemas.evaluation import (
    AssessmentReportResponse,
    CandidateEvaluationSummary,
    CandidateReportResponse,
    TestReportResponse,
)

PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 30 * mm
NAVY = colors.HexColor("#132238")
INK = colors.HexColor("#182230")
MUTED = colors.HexColor("#667085")
BLUE = colors.HexColor("#2563EB")
TEAL = colors.HexColor("#0F766E")
GREEN = colors.HexColor("#15803D")
AMBER = colors.HexColor("#B45309")
RED = colors.HexColor("#B42318")
LINE = colors.HexColor("#D0D5DD")
SOFT = colors.HexColor("#F7F9FC")
PALE_BLUE = colors.HexColor("#EFF6FF")
PALE_GREEN = colors.HexColor("#ECFDF3")
STYLE_ONLY_REVIEW_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcomments?\b",
        r"\bdocstrings?\b",
        r"\bvariable\s+nam(?:e|ing)s?\b",
        r"\bnaming\b",
        r"\brename\b",
        r"\bcamelcase\b",
        r"\bsnake[_\s-]?case\b",
        r"\bhelper\s+functions?\b",
        r"\bsplit\s+into\s+functions?\b",
        r"\bextract\s+(?:a\s+)?functions?\b",
        r"\bwrap\s+.*\bfunctions?\b",
        r"\bclasses?\b",
        r"\bclass-based\b",
        r"\bobject[-\s]?oriented\b",
        r"\bmodulari[sz]e\b",
        r"\bformatting\b",
        r"\bindentation\b",
        r"\bcode\s+style\b",
    )
]
HIDDEN_BREAKDOWN_KEYS = {
    "comments",
    "formatting",
    "maintainability",
    "naming",
    "readability",
    "style",
}


@dataclass(frozen=True)
class GeneratedReport:
    """Generated report file metadata."""

    path: Path
    filename: str
    media_type: str = "application/pdf"


class ReportPdfService:
    """Create assessment, test-batch, and candidate evaluation reports."""

    def __init__(self, output_dir: str) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._styles = _report_styles()

    def assessment_report(self, report: AssessmentReportResponse) -> GeneratedReport:
        """Generate an assessment-level evaluation report."""

        filename = (
            f"assessment-{safe_report_slug(report.overview.assessment_id)}-report.pdf"
        )
        path = self._output_dir / filename
        story: list[Any] = [
            self._report_header(
                "Assessment Evaluation Report",
                report.overview.title,
                report.generated_at,
                "Assessment-wide outcomes, question performance, and ranking.",
            ),
            Spacer(1, 7 * mm),
            self._section_title("Executive summary", "01"),
            self._summary_paragraph(
                assessment_summary(report.overview, report.leaderboard)
            ),
            Spacer(1, 4 * mm),
            self._overview_cards(report.overview),
            Spacer(1, 6 * mm),
            self._section_title("Score distribution", "02"),
            self._score_distribution(report.leaderboard),
            Spacer(1, 6 * mm),
            self._section_title("Question analytics", "03"),
            self._question_analytics_table(report.leaderboard),
            Spacer(1, 7 * mm),
            self._section_title("Candidate leaderboard", "04"),
            self._leaderboard_table(report.leaderboard),
        ]
        _build_pdf(path, report.overview.title, story)
        return GeneratedReport(path=path, filename=filename)

    def test_report(self, report: TestReportResponse) -> GeneratedReport:
        """Generate a report scoped to one scheduled test batch."""

        filename = f"test-{safe_report_slug(report.test_id)}-report.pdf"
        path = self._output_dir / filename
        schedule = schedule_label(
            report.scheduled_start,
            report.scheduled_end,
            report.timezone_name,
        )
        completion_rate = (
            report.overview.completed_candidates
            / report.overview.total_candidates
            * 100
            if report.overview.total_candidates
            else 0
        )
        story: list[Any] = [
            self._report_header(
                "Scheduled Test Report",
                report.test_title,
                report.generated_at,
                "Batch participation, evaluation quality, and candidate ranking.",
            ),
            Spacer(1, 5 * mm),
            self._metadata_strip(
                [
                    ("Test ID", report.test_id),
                    ("Schedule", schedule),
                    ("Timezone", report.timezone_name),
                ]
            ),
            Spacer(1, 6 * mm),
            self._section_title("Cohort funnel", "01"),
            _metric_table(
                [
                    ("Candidates", str(report.overview.total_candidates), NAVY),
                    ("Submitted", str(report.submitted_count), BLUE),
                    (
                        "Evaluated",
                        str(report.overview.completed_candidates),
                        TEAL,
                    ),
                    ("Completion", f"{completion_rate:.1f}%", GREEN),
                ],
                self._styles,
            ),
            Spacer(1, 6 * mm),
            self._section_title("Performance summary", "02"),
            self._overview_cards(report.overview),
            Spacer(1, 6 * mm),
            self._section_title("Question analytics", "03"),
            self._question_analytics_table(report.leaderboard),
            Spacer(1, 7 * mm),
            self._section_title("Test leaderboard", "04"),
            self._leaderboard_table(report.leaderboard),
            Spacer(1, 7 * mm),
            self._report_notes(
                [
                    "This report includes only candidates assigned to this scheduled "
                    "test batch.",
                    "Submitted but unevaluated candidates are visible in the cohort "
                    "funnel and excluded from score averages.",
                    "Use candidate scorecards for source-code review and hidden-case "
                    "diagnostics.",
                ]
            ),
        ]
        _build_pdf(path, report.test_title, story)
        return GeneratedReport(path=path, filename=filename)

    def candidate_report(self, report: CandidateReportResponse) -> GeneratedReport:
        """Generate a detailed candidate scorecard with source and test evidence."""

        candidate = report.candidate
        filename = (
            f"candidate-{safe_report_slug(candidate.candidate_assessment_id)}"
            "-scorecard.pdf"
        )
        path = self._output_dir / filename
        story: list[Any] = [
            self._report_header(
                "Candidate Technical Scorecard",
                candidate.candidate_name,
                report.generated_at,
                "Decision-ready evidence from correctness, execution, and code "
                "quality.",
            ),
            Spacer(1, 5 * mm),
            self._candidate_identity(candidate),
            Spacer(1, 6 * mm),
            self._section_title("Recruiter recommendation", "01"),
            self._recommendation_panel(candidate),
            Spacer(1, 7 * mm),
            self._section_title("Score composition", "02"),
            _metric_table(
                [
                    ("Final score", f"{candidate.scores.final_score:.1f}%", NAVY),
                    (
                        "Hidden tests",
                        f"{candidate.scores.test_case_score:.1f}%",
                        BLUE,
                    ),
                    (
                        "Coding metrics",
                        f"{candidate.scores.coding_score:.1f}%",
                        TEAL,
                    ),
                    ("AI review", f"{candidate.scores.ai_score:.1f}%", GREEN),
                ],
                self._styles,
            ),
            Spacer(1, 4 * mm),
            self._score_breakdown_table(candidate),
            Spacer(1, 6 * mm),
            self._section_title("Assessment summary", "03"),
            self._execution_facts(candidate),
            Spacer(1, 5 * mm),
            self._activity_timeline(candidate),
            Spacer(1, 5 * mm),
            self._integrity_signals(candidate),
            Spacer(1, 5 * mm),
            self._benchmark_context(report.benchmark),
            Spacer(1, 7 * mm),
            self._section_title("AI solution review", "04"),
            self._ai_review(candidate),
            Spacer(1, 7 * mm),
            self._section_title("Question-wise performance", "05"),
        ]
        for index, question in enumerate(candidate.question_breakdown, start=1):
            story.extend(
                [
                    PageBreak(),
                    self._question_header(
                        index, question.question_title, question.score
                    ),
                    Spacer(1, 4 * mm),
                    _metric_table(
                        [
                            (
                                "Cases passed",
                                f"{question.passed_count}/{question.total_count}",
                                GREEN if not question.mandatory_failed else RED,
                            ),
                            (
                                "Marks",
                                f"{question.earned_marks:.1f}/{question.assigned_marks:.1f}",
                                BLUE,
                            ),
                            (
                                "Hidden score",
                                f"{question.test_case_score:.0f}%",
                                TEAL,
                            ),
                            (
                                "Coding metrics",
                                f"{question.coding_score:.0f}%",
                                TEAL,
                            ),
                            ("AI review", f"{question.ai_score:.0f}%", GREEN),
                            ("Language", question.language or candidate.language, TEAL),
                        ],
                        self._styles,
                        columns=3,
                    ),
                    Spacer(1, 5 * mm),
                    self._question_context(question),
                    Spacer(1, 5 * mm),
                    self._question_ai_review(question),
                    Spacer(1, 5 * mm),
                    self._test_coverage_summary(question.test_cases),
                    Spacer(1, 4 * mm),
                    Paragraph("Hidden test-case results", self._styles["h3"]),
                    Spacer(1, 2 * mm),
                    self._test_case_table(question.test_cases),
                    Spacer(1, 5 * mm),
                ]
            )
            failures = [case for case in question.test_cases if not case.passed]
            if failures:
                story.extend(
                    [
                        Paragraph("Failure diagnostics", self._styles["h3"]),
                        Spacer(1, 2 * mm),
                        self._failure_evidence(failures),
                        Spacer(1, 5 * mm),
                    ]
                )
            filtered_notes = _filter_review_items(
                question.suggested_improvement_notes or []
            )
            if question.suggested_solution or filtered_notes:
                story.append(
                    KeepTogether(
                        [
                            Paragraph("Suggested improvements", self._styles["h3"]),
                            Spacer(1, 2 * mm),
                            self._suggested_improvements(question, filtered_notes),
                            Spacer(1, 5 * mm),
                        ]
                    )
                )
            story.extend(
                [
                    PageBreak(),
                    Paragraph(
                        "Submitted source and candidate approach",
                        self._styles["h3"],
                    ),
                    Spacer(1, 2 * mm),
                    self._source_context_panel(
                        question,
                        question.ai_quality or candidate.ai_quality,
                    ),
                    Spacer(1, 4 * mm),
                ]
            )
            story.extend(self._code_panels(question.submitted_code))
        story.extend(
            [
                Spacer(1, 7 * mm),
                self._report_notes(
                    [
                        "Hidden inputs and expected outputs are recruiter-confidential "
                        "evaluation evidence.",
                        "AI quality feedback supports technical review and should not "
                        "replace human hiring judgment.",
                    ]
                ),
            ]
        )
        _build_pdf(path, candidate.candidate_name, story)
        return GeneratedReport(path=path, filename=filename)

    def purge_generated_before(self, cutoff: datetime) -> int:
        """Delete generated PDF artifacts older than the retention cutoff."""

        deleted = 0
        cutoff_timestamp = cutoff.timestamp()
        for path in self._output_dir.glob("*.pdf"):
            try:
                if path.stat().st_mtime < cutoff_timestamp:
                    path.unlink()
                    deleted += 1
            except FileNotFoundError:
                continue
        return deleted

    def _report_header(
        self,
        report_type: str,
        title: str,
        generated_at: datetime,
        subtitle: str,
    ) -> Table:
        generated = generated_at.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")
        brand = Table(
            [[Paragraph("CAP", self._styles["brandMark"])], ["COE EVALUATION"]],
            colWidths=[28 * mm],
        )
        brand.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                    ("TEXTCOLOR", (0, 1), (0, 1), colors.HexColor("#D0D5DD")),
                    ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 1), (0, 1), 6.5),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
                ]
            )
        )
        copy = [
            Paragraph(escape(report_type.upper()), self._styles["eyebrow"]),
            Paragraph(escape(title), self._styles["reportTitle"]),
            Paragraph(escape(subtitle), self._styles["reportSubtitle"]),
            Paragraph(f"Generated {escape(generated)}", self._styles["generated"]),
        ]
        header = Table(
            [[brand, copy]],
            colWidths=[32 * mm, CONTENT_WIDTH - 32 * mm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 10),
                    ("LEFTPADDING", (1, 0), (1, 0), 12),
                    ("RIGHTPADDING", (1, 0), (1, 0), 12),
                    ("TOPPADDING", (1, 0), (1, 0), 12),
                    ("BOTTOMPADDING", (1, 0), (1, 0), 12),
                ]
            )
        )
        return header

    def _section_title(self, title: str, number: str) -> Table:
        table = Table(
            [
                [
                    Paragraph(number, self._styles["sectionNumber"]),
                    Paragraph(title, self._styles["h2"]),
                ]
            ],
            colWidths=[12 * mm, CONTENT_WIDTH - 12 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (1, 0), (1, 0), 0.8, LINE),
                ]
            )
        )
        return table

    def _summary_paragraph(self, text: str) -> Table:
        table = Table(
            [[Paragraph(escape(text), self._styles["bodyLead"])]],
            colWidths=[CONTENT_WIDTH],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#BFDBFE")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return table

    def _overview_cards(self, overview: Any) -> Table:
        return _metric_table(
            [
                (
                    "Evaluated",
                    f"{overview.completed_candidates}/{overview.total_candidates}",
                    NAVY,
                ),
                ("Average", f"{overview.average_score:.1f}%", BLUE),
                ("Pass rate", f"{overview.pass_rate:.1f}%", TEAL),
                ("Highest", f"{overview.highest_score:.1f}%", GREEN),
                ("Hidden tests", f"{overview.average_test_case_score:.1f}%", BLUE),
                ("Coding", f"{overview.average_coding_score:.1f}%", TEAL),
                ("AI quality", f"{overview.average_ai_score:.1f}%", GREEN),
                (
                    "Failed jobs",
                    str(overview.failed_jobs),
                    RED if overview.failed_jobs else MUTED,
                ),
            ],
            self._styles,
            columns=4,
        )

    def _score_distribution(
        self,
        leaderboard: list[CandidateEvaluationSummary],
    ) -> Table:
        buckets = [
            ("Excellent", 80, 101, GREEN),
            ("Strong", 60, 80, TEAL),
            ("Developing", 40, 60, AMBER),
            ("Below threshold", 0, 40, RED),
        ]
        total = len(leaderboard)
        rows: list[list[Any]] = [
            ["Band", "Range", "Candidates", "Share", "Distribution"]
        ]
        for label, lower, upper, color in buckets:
            count = sum(
                1
                for candidate in leaderboard
                if lower <= candidate.scores.final_score < upper
            )
            share = count / total * 100 if total else 0
            rows.append(
                [
                    Paragraph(label, self._styles["tableBodyStrong"]),
                    f"{lower}-{upper - 1}%",
                    str(count),
                    f"{share:.1f}%",
                    _bar_cell(share, color),
                ]
            )
        return _styled_table(
            rows,
            [35 * mm, 24 * mm, 25 * mm, 20 * mm, CONTENT_WIDTH - 104 * mm],
            repeat_rows=1,
        )

    def _question_analytics_table(
        self,
        leaderboard: list[CandidateEvaluationSummary],
    ) -> Any:
        analytics = question_analytics(leaderboard)
        if not analytics:
            return self._empty_state(
                "Question analytics become available after evaluations complete."
            )
        rows: list[list[Any]] = [
            ["Question", "Candidates", "Average", "Pass rate", "Signal"]
        ]
        for row in analytics:
            rows.append(
                [
                    Paragraph(escape(row["title"]), self._styles["tableBodyStrong"]),
                    str(row["candidates"]),
                    f"{row['average_score']:.1f}%",
                    f"{row['pass_rate']:.1f}%",
                    _signal_label(row["pass_rate"], self._styles),
                ]
            )
        return _styled_table(
            rows,
            [CONTENT_WIDTH - 95 * mm, 23 * mm, 23 * mm, 23 * mm, 26 * mm],
            repeat_rows=1,
        )

    def _leaderboard_table(
        self,
        leaderboard: list[CandidateEvaluationSummary],
    ) -> Any:
        if not leaderboard:
            return self._empty_state(
                "No completed candidate evaluations are available."
            )
        rows: list[list[Any]] = [
            ["Rank", "Candidate", "Final", "Tests", "Coding", "AI", "Hidden"]
        ]
        for candidate in leaderboard:
            candidate_cell = Paragraph(
                f"<b>{escape(candidate.candidate_name)}</b><br/>"
                f"<font color='#667085' size='7.5'>"
                f"{escape(candidate.candidate_email)}</font>",
                self._styles["tableBody"],
            )
            rows.append(
                [
                    f"#{candidate.rank or '-'}",
                    candidate_cell,
                    f"{candidate.scores.final_score:.1f}%",
                    f"{candidate.scores.test_case_score:.1f}%",
                    f"{candidate.scores.coding_score:.1f}%",
                    f"{candidate.scores.ai_score:.1f}%",
                    f"{candidate.hidden_passed}/{candidate.hidden_total}",
                ]
            )
        table = _styled_table(
            rows,
            [
                14 * mm,
                CONTENT_WIDTH - 92 * mm,
                16 * mm,
                16 * mm,
                16 * mm,
                14 * mm,
                16 * mm,
            ],
            repeat_rows=1,
        )
        table.setStyle(TableStyle([("ALIGN", (0, 1), (0, -1), "CENTER")]))
        return table

    def _metadata_strip(self, items: list[tuple[str, str]]) -> Table:
        cells = [
            [
                Paragraph(escape(label.upper()), self._styles["metaLabel"]),
                _meta_paragraph(value, self._styles),
            ]
            for label, value in items
        ]
        table = Table([cells], colWidths=[CONTENT_WIDTH / len(cells)] * len(cells))
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table

    def _candidate_identity(self, candidate: CandidateEvaluationSummary) -> Table:
        rank = f"#{candidate.rank}" if candidate.rank else "Not ranked"
        return self._metadata_strip(
            [
                ("Candidate", candidate.candidate_name),
                ("Email", candidate.candidate_email),
                ("Language", candidate.language),
                ("Assessment rank", rank),
            ]
        )

    def _execution_facts(self, candidate: CandidateEvaluationSummary) -> Table:
        duration = duration_label(candidate.time_taken_seconds)
        return self._metadata_strip(
            [
                ("Hidden cases", f"{candidate.hidden_passed}/{candidate.hidden_total}"),
                ("Runtime total", f"{candidate.total_execution_time_ms:.0f} ms"),
                ("Peak memory", memory_label(candidate.peak_memory_kb)),
                ("Time taken", duration),
            ]
        )

    def _recommendation_panel(self, candidate: CandidateEvaluationSummary) -> Table:
        recommendation = recruiter_recommendation(candidate)
        accent = {
            "green": GREEN,
            "red": RED,
            "amber": AMBER,
        }.get(recommendation["color"], BLUE)
        pass_rate = (
            candidate.hidden_passed / candidate.hidden_total * 100
            if candidate.hidden_total
            else 0
        )
        table = Table(
            [
                [
                    Paragraph(recommendation["label"], self._styles["recommendation"]),
                    Paragraph(
                        escape(recommendation["explanation"]),
                        self._styles["bodyLead"],
                    ),
                ],
                [
                    Paragraph("Decision signals", self._styles["metaLabel"]),
                    Paragraph(
                        "Final score "
                        f"{candidate.scores.final_score:.1f}% | Hidden pass rate "
                        f"{pass_rate:.1f}% | AI quality "
                        f"{candidate.scores.ai_score:.1f}%",
                        self._styles["tableBody"],
                    ),
                ],
            ],
            colWidths=[42 * mm, CONTENT_WIDTH - 42 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.8, accent),
                    ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        return table

    def _score_breakdown_table(self, candidate: CandidateEvaluationSummary) -> Table:
        rows: list[list[Any]] = [["Component", "Weight", "Raw score", "Weighted score"]]
        for row in score_breakdown_rows(candidate.scores, candidate.weights):
            rows.append(
                [
                    Paragraph(
                        escape(row["component"]),
                        self._styles["tableBodyStrong"],
                    ),
                    f"{row['weight']:.0f}%",
                    f"{row['raw_score']:.1f}%",
                    f"{row['weighted_score']:.1f}",
                ]
            )
        rows.append(
            [
                Paragraph("Final score", self._styles["tableBodyStrong"]),
                "100%",
                "-",
                f"{candidate.scores.final_score:.1f}",
            ]
        )
        return _styled_table(
            rows,
            [CONTENT_WIDTH - 78 * mm, 22 * mm, 28 * mm, 28 * mm],
            repeat_rows=1,
        )

    def _activity_timeline(self, candidate: CandidateEvaluationSummary) -> Table:
        activity = candidate.activity
        started_at = activity.started_at if activity else None
        submitted_at = activity.submitted_at if activity else candidate.submitted_at
        total_time = (
            activity.total_time_seconds
            if activity and activity.total_time_seconds is not None
            else candidate.time_taken_seconds
        )
        question_time = "Not recorded"
        if activity and activity.question_time_seconds:
            question_time = ", ".join(
                f"{question_id}: {duration_label(seconds)}"
                for question_id, seconds in activity.question_time_seconds.items()
            )
        return self._metadata_strip(
            [
                ("Started", _datetime_label(started_at)),
                ("Submitted", _datetime_label(submitted_at)),
                ("Total time", duration_label(total_time)),
                ("Question time", question_time),
            ]
        )

    def _integrity_signals(self, candidate: CandidateEvaluationSummary) -> Table:
        integrity = candidate.integrity
        if integrity is None:
            return self._metadata_strip(
                [
                    ("Proctoring", "Not available"),
                    ("Tab switches", "Not available"),
                    ("Copy/paste", "Not available"),
                    ("Similarity", "Not available"),
                ]
            )
        similarity = (
            f"{integrity.plagiarism_similarity_score:.1f}%"
            if integrity.plagiarism_similarity_score is not None
            else "Not available"
        )
        suspicious = (
            "; ".join(integrity.suspicious_activity)
            if integrity.suspicious_activity
            else "No suspicious activity recorded"
        )
        return Table(
            [
                [
                    self._metadata_strip(
                        [
                            ("Proctoring", safe_text(integrity.proctoring_mode)),
                            (
                                "Tab switches",
                                safe_text(integrity.tab_switches),
                            ),
                            (
                                "Copy/paste",
                                safe_text(integrity.copy_paste_count),
                            ),
                            ("Similarity", similarity),
                        ]
                    )
                ],
                [
                    Paragraph(
                        f"<b>Integrity notes:</b> {escape(suspicious)}",
                        self._styles["bodyMuted"],
                    )
                ],
            ],
            colWidths=[CONTENT_WIDTH],
            style=TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            ),
        )

    def _benchmark_context(self, benchmark: Any) -> Any:
        if benchmark is None or not benchmark.total_candidates:
            return self._empty_state("Benchmark unavailable.")
        return self._metadata_strip(
            [
                (
                    "Candidate rank",
                    (
                        f"#{benchmark.candidate_rank}/{benchmark.total_candidates}"
                        if benchmark.candidate_rank
                        else "Not ranked"
                    ),
                ),
                (
                    "Average score",
                    (
                        f"{benchmark.average_score:.1f}%"
                        if benchmark.average_score is not None
                        else "Not available"
                    ),
                ),
                (
                    "Average time",
                    duration_label(benchmark.average_completion_time_seconds),
                ),
                (
                    "Percentile",
                    (
                        f"{benchmark.percentile:.1f}"
                        if benchmark.percentile is not None
                        else "Not available"
                    ),
                ),
            ]
        )

    def _ai_review(self, candidate: CandidateEvaluationSummary) -> Table:
        quality = candidate.ai_quality
        breakdown = self._ai_quality_breakdown(quality)
        narrative = Table(
            [
                [
                    Paragraph("Approach", self._styles["metaLabel"]),
                    Paragraph(escape(quality.approach), self._styles["tableBody"]),
                ],
                [
                    Paragraph("Complexity", self._styles["metaLabel"]),
                    Paragraph(
                        f"Time: {escape(quality.time_complexity)} &nbsp;&nbsp; "
                        f"Space: {escape(quality.space_complexity)}",
                        self._styles["tableBody"],
                    ),
                ],
                [
                    Paragraph("Quality score", self._styles["metaLabel"]),
                    Paragraph(
                        f"{quality.score:.1f}% {breakdown}",
                        self._styles["tableBody"],
                    ),
                ],
            ],
            colWidths=[27 * mm, CONTENT_WIDTH - 27 * mm],
        )
        narrative.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        signal_table = Table(
            [
                [
                    _bullet_panel(
                        "Strengths",
                        _filter_review_items(quality.strengths),
                        PALE_GREEN,
                        self._styles,
                    ),
                    _bullet_panel(
                        "Watch areas",
                        _filter_review_items(quality.weaknesses),
                        colors.HexColor("#FFF7ED"),
                        self._styles,
                    ),
                    _bullet_panel(
                        "Improvements",
                        _filter_review_items(quality.improvements),
                        PALE_BLUE,
                        self._styles,
                    ),
                ]
            ],
            colWidths=[CONTENT_WIDTH / 3] * 3,
        )
        signal_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return Table(
            [[narrative], [Spacer(1, 3 * mm)], [signal_table]],
            colWidths=[CONTENT_WIDTH],
            style=TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            ),
        )

    def _question_header(self, index: int, title: str, score: float) -> Table:
        table = Table(
            [
                [
                    Paragraph(f"QUESTION {index:02d}", self._styles["eyebrow"]),
                    Paragraph(escape(title), self._styles["questionTitle"]),
                    Paragraph(f"{score:.1f}%", self._styles["questionScore"]),
                ]
            ],
            colWidths=[28 * mm, CONTENT_WIDTH - 52 * mm, 24 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return table

    def _question_context(self, question: Any) -> Table:
        tags = ", ".join(question.tags) if question.tags else "Not available"
        summary = _summarize(question.problem_statement, 520)
        rows: list[list[Any]] = [
            [
                Paragraph("Difficulty", self._styles["metaLabel"]),
                Paragraph(safe_text(question.difficulty), self._styles["tableBody"]),
                Paragraph("Tags", self._styles["metaLabel"]),
                Paragraph(escape(tags), self._styles["tableBody"]),
            ],
            [
                Paragraph("Problem summary", self._styles["metaLabel"]),
                Paragraph(escape(summary), self._styles["tableBody"]),
                Paragraph("Marks", self._styles["metaLabel"]),
                Paragraph(
                    f"{question.earned_marks:.1f}/{question.assigned_marks:.1f}",
                    self._styles["tableBody"],
                ),
            ],
            [
                Paragraph("Input format", self._styles["metaLabel"]),
                Paragraph(
                    escape(_summarize(question.input_format, 260)),
                    self._styles["tableBody"],
                ),
                Paragraph("Output format", self._styles["metaLabel"]),
                Paragraph(
                    escape(_summarize(question.output_format, 260)),
                    self._styles["tableBody"],
                ),
            ],
            [
                Paragraph("Constraints", self._styles["metaLabel"]),
                Paragraph(
                    escape(_summarize(question.constraints, 420)),
                    self._styles["tableBody"],
                ),
                Paragraph("Language", self._styles["metaLabel"]),
                Paragraph(safe_text(question.language), self._styles["tableBody"]),
            ],
        ]
        table = Table(
            rows,
            colWidths=[
                24 * mm,
                (CONTENT_WIDTH - 48 * mm) / 2,
                24 * mm,
                (CONTENT_WIDTH - 48 * mm) / 2,
            ],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                    ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _question_ai_review(self, question: Any) -> Any:
        quality = question.ai_quality
        if quality is None:
            return self._empty_state("AI code-quality review is not available.")
        return Table(
            [
                [
                    Paragraph("AI review summary", self._styles["metaLabel"]),
                    Paragraph(
                        escape(
                            f"{quality.approach} Time {quality.time_complexity}; "
                            f"space {quality.space_complexity}."
                        ),
                        self._styles["tableBody"],
                    ),
                ],
                [
                    Paragraph("Quality concerns", self._styles["metaLabel"]),
                    Paragraph(
                        escape(
                            _join_or_fallback(_filter_review_items(quality.weaknesses))
                        ),
                        self._styles["tableBody"],
                    ),
                ],
                [
                    Paragraph("Why AI score may differ", self._styles["metaLabel"]),
                    Paragraph(
                        escape(
                            "AI quality scores focus on algorithm choice, complexity, "
                            "input handling, edge-case risks, and runtime/memory "
                            "behavior, so a submission can pass hidden tests but still "
                            "lose quality marks."
                        ),
                        self._styles["tableBody"],
                    ),
                ],
            ],
            colWidths=[33 * mm, CONTENT_WIDTH - 33 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                    ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        )

    def _test_coverage_summary(self, test_cases: list[Any]) -> Any:
        if not test_cases:
            return self._empty_state("Test coverage summary is not available.")
        rows: list[list[Any]] = [["Coverage category", "Cases", "Passed"]]
        grouped: dict[str, list[Any]] = {}
        for case in test_cases:
            category = (
                case.case_category.strip()
                if case.case_category
                else "Confidential hidden validation case"
            )
            grouped.setdefault(category, []).append(case)
        for category, cases in grouped.items():
            rows.append(
                [
                    Paragraph(escape(category), self._styles["tableBodyStrong"]),
                    str(len(cases)),
                    f"{sum(1 for case in cases if case.passed)}/{len(cases)}",
                ]
            )
        return _styled_table(
            rows,
            [CONTENT_WIDTH - 52 * mm, 22 * mm, 30 * mm],
            repeat_rows=1,
        )

    def _test_case_table(self, test_cases: list[Any]) -> Any:
        if not test_cases:
            return self._empty_state(
                "No hidden-case rows were retained for this question."
            )
        rows: list[list[Any]] = [
            [
                "Case",
                "Coverage",
                "Result",
                "Verdict",
                "Runtime",
                "Memory",
                "Points",
            ]
        ]
        for index, case in enumerate(test_cases, start=1):
            rows.append(
                [
                    Paragraph(hidden_case_label(index), self._styles["tableBody"]),
                    Paragraph(
                        escape(
                            case.case_category or "Confidential hidden validation case"
                        ),
                        self._styles["tableBody"],
                    ),
                    _result_label(case.passed, self._styles),
                    case.verdict.value.replace("_", " ").title(),
                    f"{case.execution_time_ms or 0:.0f} ms",
                    memory_label(case.memory_kb or 0),
                    f"{case.points:g}",
                ]
            )
        return _styled_table(
            rows,
            [
                17 * mm,
                CONTENT_WIDTH - 107 * mm,
                16 * mm,
                26 * mm,
                17 * mm,
                17 * mm,
                14 * mm,
            ],
            repeat_rows=1,
            font_size=7.2,
        )

    def _failure_evidence(self, failures: list[Any]) -> LongTable:
        rows: list[list[Any]] = [["Case", "Coverage", "Verdict", "Reviewer note"]]
        for index, case in enumerate(failures, start=1):
            note = case.message or "Failed hidden validation case."
            rows.append(
                [
                    Paragraph(
                        hidden_case_label(index),
                        self._styles["tableBodyStrong"],
                    ),
                    Paragraph(
                        escape(
                            case.case_category or "Confidential hidden validation case"
                        ),
                        self._styles["tableBody"],
                    ),
                    case.verdict.value.replace("_", " ").title(),
                    Paragraph(escape(note), self._styles["tableBody"]),
                ]
            )
        return _styled_table(
            rows,
            [
                18 * mm,
                CONTENT_WIDTH - 84 * mm,
                28 * mm,
                38 * mm,
            ],
            repeat_rows=1,
            font_size=7,
        )

    def _suggested_improvements(self, question: Any, notes: list[str]) -> Any:
        if question.suggested_solution:
            return Table(
                [
                    [
                        Paragraph("Cleaner solution", self._styles["metaLabel"]),
                        _mono_paragraph(
                            _summarize(question.suggested_solution, 3000),
                            self._styles,
                        ),
                    ]
                ],
                colWidths=[28 * mm, CONTENT_WIDTH - 28 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), SOFT),
                        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                ),
            )
        notes = notes or ["No suggested improvement notes were supplied."]
        return _bullet_panel(
            "Suggested improvement notes",
            notes,
            PALE_BLUE,
            self._styles,
        )

    def _source_context_panel(self, question: Any, quality: Any) -> Table:
        """Show the candidate's inferred approach next to the submitted source."""

        weaknesses = _filter_review_items(getattr(quality, "weaknesses", []) or [])
        reviewer_focus = (
            "; ".join(str(item).strip() for item in weaknesses[:3] if str(item).strip())
            or "No major quality concerns recorded."
        )
        rows = [
            [
                Paragraph("Candidate approach", self._styles["metaLabel"]),
                Paragraph(
                    escape(_summarize(getattr(quality, "approach", ""), 900)),
                    self._styles["bodyLead"],
                ),
            ],
            [
                Paragraph("Complexity", self._styles["metaLabel"]),
                Paragraph(
                    "Time: "
                    f"{escape(safe_text(getattr(quality, 'time_complexity', None)))}"
                    " &nbsp;&nbsp; Space: "
                    f"{escape(safe_text(getattr(quality, 'space_complexity', None)))}",
                    self._styles["tableBody"],
                ),
            ],
            [
                Paragraph("Reviewer focus", self._styles["metaLabel"]),
                Paragraph(
                    escape(_summarize(reviewer_focus, 700)),
                    self._styles["tableBody"],
                ),
            ],
            [
                Paragraph("Question", self._styles["metaLabel"]),
                Paragraph(
                    escape(safe_text(getattr(question, "question_title", None))),
                    self._styles["tableBody"],
                ),
            ],
        ]
        table = Table(rows, colWidths=[34 * mm, CONTENT_WIDTH - 34 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
                    ("BACKGROUND", (0, 0), (0, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                    ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table

    @staticmethod
    def _ai_quality_breakdown(quality: Any) -> str:
        breakdown = getattr(quality, "score_breakdown", {}) or {}
        if not breakdown:
            return "(sub-score breakdown not available)"
        ordered_keys = [
            "correctness",
            "complexity",
            "error_handling",
            "input_handling",
        ]
        labels = {
            "error_handling": "error handling",
            "input_handling": "input handling",
        }
        parts = [
            f"{labels.get(key, key.replace('_', ' '))}: {breakdown[key]:.0f}%"
            for key in ordered_keys
            if key in breakdown and key.lower() not in HIDDEN_BREAKDOWN_KEYS
        ]
        return (
            f"({'; '.join(parts)})" if parts else "(sub-score breakdown not available)"
        )

    def _code_panels(self, source_code: str) -> list[Any]:
        numbered = numbered_code(source_code or "No submitted code available.")
        lines = numbered.splitlines()
        panels: list[Any] = []
        for index in range(0, len(lines), 52):
            if index:
                panels.append(PageBreak())
            chunk = lines[index : index + 52]
            panels.extend(
                [
                    Paragraph(
                        f"SOURCE LINES {index + 1}-{index + len(chunk)}",
                        self._styles["eyebrow"],
                    ),
                    HRFlowable(width="100%", thickness=0.5, color=LINE),
                    Spacer(1, 2 * mm),
                ]
            )
            panels.extend(
                Paragraph(
                    escape(line).replace(" ", "&#160;"),
                    self._styles["codeLine"],
                )
                for line in chunk
            )
        return panels

    def _empty_state(self, message: str) -> Table:
        table = Table(
            [[Paragraph(escape(message), self._styles["bodyMuted"])]],
            colWidths=[CONTENT_WIDTH],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return table

    def _report_notes(self, notes: list[str]) -> Table:
        content: list[Any] = [
            HRFlowable(width="100%", thickness=0.7, color=LINE),
            Spacer(1, 2 * mm),
            Paragraph("REPORT NOTES", self._styles["eyebrow"]),
        ]
        content.extend(
            Paragraph(f"- {escape(note)}", self._styles["note"]) for note in notes
        )
        table = Table([[content]], colWidths=[CONTENT_WIDTH])
        table.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return table


def _build_pdf(path: Path, document_title: str, story: list[Any]) -> None:
    """Build atomically so downloads never observe a partial PDF."""

    temporary = path.with_suffix(".tmp.pdf")
    document = SimpleDocTemplate(
        str(temporary),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=document_title,
        author="Coding Assessment Platform",
        subject="Confidential evaluation report",
        pageCompression=1,
    )
    page_decorator = partial(_decorate_page, document_title=document_title)
    document.build(
        story,
        onFirstPage=page_decorator,
        onLaterPages=page_decorator,
    )
    temporary.replace(path)


def _decorate_page(canvas: Canvas, document: Any, *, document_title: str) -> None:
    canvas.saveState()
    canvas.setTitle(document_title)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(
        15 * mm, PAGE_HEIGHT - 11 * mm, PAGE_WIDTH - 15 * mm, PAGE_HEIGHT - 11 * mm
    )
    canvas.setFont("Helvetica-Bold", 7)
    canvas.setFillColor(NAVY)
    canvas.drawString(
        15 * mm, PAGE_HEIGHT - 8.5 * mm, "CAP  |  CONFIDENTIAL RECRUITER REPORT"
    )
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(
        PAGE_WIDTH - 15 * mm, PAGE_HEIGHT - 8.5 * mm, document_title[:72]
    )
    canvas.line(15 * mm, 10 * mm, PAGE_WIDTH - 15 * mm, 10 * mm)
    canvas.drawString(15 * mm, 6.5 * mm, "Generated by Coding Assessment Platform")
    canvas.drawRightString(PAGE_WIDTH - 15 * mm, 6.5 * mm, f"Page {document.page}")
    canvas.restoreState()


def _report_styles() -> dict[str, ParagraphStyle]:
    _register_report_fonts()
    base = getSampleStyleSheet()
    return {
        "brandMark": ParagraphStyle(
            "BrandMark",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=22,
            textColor=colors.white,
        ),
        "eyebrow": ParagraphStyle(
            "Eyebrow",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=BLUE,
            spaceAfter=2,
        ),
        "reportTitle": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=22,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "reportSubtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
            spaceAfter=5,
        ),
        "generated": ParagraphStyle(
            "Generated",
            parent=base["Normal"],
            fontSize=7.5,
            leading=9,
            textColor=MUTED,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=15,
            textColor=NAVY,
            spaceAfter=0,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            textColor=INK,
            spaceAfter=0,
        ),
        "sectionNumber": ParagraphStyle(
            "SectionNumber",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
            backColor=BLUE,
            borderPadding=4,
        ),
        "bodyLead": ParagraphStyle(
            "BodyLead",
            parent=base["BodyText"],
            fontSize=9.2,
            leading=14,
            textColor=INK,
        ),
        "bodyMuted": ParagraphStyle(
            "BodyMuted",
            parent=base["BodyText"],
            fontSize=8.2,
            leading=12,
            textColor=MUTED,
        ),
        "metricLabel": ParagraphStyle(
            "MetricLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.8,
            leading=8,
            textColor=MUTED,
        ),
        "metricValue": ParagraphStyle(
            "MetricValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=17,
            textColor=NAVY,
        ),
        "tableBody": ParagraphStyle(
            "TableBody",
            parent=base["Normal"],
            fontSize=7.6,
            leading=10,
            textColor=INK,
        ),
        "tableBodyStrong": ParagraphStyle(
            "TableBodyStrong",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=10,
            textColor=INK,
        ),
        "metaLabel": ParagraphStyle(
            "MetaLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=8,
            textColor=MUTED,
        ),
        "metaValue": ParagraphStyle(
            "MetaValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.2,
            leading=10,
            textColor=INK,
        ),
        "questionTitle": ParagraphStyle(
            "QuestionTitle",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.white,
        ),
        "questionScore": ParagraphStyle(
            "QuestionScore",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=colors.white,
        ),
        "recommendation": ParagraphStyle(
            "Recommendation",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=NAVY,
        ),
        "pill": ParagraphStyle(
            "Pill",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=6.7,
            leading=8,
            textColor=colors.white,
        ),
        "mono": ParagraphStyle(
            "Mono",
            parent=base["Normal"],
            fontName="CAPCode",
            fontSize=6.5,
            leading=8,
            textColor=INK,
        ),
        "codeLine": ParagraphStyle(
            "CodeLine",
            parent=base["Code"],
            fontName="Courier",
            fontSize=6.7,
            leading=9,
            textColor=INK,
            leftIndent=0,
            spaceAfter=0,
            spaceBefore=0,
        ),
        "note": ParagraphStyle(
            "Note",
            parent=base["Normal"],
            fontSize=7.2,
            leading=10,
            textColor=MUTED,
            spaceBefore=2,
        ),
    }


def _register_report_fonts() -> None:
    if "CAPCode" in pdfmetrics.getRegisteredFontNames():
        return
    font_path = files("reportlab").joinpath("fonts", "Vera.ttf")
    pdfmetrics.registerFont(TTFont("CAPCode", str(font_path)))


def _metric_table(
    metrics: list[tuple[str, str, Any]],
    styles: dict[str, ParagraphStyle],
    *,
    columns: int = 4,
) -> Table:
    rows: list[list[Any]] = []
    for index in range(0, len(metrics), columns):
        batch = metrics[index : index + columns]
        cells: list[Any] = []
        for label, value, accent in batch:
            cell = Table(
                [
                    [Paragraph(escape(label.upper()), styles["metricLabel"])],
                    [Paragraph(escape(value), styles["metricValue"])],
                ],
                colWidths=[CONTENT_WIDTH / columns - 5 * mm],
            )
            cell.setStyle(
                TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (-1, 0), 2.5, accent),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ]
                )
            )
            cells.append(cell)
        while len(cells) < columns:
            cells.append("")
        rows.append(cells)
    table = Table(rows, colWidths=[CONTENT_WIDTH / columns] * columns)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _styled_table(
    rows: list[list[Any]],
    widths: list[float],
    *,
    repeat_rows: int = 0,
    font_size: float = 7.6,
) -> LongTable:
    table = LongTable(rows, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    style_commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), font_size),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), SOFT))
    table.setStyle(TableStyle(style_commands))
    return table


def _bar_cell(percentage: float, color: Any) -> Table:
    filled = max(1, min(100, percentage)) if percentage else 0
    empty = 100 - filled
    widths = [max(filled, 1), max(empty, 1)]
    table = Table([["", ""]], colWidths=widths, rowHeights=[5])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), color if filled else LINE),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#EAECF0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _signal_label(pass_rate: float, styles: dict[str, ParagraphStyle]) -> Table:
    if pass_rate >= 75:
        label, color = "Healthy", GREEN
    elif pass_rate >= 50:
        label, color = "Review", AMBER
    else:
        label, color = "Difficult", RED
    table = Table([[Paragraph(label, styles["pill"])]], colWidths=[20 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _result_label(passed: bool, styles: dict[str, ParagraphStyle]) -> Table:
    color = GREEN if passed else RED
    label = "Passed" if passed else "Failed"
    table = Table([[Paragraph(label, styles["pill"])]], colWidths=[14 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _bullet_panel(
    title: str,
    items: list[str],
    background: Any,
    styles: dict[str, ParagraphStyle],
) -> Table:
    content: list[Any] = [Paragraph(escape(title.upper()), styles["metaLabel"])]
    content.extend(
        Paragraph(f"- {escape(item)}", styles["note"])
        for item in (items or ["No specific signal recorded."])
    )
    table = Table([[content]], colWidths=[CONTENT_WIDTH / 3 - 4 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _mono_paragraph(value: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    safe = escape(value or "-").replace("\n", "<br/>")
    return Paragraph(safe, styles["mono"])


def _meta_paragraph(value: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    text = escape(safe_text(value))
    if "@" in text and len(text) > 28:
        text = text.replace("@", "<br/>@", 1)
    return Paragraph(text, styles["metaValue"])


def _datetime_label(value: datetime | None) -> str:
    if value is None:
        return "Not available"
    return value.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _summarize(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if not text:
        return "Not available"
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 1)].rstrip()}..."


def _join_or_fallback(items: list[str], fallback: str = "Not available") -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    return "; ".join(cleaned) if cleaned else fallback


def _filter_review_items(items: list[str]) -> list[str]:
    return [
        item.strip()
        for item in items
        if item.strip()
        and not any(pattern.search(item) for pattern in STYLE_ONLY_REVIEW_PATTERNS)
    ]
