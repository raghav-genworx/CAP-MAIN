"""Tests for deterministic printable-report formatting."""

import unittest
from datetime import UTC, datetime

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
    AssessmentEvaluationOverview,
    CandidateEvaluationSummary,
    CandidateIntegritySignal,
    EvaluationScores,
    QuestionEvaluationBreakdown,
    ScoringWeights,
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

    def test_safe_labels_and_score_breakdown_are_recruiter_ready(self) -> None:
        rows = score_breakdown_rows(
            EvaluationScores(
                test_case_score=75,
                coding_score=80,
                ai_score=60,
                final_score=73,
                percentage=73,
            ),
            ScoringWeights(test_case_weight=60, coding_weight=20, ai_weight=20),
        )

        self.assertEqual(safe_text(""), "Not available")
        self.assertEqual(hidden_case_label(2), "Case 2")
        self.assertEqual(rows[0]["component"], "Hidden test correctness")
        self.assertEqual(rows[0]["weighted_score"], 45)

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

    def test_recruiter_recommendation_uses_score_and_integrity_signals(self) -> None:
        strong = CandidateEvaluationSummary.model_construct(
            scores=EvaluationScores(
                test_case_score=95,
                coding_score=90,
                ai_score=85,
                final_score=91,
                percentage=91,
            ),
            hidden_passed=9,
            hidden_total=10,
            integrity=CandidateIntegritySignal(),
        )
        failed = CandidateEvaluationSummary.model_construct(
            scores=EvaluationScores(
                test_case_score=30,
                coding_score=55,
                ai_score=65,
                final_score=37,
                percentage=37,
            ),
            hidden_passed=3,
            hidden_total=10,
            integrity=CandidateIntegritySignal(),
        )
        flagged = CandidateEvaluationSummary.model_construct(
            scores=EvaluationScores(
                test_case_score=90,
                coding_score=90,
                ai_score=90,
                final_score=90,
                percentage=90,
            ),
            hidden_passed=9,
            hidden_total=10,
            integrity=CandidateIntegritySignal(
                suspicious_activity=["Fullscreen exit detected"]
            ),
        )

        self.assertEqual(recruiter_recommendation(strong)["label"], "Strong Hire")
        self.assertEqual(recruiter_recommendation(failed)["label"], "Reject")
        self.assertEqual(
            recruiter_recommendation(flagged)["label"],
            "Manual Review Required",
        )


if __name__ == "__main__":
    unittest.main()
