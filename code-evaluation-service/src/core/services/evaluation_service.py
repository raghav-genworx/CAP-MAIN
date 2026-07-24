"""Business logic for candidate evaluation and recruiter scorecards."""

import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4

from core.exceptions.evaluation import (
    AssessmentNotFoundError,
    EvaluationJobNotFoundError,
    EvaluationRetryError,
)
from core.services.code_quality_evaluator import CodeQualityEvaluator
from core.services.report_pdf_service import GeneratedReport, ReportPdfService
from data.repositories.evaluation_repository import EvaluationRepository
from handlers.http_clients.groq_code_quality import GroqCodeQualityEvaluator
from schemas.evaluation import (
    AICodeQualitySignal,
    AssessmentEvaluationDashboard,
    AssessmentEvaluationOverview,
    AssessmentReportResponse,
    CandidateBenchmarkContext,
    CandidateEvaluationSummary,
    CandidateReportResponse,
    EvaluationJobCreateRequest,
    EvaluationJobResponse,
    EvaluationJobStatus,
    EvaluationScores,
    EvaluationWorkerRunResponse,
    ExecutionVerdict,
    HiddenExecutionResult,
    QuestionEvaluationBreakdown,
    QuestionSubmission,
    QuestionTestCaseResult,
    RetryEvaluationResponse,
    ScoringWeights,
    TestReportRequest,
    TestReportResponse,
)

LOGGER = logging.getLogger(__name__)

STYLE_ONLY_REVIEW_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcomments?\b",
        r"\bdocstrings?\b",
        r"\bvariable\s+nam(?:e|ing)\b",
        r"\bnaming\b",
        r"\brename\b",
        r"\bcamelcase\b",
        r"\bsnake_case\b",
        r"\bhelper\s+functions?\b",
        r"\bsplit\s+into\s+functions?\b",
        r"\bextract\s+(?:a\s+)?functions?\b",
        r"\bwrap\s+.*\bfunctions?\b",
        r"\bclasses?\b",
        r"\bclass-based\b",
        r"\bobject-oriented\b",
        r"\bmodulari[sz]e\b",
        r"\bformatting\b",
        r"\bindentation\b",
        r"\bcode\s+style\b",
    )
)


