"""Tests for deterministic printable-report formatting."""

import unittest
from datetime import UTC, datetime

from core.services.report_formatting import (
    assessment_summary,
    duration_label,
    memory_label,
    numbered_code,
    question_analytics,
    safe_report_slug,
    schedule_label,
)
from schemas.evaluation import (
    AssessmentEvaluationOverview,
    CandidateEvaluationSummary,
    QuestionEvaluationBreakdown,
)


class ReportFormattingTest(unittest.TestCase):
    def test_safe_report_slug_removes_path_and_control_separators(self) -> None:
        self.assertEqual(
            safe_report_slug("../../Assessment: June 2026"),
            "assessment-june-2026",
        )
        self.assertEqual(safe_report_slug("///"), "report")

    def test_numbered_code_wraps_without_losing_line_numbers(self) -> None:
        rendered = numbered_code("alpha\n123456789", line_width=5)

        self.assertEqual(
            rendered.splitlines(),
            ["   1  alpha", "   2  12345", "      6789"],
        )

    def test_schedule_duration_and_memory_labels_handle_boundaries(self) -> None:
        start = datetime(2026, 6, 27, 9, 30, tzinfo=UTC)

        self.assertEqual(
            schedule_label(None, None, "UTC"),
            "Schedule not specified",
        )
        self.assertEqual(
            schedule_label(start, None, "Asia/Kolkata"),
            "27 Jun 2026 09:30 to Open (Asia/Kolkata)",
        )
        self.assertEqual(duration_label(None), "Not recorded")
        self.assertEqual(duration_label(-1), "0m 0s")
        self.assertEqual(duration_label(3661), "1h 1m 1s")
        self.assertEqual(memory_label(-10), "0 KB")
        self.assertEqual(memory_label(1536), "1.5 MB")

    def test_question_analytics_aggregates_and_sorts_report_rows(self) -> None:
        first = CandidateEvaluationSummary.model_construct(
            question_breakdown=[
                QuestionEvaluationBreakdown(
                    question_id="q-b",
                    question_title="Binary Search",
                    passed_count=3,
                    total_count=4,
                    earned_points=7.5,
                    total_points=10,
                    score=75,
                    mandatory_failed=False,
                ),
                QuestionEvaluationBreakdown(
                    question_id="q-a",
                    question_title="Array Rotation",
                    passed_count=2,
                    total_count=2,
                    earned_points=10,
                    total_points=10,
                    score=100,
                    mandatory_failed=False,
                ),
            ]
        )
        second = CandidateEvaluationSummary.model_construct(
            question_breakdown=[
                QuestionEvaluationBreakdown(
                    question_id="q-b",
                    question_title="Binary Search",
                    passed_count=1,
                    total_count=4,
                    earned_points=2.5,
                    total_points=10,
                    score=25,
                    mandatory_failed=False,
                )
            ]
        )

        rows = question_analytics([first, second])

        self.assertEqual(
            [row["title"] for row in rows],
            ["Array Rotation", "Binary Search"],
        )
        self.assertEqual(rows[1]["candidates"], 2)
        self.assertAlmostEqual(rows[1]["average_score"], 50)
        self.assertAlmostEqual(rows[1]["pass_rate"], 50)

    def test_assessment_summary_is_truthful_for_empty_and_completed(self) -> None:
        overview = AssessmentEvaluationOverview.model_construct(
            total_candidates=4,
            completed_candidates=3,
            average_score=78.25,
            pass_rate=66.7,
            highest_score=94.5,
        )

        self.assertTrue(
            assessment_summary(overview, []).startswith("No completed evaluations")
        )
        candidate = CandidateEvaluationSummary.model_construct(question_breakdown=[])
        summary = assessment_summary(overview, [candidate])
        self.assertIn("3 of 4 candidates", summary)
        self.assertIn("78.2%", summary)
        self.assertIn("94.5%", summary)


if __name__ == "__main__":
    unittest.main()
