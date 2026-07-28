"""How the rest of the platform reaches evaluation.

Two implementations behind one protocol:

* ``HttpEvaluationPort`` -- the original adapter, calling the evaluation service
  over HTTP. Kept indefinitely: it is what makes extracting this context back into
  its own deployable a configuration change rather than a rewrite.
* ``InProcessEvaluationPort`` -- calls ``EvaluationService`` directly.

``EVALUATION_TRANSPORT`` selects between them, so the switch is an environment
variable and the rollback needs no redeploy.

**On the two schema families.** The evaluation service speaks ``schemas.evaluation``
and the rest of the platform speaks ``schemas.evaluation_reports``. They are
parallel model trees -- ``CandidateEvaluationSummary`` against
``CandidateEvaluationScorecard``, and so on -- and core's are strict field subsets
with ``extra="ignore"``.

Rather than hand-map nineteen fields per model and hope the two stay aligned,
conversion goes through ``model_dump(mode="json")``: the exact primitive
representation the HTTP transport already puts on the wire and re-validates. The
two transports therefore produce identical objects by construction, not by
diligence, and ``tests/unit/test_evaluation_port_parity.py`` holds that true.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from config.settings import Settings
from core.exceptions.assessment import EvaluationResourceNotFoundError
from handlers.http_clients.evaluation import (
    EvaluationAdapterService,
    EvaluationReportDownload,
)
from schemas.evaluation_reports import (
    AssessmentEvaluationDashboard,
    AssessmentReportResponse,
    CandidateEvaluationScorecard,
    CandidateReportResponse,
    EvaluationJobResult,
    RetryEvaluationResponse,
)

T = TypeVar("T", bound=BaseModel)

#: Transport names accepted by ``EVALUATION_TRANSPORT``.
HTTP = "http"
IN_PROCESS = "inprocess"


def _as_core_model(source: BaseModel, target: type[T]) -> T:
    """Re-validate an evaluation-family model as its core-family counterpart.

    ``mode="json"`` matters: it renders enums as their values and datetimes as ISO
    strings, which is what the HTTP path receives. Dumping in Python mode would
    hand pydantic an ``EvaluationJobStatus`` where the core model declares ``str``.
    """

    return target.model_validate(source.model_dump(mode="json"))


#: Evaluation-domain "missing" errors. Over HTTP these become a 404 that the
#: adapter turns into EvaluationResourceNotFoundError; in-process they would
#: otherwise propagate raw. Callers in assessment_service catch the latter to
#: degrade gracefully when a candidate has no evaluation yet, so leaking the
#: originals turns a clean empty state into a 500.
_NOT_FOUND_ERRORS: tuple[type[Exception], ...] = ()


def _load_not_found_errors() -> tuple[type[Exception], ...]:
    from core.exceptions.evaluation import (
        AssessmentNotFoundError,
        EvaluationJobNotFoundError,
    )

    return (AssessmentNotFoundError, EvaluationJobNotFoundError)


@contextmanager
def _http_equivalent_errors() -> Iterator[None]:
    """Raise what the HTTP transport would have raised for the same failure."""

    global _NOT_FOUND_ERRORS
    if not _NOT_FOUND_ERRORS:
        _NOT_FOUND_ERRORS = _load_not_found_errors()
    try:
        yield
    except _NOT_FOUND_ERRORS as exc:
        raise EvaluationResourceNotFoundError(str(exc)) from exc


class EvaluationPort(Protocol):
    """The evaluation capability, independent of how it is reached."""

    def create_job(self, payload: dict[str, Any]) -> EvaluationJobResult: ...

    def get_leaderboard(
        self, assessment_id: str
    ) -> list[CandidateEvaluationScorecard]: ...

    def get_dashboard(self, assessment_id: str) -> AssessmentEvaluationDashboard: ...

    def get_assessment_report(self, assessment_id: str) -> AssessmentReportResponse: ...

    def get_candidate_report(
        self, assessment_id: str, candidate_assessment_id: str
    ) -> CandidateReportResponse: ...

    def retry_job(self, job_id: str) -> RetryEvaluationResponse: ...

    def download_assessment_report(
        self, assessment_id: str
    ) -> EvaluationReportDownload: ...

    def download_candidate_report(
        self, assessment_id: str, candidate_assessment_id: str
    ) -> EvaluationReportDownload: ...

    def download_test_report(
        self, assessment_id: str, test_id: str, payload: dict[str, Any]
    ) -> EvaluationReportDownload: ...


class InProcessEvaluationPort:
    """Call ``EvaluationService`` in this process.

    The service keeps its own repository and session scope. That is deliberate:
    submit-then-evaluate is two transactions today because it crosses a network
    boundary, and collapsing them into one would quietly change what a partial
    failure leaves behind on the candidate submit path.
    """

    def __init__(self, settings: Settings) -> None:
        # Imported here rather than at module scope: importing the evaluation
        # service pulls in reportlab and the whole PDF stack, which the execution
        # and gateway applications have no reason to load.
        from core.services.evaluation.evaluation_service import get_evaluation_service

        self._service = get_evaluation_service(
            settings.database_url,
            settings.evaluation_report_dir,
            settings.seed_demo_evaluations,
            settings.groq_api_key,
            settings.groq_base_url,
            settings.groq_model,
            settings.groq_request_timeout_seconds,
            settings.groq_retry_count,
            settings.groq_max_source_chars,
        )

    def create_job(self, payload: dict[str, Any]) -> EvaluationJobResult:
        """Create and process an evaluation job."""

        from schemas.evaluation import EvaluationJobCreateRequest

        request = EvaluationJobCreateRequest.model_validate(payload)
        with _http_equivalent_errors():
            return _as_core_model(
                self._service.create_job(request, process_inline=True),
                EvaluationJobResult,
            )

    def get_leaderboard(self, assessment_id: str) -> list[CandidateEvaluationScorecard]:
        """Return ranked scorecards for one assessment."""

        with _http_equivalent_errors():
            return [
                _as_core_model(item, CandidateEvaluationScorecard)
                for item in self._service.get_leaderboard(assessment_id)
            ]

    def get_dashboard(self, assessment_id: str) -> AssessmentEvaluationDashboard:
        """Return the recruiter evaluation workspace."""

        with _http_equivalent_errors():
            return _as_core_model(
                self._service.get_assessment_dashboard(assessment_id),
                AssessmentEvaluationDashboard,
            )

    def get_assessment_report(self, assessment_id: str) -> AssessmentReportResponse:
        """Return assessment-level report data."""

        with _http_equivalent_errors():
            return _as_core_model(
                self._service.get_assessment_report(assessment_id),
                AssessmentReportResponse,
            )

    def get_candidate_report(
        self, assessment_id: str, candidate_assessment_id: str
    ) -> CandidateReportResponse:
        """Return one candidate's scorecard."""

        with _http_equivalent_errors():
            return _as_core_model(
                self._service.get_candidate_report(
                    assessment_id, candidate_assessment_id
                ),
                CandidateReportResponse,
            )

    def retry_job(self, job_id: str) -> RetryEvaluationResponse:
        """Retry one failed evaluation job."""

        return _as_core_model(self._service.retry_job(job_id), RetryEvaluationResponse)

    def download_assessment_report(
        self, assessment_id: str
    ) -> EvaluationReportDownload:
        """Generate and read back the assessment PDF."""

        with _http_equivalent_errors():
            return self._read(
                self._service.generate_assessment_report_pdf(assessment_id)
            )

    def download_candidate_report(
        self, assessment_id: str, candidate_assessment_id: str
    ) -> EvaluationReportDownload:
        """Generate and read back one candidate scorecard PDF."""

        with _http_equivalent_errors():
            return self._read(
                self._service.generate_candidate_report_pdf(
                    assessment_id, candidate_assessment_id
                )
            )

    def download_test_report(
        self, assessment_id: str, test_id: str, payload: dict[str, Any]
    ) -> EvaluationReportDownload:
        """Generate and read back one scheduled-test PDF."""

        from schemas.evaluation import TestReportRequest

        request = TestReportRequest.model_validate({**payload, "test_id": test_id})
        with _http_equivalent_errors():
            return self._read(
                self._service.generate_test_report_pdf(assessment_id, request)
            )

    @staticmethod
    def _read(report: Any) -> EvaluationReportDownload:
        """Read a generated report off disk into the download envelope.

        Note this still requires the process serving the download to see the file.
        Compose shares ``EVALUATION_REPORT_DIR`` between the API and the worker;
        on Cloud Run those are separate revisions with separate disks. Generation
        happens in the request path here, so the file is local -- but moving
        generation to the worker would need shared storage first.
        """

        path = Path(report.path)
        return EvaluationReportDownload(
            content=path.read_bytes(),
            filename=report.filename,
            media_type=report.media_type,
        )