class EvaluationService:
    """Evaluate final submissions and maintain assessment scoreboards."""

    def __init__(
        self,
        repository: EvaluationRepository,
        report_pdf_service: ReportPdfService,
        *,
        seed_demo_data: bool = False,
        code_quality_evaluator: CodeQualityEvaluator | None = None,
    ) -> None:
        """Create an evaluation service backed by durable storage."""

        self._repository = repository
        self._report_pdf_service = report_pdf_service
        self._code_quality_evaluator = code_quality_evaluator
        if seed_demo_data:
            self._seed_demo_data()

    def create_job(
        self,
        request: EvaluationJobCreateRequest,
        *,
        process_inline: bool = True,
    ) -> EvaluationJobResponse:
        """Create an evaluation job and optionally process it immediately."""

        force = request.force
        request_payload = request.model_dump(mode="json", exclude={"force"})
        existing = self._repository.get_job_by_candidate_assessment(
            request.candidate_assessment_id
        )
        if existing is not None:
            if not force:
                return existing
            reset_job = existing.model_copy(
                update={
                    "status": EvaluationJobStatus.PENDING,
                    "attempt_count": existing.attempt_count + 1,
                    "error_message": None,
                    "result": None,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._repository.save_job(reset_job, request_payload=request_payload)
            if process_inline:
                return self.process_job(existing.job_id)
            return reset_job

        now = datetime.now(UTC)
        job = EvaluationJobResponse(
            job_id=f"eval_{uuid4().hex[:12]}",
            assessment_id=request.assessment_id,
            candidate_assessment_id=request.candidate_assessment_id,
            status=EvaluationJobStatus.PENDING,
            attempt_count=1,
            created_at=now,
            updated_at=now,
        )
        stored_job, created = self._repository.create_job_if_absent(
            job,
            request_payload,
        )
        if not created:
            return stored_job
        self._repository.save_assessment_title(
            request.assessment_id,
            "Coding Assessment Evaluation",
        )
        if process_inline:
            return self.process_job(job.job_id)
        return job

    def get_job(self, job_id: str) -> EvaluationJobResponse:
        """Return one evaluation job."""

        job = self._repository.get_job(job_id)
        if job is None:
            raise EvaluationJobNotFoundError(job_id)
        return job

    def retry_job(self, job_id: str) -> RetryEvaluationResponse:
        """Retry a failed evaluation job."""

        job = self.get_job(job_id)
        if job.status != EvaluationJobStatus.FAILED:
            raise EvaluationRetryError("Only failed evaluation jobs can be retried.")
        retried = job.model_copy(
            update={
                "status": EvaluationJobStatus.PENDING,
                "attempt_count": job.attempt_count + 1,
                "error_message": None,
                "updated_at": datetime.now(UTC),
            }
        )
        self._repository.save_job(retried)
        return RetryEvaluationResponse(
            job=self.process_job(job_id),
            message="Evaluation job retried successfully.",
        )

    def process_job(self, job_id: str) -> EvaluationJobResponse:
        """Process one queued evaluation job."""

        claimed = self._repository.claim_job(job_id)
        if claimed is None:
            job = self._repository.get_job(job_id)
            if job is None:
                raise EvaluationJobNotFoundError(job_id)
            raise EvaluationRetryError("Only pending evaluation jobs can be processed.")
        return self._process_job(job_id)

    def process_pending_jobs(
        self,
        limit: int = 20,
        *,
        lease_seconds: int = 300,
    ) -> EvaluationWorkerRunResponse:
        """Process queued evaluation jobs using the same scorer as the API path."""

        safe_limit = max(1, min(limit, 100))
        pending_jobs = self._repository.claim_pending_jobs(
            limit=safe_limit,
            lease_seconds=max(30, lease_seconds),
        )
        processed = [self._process_job(job.job_id) for job in pending_jobs]
        return EvaluationWorkerRunResponse(
            processed_count=len(processed),
            completed_count=sum(
                1 for job in processed if job.status == EvaluationJobStatus.COMPLETED
            ),
            failed_count=sum(
                1 for job in processed if job.status == EvaluationJobStatus.FAILED
            ),
            jobs=processed,
        )

    def purge_expired_data(self, retention_days: int) -> tuple[int, int]:
        """Purge expired terminal jobs and generated report artifacts."""

        cutoff = datetime.now(UTC) - timedelta(days=max(retention_days, 1))
        deleted_jobs = self._repository.purge_terminal_jobs_before(cutoff)
        deleted_reports = self._report_pdf_service.purge_generated_before(cutoff)
        return deleted_jobs, deleted_reports

    def get_assessment_dashboard(
        self,
        assessment_id: str,
    ) -> AssessmentEvaluationDashboard:
        """Return overview, leaderboard, and jobs for an assessment."""

        jobs = self._repository.list_jobs(assessment_id)
        if not jobs:
            raise AssessmentNotFoundError(assessment_id)
        completed = [
            job.result
            for job in jobs
            if job.status == EvaluationJobStatus.COMPLETED and job.result is not None
        ]
        try:
            leaderboard = self.get_leaderboard(assessment_id)
        except AssessmentNotFoundError:
            leaderboard = []
        overview = self._build_overview(assessment_id, completed, jobs)
        return AssessmentEvaluationDashboard(
            overview=overview,
            leaderboard=leaderboard,
            jobs=sorted(jobs, key=lambda item: item.created_at, reverse=True),
        )

    def get_leaderboard(self, assessment_id: str) -> list[CandidateEvaluationSummary]:
        """Return ranked completed evaluations for an assessment."""

        completed = [
            job.result
            for job in self._repository.list_jobs(assessment_id)
            if job.assessment_id == assessment_id
            and job.status == EvaluationJobStatus.COMPLETED
            and job.result is not None
        ]
        if not completed:
            raise AssessmentNotFoundError(assessment_id)
        ranked = sorted(
            completed,
            key=lambda item: (
                -item.scores.final_score,
                -item.scores.test_case_score,
                -item.scores.coding_score,
                item.total_execution_time_ms,
                item.peak_memory_kb,
                item.time_taken_seconds or 0,
                item.submitted_at,
            ),
        )
        return [
            item.model_copy(update={"rank": index + 1})
            for index, item in enumerate(ranked)
        ]

    def list_assessment_ids(self) -> list[str]:
        """Return assessment IDs that have evaluation activity."""

        return self._repository.list_assessment_ids()

    def get_assessment_report(self, assessment_id: str) -> AssessmentReportResponse:
        """Return the recruiter-ready assessment report payload."""

        dashboard = self.get_assessment_dashboard(assessment_id)
        return AssessmentReportResponse(
            overview=dashboard.overview,
            leaderboard=dashboard.leaderboard,
            generated_at=datetime.now(UTC),
            download_label=f"{dashboard.overview.title} evaluation report",
        )

    def generate_assessment_report_pdf(self, assessment_id: str) -> GeneratedReport:
        """Generate and return a downloadable assessment PDF report."""

        return self._report_pdf_service.assessment_report(
            self.get_assessment_report(assessment_id)
        )

    def get_candidate_report(
        self,
        assessment_id: str,
        candidate_assessment_id: str,
    ) -> CandidateReportResponse:
        """Return one candidate scorecard report."""

        candidate = next(
            (
                item
                for item in self.get_leaderboard(assessment_id)
                if item.candidate_assessment_id == candidate_assessment_id
            ),
            None,
        )
        if candidate is None:
            raise EvaluationJobNotFoundError(candidate_assessment_id)
        benchmark = self._candidate_benchmark(
            candidate,
            self.get_leaderboard(assessment_id),
        )
        return CandidateReportResponse(
            assessment_id=assessment_id,
            candidate_assessment_id=candidate_assessment_id,
            candidate=candidate,
            benchmark=benchmark,
            generated_at=datetime.now(UTC),
            download_label=f"{candidate.candidate_name} scorecard",
        )

    def generate_candidate_report_pdf(
        self,
        assessment_id: str,
        candidate_assessment_id: str,
    ) -> GeneratedReport:
        """Generate and return a downloadable candidate PDF scorecard."""

        return self._report_pdf_service.candidate_report(
            self.get_candidate_report(assessment_id, candidate_assessment_id)
        )

    def get_test_report(
        self,
        assessment_id: str,
        request: TestReportRequest,
    ) -> TestReportResponse:
        """Build a test-batch report from authorized candidate assignments."""

        candidate_ids = set(request.candidate_assessment_ids)
        jobs = [
            job
            for job in self._repository.list_jobs(assessment_id)
            if job.candidate_assessment_id in candidate_ids
        ]
        try:
            assessment_leaderboard = self.get_leaderboard(assessment_id)
        except AssessmentNotFoundError:
            assessment_leaderboard = []
        leaderboard = [
            candidate
            for candidate in assessment_leaderboard
            if candidate.candidate_assessment_id in candidate_ids
        ]
        leaderboard = [
            candidate.model_copy(update={"rank": index})
            for index, candidate in enumerate(leaderboard, start=1)
        ]
        overview = self._build_overview(assessment_id, leaderboard, jobs)
        unresolved_submissions = max(
            request.submitted_count - len(leaderboard) - overview.failed_jobs,
            0,
        )
        overview = overview.model_copy(
            update={
                "title": request.test_title,
                "total_candidates": request.candidate_count,
                "completed_candidates": len(leaderboard),
                "pending_jobs": max(overview.pending_jobs, unresolved_submissions),
            }
        )
        return TestReportResponse(
            assessment_id=assessment_id,
            test_id=request.test_id,
            test_title=request.test_title,
            timezone_name=request.timezone_name,
            scheduled_start=request.scheduled_start,
            scheduled_end=request.scheduled_end,
            submitted_count=request.submitted_count,
            overview=overview,
            leaderboard=leaderboard,
            generated_at=datetime.now(UTC),
            download_label=f"{request.test_title} test evaluation report",
        )

    def generate_test_report_pdf(
        self,
        assessment_id: str,
        request: TestReportRequest,
    ) -> GeneratedReport:
        """Generate a printable report for one scheduled test batch."""

        return self._report_pdf_service.test_report(
            self.get_test_report(assessment_id, request)
        )

    def _process_job(self, job_id: str) -> EvaluationJobResponse:
        request_payload = self._repository.get_request_payload(job_id)
        if request_payload is None:
            raise EvaluationRetryError("Evaluation job payload is unavailable.")
        request = EvaluationJobCreateRequest.model_validate(request_payload)
        job = self.get_job(job_id)
        if job.status != EvaluationJobStatus.PROCESSING:
            raise EvaluationRetryError("Claimed evaluation job is not processing.")
        processing = job
        try:
            result = self._evaluate(request)
        except Exception as exc:  # pragma: no cover - defensive status capture
            failed = processing.model_copy(
                update={
                    "status": EvaluationJobStatus.FAILED,
                    "error_message": str(exc),
                    "updated_at": datetime.now(UTC),
                }
            )
            self._repository.save_job(failed)
            return failed

        completed = processing.model_copy(
            update={
                "status": EvaluationJobStatus.COMPLETED,
                "result": result,
                "updated_at": datetime.now(UTC),
            }
        )
        self._repository.save_job(completed)
        self._repository.mark_report_ready(request.assessment_id)
        self._refresh_ranks(request.assessment_id)
        return self.get_job(job_id)

    def _evaluate(
        self,
        request: EvaluationJobCreateRequest,
    ) -> CandidateEvaluationSummary:
        question_submissions = self._question_submissions(request)
        question_breakdown = self._build_question_breakdown(
            request,
            question_submissions,
        )
        evaluated_question_ids = {
            item.question_id
            for item in question_breakdown
            if item.evaluation_status == "evaluated"
        }
        evaluated_results = [
            item
            for item in request.hidden_results
            if item.question_id in evaluated_question_ids
        ]
        hidden_passed = sum(1 for item in evaluated_results if item.passed)
        hidden_total = len(evaluated_results)
        total_time = round(
            sum(item.execution_time_ms or 0 for item in evaluated_results),
            2,
        )
        peak_memory = max(
            (item.memory_kb or 0 for item in evaluated_results),
            default=0,
        )
        total_marks = sum(item.assigned_marks for item in question_breakdown)
        test_case_score = self._marks_weighted_question_score(
            question_breakdown, "test_case_score", total_marks
        )
        coding_score = self._marks_weighted_question_score(
            question_breakdown, "coding_score", total_marks
        )
        ai_score = self._marks_weighted_question_score(
            question_breakdown, "ai_score", total_marks
        )
        final_score = (
            sum(item.score * item.assigned_marks for item in question_breakdown)
            / total_marks
            if total_marks
            else 0
        )
        ai_quality = self._aggregate_ai_quality(question_breakdown, ai_score)
        scores = EvaluationScores(
            test_case_score=round(test_case_score, 2),
            coding_score=round(coding_score, 2),
            ai_score=round(ai_score, 2),
            final_score=round(final_score, 2),
            percentage=round(final_score, 2),
        )
        return CandidateEvaluationSummary(
            assessment_id=request.assessment_id,
            candidate_assessment_id=request.candidate_assessment_id,
            candidate_id=request.candidate_id,
            candidate_name=request.candidate_name,
            candidate_email=request.candidate_email,
            submission_id=request.submission_id,
            language=request.language,
            status=EvaluationJobStatus.COMPLETED,
            scores=scores,
            hidden_passed=hidden_passed,
            hidden_total=hidden_total,
            weights=request.weights,
            total_execution_time_ms=total_time,
            peak_memory_kb=peak_memory,
            ai_quality=ai_quality,
            question_breakdown=question_breakdown,
            activity=request.activity,
            integrity=request.integrity,
            submitted_at=request.submitted_at,
            evaluated_at=datetime.now(UTC),
            time_taken_seconds=request.time_taken_seconds,
        )

    def _question_submissions(
        self,
        request: EvaluationJobCreateRequest,
    ) -> list[QuestionSubmission]:
        if request.question_submissions:
            return request.question_submissions

        grouped: dict[str, list[HiddenExecutionResult]] = defaultdict(list)
        for result in request.hidden_results:
            grouped[result.question_id].append(result)
        code_by_question = self._split_source_by_question(request.source_code)
        only_question_id = next(iter(grouped)) if len(grouped) == 1 else None
        return [
            QuestionSubmission(
                question_id=question_id,
                question_title=items[0].question_title,
                language=request.language,
                source_code=code_by_question.get(
                    question_id,
                    request.source_code if question_id == only_question_id else "",
                ),
                marks=sum(item.points for item in items),
            )
            for question_id, items in grouped.items()
        ]

    def _build_question_breakdown(
        self,
        request: EvaluationJobCreateRequest,
        submissions: list[QuestionSubmission],
    ) -> list[QuestionEvaluationBreakdown]:
        grouped: dict[str, list[HiddenExecutionResult]] = defaultdict(list)
        for result in request.hidden_results:
            grouped[result.question_id].append(result)

        breakdown: list[QuestionEvaluationBreakdown] = []
        answered_count = sum(1 for item in submissions if item.source_code.strip())
        for submission in submissions:
            question_id = submission.question_id
            items = grouped.get(question_id, [])
            if not submission.source_code.strip():
                breakdown.append(
                    QuestionEvaluationBreakdown(
                        question_id=question_id,
                        question_title=submission.question_title,
                        language=submission.language,
                        submitted_code="",
                        evaluation_status="not_attempted",
                        passed_count=0,
                        total_count=0,
                        earned_points=0,
                        total_points=submission.marks,
                        score=0,
                        assigned_marks=submission.marks,
                        earned_marks=0,
                        test_case_score=0,
                        coding_score=0,
                        ai_score=0,
                        ai_quality=None,
                        difficulty=submission.difficulty,
                        tags=submission.tags,
                        problem_statement=submission.problem_statement,
                        input_format=submission.input_format,
                        output_format=submission.output_format,
                        constraints=submission.constraints,
                        suggested_solution=submission.suggested_solution,
                        suggested_improvement_notes=submission.suggested_improvement_notes,
                        mandatory_failed=False,
                        test_cases=[],
                    )
                )
                continue

            total_points = sum(item.points for item in items)
            earned_points = sum(item.points for item in items if item.passed)
            test_case_score = self._test_case_score(items)
            coding_score = self._coding_score(items)
            ai_quality = self._resolve_question_ai_quality(
                request=request,
                submission=submission,
                test_case_score=test_case_score,
                coding_score=coding_score,
                use_request_quality=answered_count == 1,
            )
            score = self._weighted_score(
                test_case_score,
                coding_score,
                ai_quality.score,
                request.weights,
            )
            earned_marks = submission.marks * score / 100
            breakdown.append(
                QuestionEvaluationBreakdown(
                    question_id=question_id,
                    question_title=submission.question_title,
                    language=submission.language,
                    submitted_code=submission.source_code,
                    evaluation_status="evaluated",
                    passed_count=sum(1 for item in items if item.passed),
                    total_count=len(items),
                    earned_points=round(earned_points, 2),
                    total_points=round(total_points or submission.marks, 2),
                    score=round(score, 2),
                    assigned_marks=round(submission.marks, 2),
                    earned_marks=round(earned_marks, 2),
                    test_case_score=round(test_case_score, 2),
                    coding_score=round(coding_score, 2),
                    ai_score=round(ai_quality.score, 2),
                    ai_quality=ai_quality,
                    difficulty=submission.difficulty,
                    tags=submission.tags,
                    problem_statement=submission.problem_statement,
                    input_format=submission.input_format,
                    output_format=submission.output_format,
                    constraints=submission.constraints,
                    suggested_solution=submission.suggested_solution,
                    suggested_improvement_notes=submission.suggested_improvement_notes,
                    mandatory_failed=any(
                        item.mandatory and not item.passed for item in items
                    ),
                    test_cases=[
                        QuestionTestCaseResult(
                            test_case_id=item.test_case_id,
                            passed=item.passed,
                            verdict=item.verdict,
                            execution_time_ms=item.execution_time_ms,
                            memory_kb=item.memory_kb,
                            points=item.points,
                            mandatory=item.mandatory,
                            input=item.input,
                            expected_output=item.expected_output,
                            actual_output=item.actual_output,
                            message=item.message,
                            case_category=item.case_category,
                        )
                        for item in sorted(
                            items,
                            key=lambda result: result.test_case_id,
                        )
                    ],
                )
            )
        return sorted(breakdown, key=lambda item: item.question_title.lower())

    @staticmethod
    def _marks_weighted_question_score(
        breakdown: list[QuestionEvaluationBreakdown],
        field: str,
        total_marks: float,
    ) -> float:
        if total_marks <= 0:
            return 0
        return (
            sum(float(getattr(item, field)) * item.assigned_marks for item in breakdown)
            / total_marks
        )

    @staticmethod
    def _split_source_by_question(source_code: str) -> dict[str, str]:
        blocks: dict[str, list[str]] = {}
        current_question_id: str | None = None
        current_lines: list[str] = []

        for line in source_code.splitlines():
            if line.startswith("# Question ID:"):
                if current_question_id is not None:
                    blocks[current_question_id] = current_lines
                current_question_id = line.removeprefix("# Question ID:").strip()
                current_lines = []
                continue
            if line.startswith("# Question:"):
                continue
            if current_question_id is not None:
                current_lines.append(line)

        if current_question_id is not None:
            blocks[current_question_id] = current_lines

        return {
            question_id: "\n".join(lines).strip()
            for question_id, lines in blocks.items()
            if "\n".join(lines).strip()
        }

    @staticmethod
    def _test_case_score(results: list[HiddenExecutionResult]) -> float:
        total_points = sum(item.points for item in results)
        if total_points == 0:
            return 0
        earned_points = sum(item.points for item in results if item.passed)
        mandatory_failed = any(item.mandatory and not item.passed for item in results)
        raw_score = (earned_points / total_points) * 100
        return min(raw_score, 50) if mandatory_failed else raw_score

    @staticmethod
    def _coding_score(results: list[HiddenExecutionResult]) -> float:
        score = 100.0
        verdict_penalties = {
            ExecutionVerdict.COMPILE_ERROR: 35,
            ExecutionVerdict.RUNTIME_ERROR: 20,
            ExecutionVerdict.TIME_LIMIT_EXCEEDED: 18,
            ExecutionVerdict.MEMORY_LIMIT_EXCEEDED: 18,
            ExecutionVerdict.EXECUTION_FAILURE: 25,
            ExecutionVerdict.WRONG_ANSWER: 4,
            ExecutionVerdict.ACCEPTED: 0,
        }
        for result in results:
            if not result.passed:
                score -= verdict_penalties[result.verdict]
        average_time = _average([item.execution_time_ms for item in results])
        average_memory = _average([item.memory_kb for item in results])
        if average_time > 1800:
            score -= 8
        elif average_time > 900:
            score -= 4
        if average_memory > 180_000:
            score -= 8
        elif average_memory > 96_000:
            score -= 4
        return max(0, min(100, score))

    @staticmethod
    def _weighted_score(
        test_case_score: float,
        coding_score: float,
        ai_score: float,
        weights: ScoringWeights,
    ) -> float:
        return (
            test_case_score * weights.test_case_weight
            + coding_score * weights.coding_weight
            + ai_score * weights.ai_weight
        ) / 100

    def _resolve_question_ai_quality(
        self,
        *,
        request: EvaluationJobCreateRequest,
        submission: QuestionSubmission,
        test_case_score: float,
        coding_score: float,
        use_request_quality: bool,
    ) -> AICodeQualitySignal:
        if use_request_quality and request.ai_quality is not None:
            return _sanitize_ai_quality(request.ai_quality)
        if self._code_quality_evaluator is not None:
            try:
                return _sanitize_ai_quality(
                    self._code_quality_evaluator.evaluate(
                        language=submission.language,
                        source_code=submission.source_code,
                    )
                )
            except Exception as exc:
                LOGGER.warning(
                    "AI code-quality evaluation failed; using heuristic fallback "
                    "candidate_assessment_id=%s error_type=%s",
                    request.candidate_assessment_id,
                    type(exc).__name__,
                )
        return _sanitize_ai_quality(
            self._heuristic_ai_quality(
                submission.source_code,
                test_case_score,
                coding_score,
            )
        )

    @staticmethod
    def _aggregate_ai_quality(
        breakdown: list[QuestionEvaluationBreakdown],
        score: float,
    ) -> AICodeQualitySignal:
        qualities = [
            item.ai_quality for item in breakdown if item.ai_quality is not None
        ]
        if not qualities:
            return AICodeQualitySignal(
                score=0,
                approach="No answered questions were available for AI code review.",
                time_complexity="Not evaluated",
                space_complexity="Not evaluated",
                readability="Not evaluated",
                maintainability="Not evaluated",
                strengths=[],
                weaknesses=[],
                improvements=[],
            )

        def unique_values(attribute: str) -> list[str]:
            values: list[str] = []
            for quality in qualities:
                for value in _filter_review_items(getattr(quality, attribute)):
                    if value not in values:
                        values.append(value)
            return values[:6]

        return AICodeQualitySignal(
            score=round(score, 2),
            approach=f"Aggregated from {len(qualities)} question-level code reviews.",
            time_complexity="See each question's code-quality review.",
            space_complexity="See each question's code-quality review.",
            readability="Style-only factors are not evaluated.",
            maintainability="Style-only factors are not evaluated.",
            strengths=unique_values("strengths"),
            weaknesses=unique_values("weaknesses"),
            improvements=unique_values("improvements"),
        )

    @staticmethod
    def _heuristic_ai_quality(
        source_code: str,
        test_case_score: float,
        coding_score: float,
    ) -> AICodeQualitySignal:
        nesting_hits = source_code.count("for ") + source_code.count("while ")
        complexity_penalty = max(0, nesting_hits - 3) * 4
        complexity_score = max(0, 20 - complexity_penalty)
        score = max(
            0,
            min(
                100,
                (test_case_score * 0.45) + (coding_score * 0.35) + complexity_score,
            ),
        )
        return AICodeQualitySignal(
            score=round(score, 2),
            approach=(
                "Fallback quality estimate based on hidden correctness, execution "
                "stability, and loop complexity risk."
            ),
            time_complexity="Estimated from loop usage",
            space_complexity="Estimated from submitted memory evidence where available",
            readability="Style-only factors are not evaluated.",
            maintainability="Style-only factors are not evaluated.",
            strengths=[
                "Final score uses hidden execution evidence.",
                "Execution stability is included in the quality signal.",
            ],
            weaknesses=[
                "AI review was unavailable; this result uses heuristic analysis."
            ],
            improvements=["Re-run the evaluation when the AI reviewer is available."],
        )

    def _build_overview(
        self,
        assessment_id: str,
        completed: list[CandidateEvaluationSummary],
        jobs: list[EvaluationJobResponse],
    ) -> AssessmentEvaluationOverview:
        total = len(jobs)
        scores = [item.scores for item in completed]
        return AssessmentEvaluationOverview(
            assessment_id=assessment_id,
            title=self._repository.get_assessment_title(assessment_id),
            total_candidates=total,
            completed_candidates=len(completed),
            pending_jobs=sum(
                1
                for job in jobs
                if job.status
                in {EvaluationJobStatus.PENDING, EvaluationJobStatus.PROCESSING}
            ),
            failed_jobs=sum(
                1 for job in jobs if job.status == EvaluationJobStatus.FAILED
            ),
            average_score=round(_average([score.final_score for score in scores]), 2),
            average_test_case_score=round(
                _average([score.test_case_score for score in scores]),
                2,
            ),
            average_coding_score=round(
                _average([score.coding_score for score in scores]),
                2,
            ),
            average_ai_score=round(_average([score.ai_score for score in scores]), 2),
            pass_rate=round(
                (
                    sum(1 for score in scores if score.final_score >= 40)
                    / len(scores)
                    * 100
                )
                if scores
                else 0,
                2,
            ),
            highest_score=round(
                max((score.final_score for score in scores), default=0),
                2,
            ),
            report_status="ready" if completed else "pending",
            generated_at=datetime.now(UTC),
        )

    @staticmethod
    def _candidate_benchmark(
        candidate: CandidateEvaluationSummary,
        leaderboard: list[CandidateEvaluationSummary],
    ) -> CandidateBenchmarkContext:
        total = len(leaderboard)
        completion_times = [
            item.time_taken_seconds
            for item in leaderboard
            if item.time_taken_seconds is not None
        ]
        average_completion = (
            round(sum(completion_times) / len(completion_times))
            if completion_times
            else None
        )
        percentile = None
        if total:
            lower_or_equal = sum(
                1
                for item in leaderboard
                if item.scores.final_score <= candidate.scores.final_score
            )
            percentile = round(lower_or_equal / total * 100, 1)
        return CandidateBenchmarkContext(
            candidate_rank=candidate.rank,
            total_candidates=total,
            average_score=round(
                _average([item.scores.final_score for item in leaderboard]),
                2,
            )
            if leaderboard
            else None,
            average_completion_time_seconds=average_completion,
            percentile=percentile,
        )

    def _refresh_ranks(self, assessment_id: str) -> None:
        try:
            ranked = self.get_leaderboard(assessment_id)
        except AssessmentNotFoundError:
            return
        ranks_by_candidate = {
            item.candidate_assessment_id: item.rank for item in ranked
        }
        for job in self._repository.list_jobs(assessment_id):
            if job.assessment_id != assessment_id or job.result is None:
                continue
            rank = ranks_by_candidate.get(job.result.candidate_assessment_id)
            self._repository.save_job(
                job.model_copy(
                    update={"result": job.result.model_copy(update={"rank": rank})}
                )
            )

    def _seed_demo_data(self) -> None:
        """Provide a usable local dashboard before database wiring exists."""

        if self._repository.has_jobs():
            return
        self._repository.save_assessment_title(
            "assessment_algorithms_june",
            "Backend Engineer Screening - June",
        )
        samples = [
            (
                "cand_001",
                "Aarav Mehta",
                "aarav.mehta@example.com",
                9,
                10,
                78,
                44_000,
                3280,
            ),
            (
                "cand_002",
                "Isha Raman",
                "isha.raman@example.com",
                8,
                10,
                91,
                51_000,
                4020,
            ),
            (
                "cand_003",
                "Kabir Nair",
                "kabir.nair@example.com",
                6,
                10,
                84,
                83_000,
                4760,
            ),
        ]
        for index, sample in enumerate(samples, start=1):
            candidate_id, name, email, passed, total, ai, memory, taken = sample
            results = [
                HiddenExecutionResult(
                    question_id="q_arrays",
                    question_title="Minimum Window Score",
                    test_case_id=f"q_arrays_{case}",
                    passed=case <= min(passed, 5),
                    verdict=(
                        ExecutionVerdict.ACCEPTED
                        if case <= min(passed, 5)
                        else ExecutionVerdict.WRONG_ANSWER
                    ),
                    execution_time_ms=120 + case * 18 + index * 10,
                    memory_kb=memory,
                    points=1,
                    mandatory=case == 1,
                )
                for case in range(1, 6)
            ] + [
                HiddenExecutionResult(
                    question_id="q_graphs",
                    question_title="Delivery Route Planner",
                    test_case_id=f"q_graphs_{case}",
                    passed=case <= max(0, passed - 5),
                    verdict=(
                        ExecutionVerdict.ACCEPTED
                        if case <= max(0, passed - 5)
                        else ExecutionVerdict.TIME_LIMIT_EXCEEDED
                    ),
                    execution_time_ms=240 + case * 31 + index * 15,
                    memory_kb=memory + 12_000,
                    points=1,
                    mandatory=case == 1,
                )
                for case in range(1, total - 4)
            ]
            request = EvaluationJobCreateRequest(
                assessment_id="assessment_algorithms_june",
                candidate_assessment_id=f"ca_{index:03d}",
                candidate_id=candidate_id,
                candidate_name=name,
                candidate_email=email,
                submission_id=f"sub_{index:03d}",
                language="Python 3",
                source_code="def solve():\n    pass\n\nsolve()\n",
                hidden_results=results,
                ai_quality=AICodeQualitySignal(
                    score=ai,
                    approach="Uses a direct algorithm with clear control flow.",
                    time_complexity="O(n log n)",
                    space_complexity="O(n)",
                    readability="Style-only factors are not evaluated.",
                    maintainability="Style-only factors are not evaluated.",
                    strengths=["Clear implementation", "Handles most hidden cases"],
                    weaknesses=["Needs stronger edge-case handling"],
                    improvements=["Add boundary checks for sparse inputs"],
                ),
                time_taken_seconds=taken,
            )
            self.create_job(request)
        self._repository.save_assessment_title(
            "assessment_algorithms_june",
            "Backend Engineer Screening - June",
        )


def _sanitize_ai_quality(quality: AICodeQualitySignal) -> AICodeQualitySignal:
    return quality.model_copy(
        update={
            "readability": "Style-only factors are not evaluated.",
            "maintainability": "Style-only factors are not evaluated.",
            "strengths": _filter_review_items(quality.strengths),
            "weaknesses": _filter_review_items(quality.weaknesses),
            "improvements": _filter_review_items(quality.improvements),
        }
    )


def _filter_review_items(items: list[str]) -> list[str]:
    return [
        item.strip()
        for item in items
        if item.strip()
        and not any(pattern.search(item) for pattern in STYLE_ONLY_REVIEW_PATTERNS)
    ]


def _average(values: list[float | int | None]) -> float:
    clean_values = [float(value) for value in values if value is not None]
    return sum(clean_values) / len(clean_values) if clean_values else 0


@lru_cache
def get_evaluation_service(
    database_url: str = (
        "postgresql+psycopg://cap_user:cap_password@localhost:55432/cap_core"
    ),
    report_dir: str = "data/reports",
    seed_demo_data: bool = False,
    groq_api_key: str = "",
    groq_base_url: str = "https://api.groq.com/openai/v1",
    groq_model: str = "llama-3.3-70b-versatile",
    groq_request_timeout_seconds: float = 60,
    groq_retry_count: int = 3,
    groq_max_source_chars: int = 80_000,
) -> EvaluationService:
    """Return a process-local evaluation service backed by durable storage."""

    code_quality_evaluator = None
    if groq_api_key.strip():
        code_quality_evaluator = GroqCodeQualityEvaluator(
            api_key=groq_api_key,
            base_url=groq_base_url,
            model=groq_model,
            timeout_seconds=groq_request_timeout_seconds,
            retry_count=groq_retry_count,
            max_source_chars=groq_max_source_chars,
        )
    return EvaluationService(
        EvaluationRepository(database_url),
        ReportPdfService(report_dir),
        seed_demo_data=seed_demo_data,
        code_quality_evaluator=code_quality_evaluator,
    )