class HttpEvaluationPort(EvaluationAdapterService):
    """Call the evaluation service over HTTP.

    A thin alias over the original adapter so both transports are named
    consistently at the call site, and so the HTTP path stays obviously intact.
    """


def build_evaluation_port(settings: Settings) -> EvaluationPort:
    """Return the evaluation port selected by ``EVALUATION_TRANSPORT``."""

    if settings.evaluation_transport == IN_PROCESS:
        return InProcessEvaluationPort(settings)
    return HttpEvaluationPort(settings)


class EvaluationMaintenancePort(Protocol):
    """Queue upkeep, as distinct from serving a request.

    Separate from ``EvaluationPort`` because these are the worker's operations,
    not the platform's: nothing in a request path sweeps the queue or purges
    retention. Keeping them off the request-facing protocol stops a route
    acquiring the ability to do either by accident.
    """

    def process_pending_jobs(self, *, limit: int, lease_seconds: int) -> Any: ...

    def purge_expired_data(self, retention_days: int) -> tuple[int, int]: ...


class InProcessEvaluationMaintenancePort:
    """Run queue upkeep against ``EvaluationService`` in this process."""

    def __init__(self, settings: Settings) -> None:
        from core.services.evaluation.evaluation_service import get_evaluation_service

        self._service = get_evaluation_service(
            settings.database_url,
            settings.evaluation_report_dir,
            settings.seed_demo_evaluations,
            settings.groq_api_key,
            settings.groq_base_url,
            settings.groq_model,
            settings.groq_request_timeout_seconds,
            settings.groq_retry_count,
            settings.groq_max_source_chars,
        )

    def process_pending_jobs(self, *, limit: int, lease_seconds: int) -> Any:
        """Claim and process a bounded batch of pending jobs."""

        return self._service.process_pending_jobs(
            limit=limit, lease_seconds=lease_seconds
        )

    def purge_expired_data(self, retention_days: int) -> tuple[int, int]:
        """Delete evidence and report files past the retention window."""

        return self._service.purge_expired_data(retention_days)

    def process_job(self, job_id: str) -> Any:
        """Score one specific job."""

        with _http_equivalent_errors():
            return self._service.process_job(job_id)


def build_evaluation_maintenance_port(
    settings: Settings,
) -> EvaluationMaintenancePort:
    """Return the queue-upkeep port.

    Always in-process: sweeping and purging act on the job table directly and have
    no HTTP equivalent worth preserving -- the old worker did exactly this.
    """

    return InProcessEvaluationMaintenancePort(settings)
