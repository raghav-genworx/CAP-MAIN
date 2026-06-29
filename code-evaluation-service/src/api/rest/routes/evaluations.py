"""Evaluation job and recruiter report routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from api.rest.dependencies import (
    evaluation_service_dependency,
    require_internal_service,
)
from core.services.evaluation_service import EvaluationService
from schemas.evaluation import (
    AssessmentEvaluationDashboard,
    AssessmentReportResponse,
    CandidateEvaluationSummary,
    CandidateReportResponse,
    EvaluationJobCreateRequest,
    EvaluationJobResponse,
    EvaluationWorkerRunResponse,
    RetryEvaluationResponse,
    TestReportRequest,
)

router = APIRouter(
    prefix="/evaluations",
    tags=["evaluations"],
    dependencies=[Depends(require_internal_service)],
)


@router.post(
    "/jobs",
    response_model=EvaluationJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an evaluation job",
    description="Scores a final submission from hidden execution results.",
)
async def create_evaluation_job(
    request: EvaluationJobCreateRequest,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
    process_inline: bool = True,
) -> EvaluationJobResponse:
    """Create and process an evaluation job."""

    return service.create_job(request, process_inline=process_inline)


@router.get(
    "/jobs/{job_id}",
    response_model=EvaluationJobResponse,
    summary="Get an evaluation job",
    description="Returns status and scorecard output for one evaluation job.",
)
async def get_evaluation_job(
    job_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> EvaluationJobResponse:
    """Return a single evaluation job."""

    return service.get_job(job_id)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=RetryEvaluationResponse,
    summary="Retry a failed evaluation job",
    description="Re-runs a failed job and updates score, rank, and report state.",
)
async def retry_evaluation_job(
    job_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> RetryEvaluationResponse:
    """Retry a failed evaluation job."""

    return service.retry_job(job_id)


@router.post(
    "/jobs/{job_id}/process",
    response_model=EvaluationJobResponse,
    summary="Process an evaluation job",
    description="Runs scoring for one queued evaluation job.",
)
async def process_evaluation_job(
    job_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> EvaluationJobResponse:
    """Process one evaluation job."""

    return service.process_job(job_id)


@router.post(
    "/worker/process-pending",
    response_model=EvaluationWorkerRunResponse,
    summary="Process pending evaluation jobs",
    description="Processes a bounded batch of queued evaluation jobs.",
)
async def process_pending_evaluation_jobs(
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EvaluationWorkerRunResponse:
    """Process pending jobs for a worker or operational backfill."""

    return service.process_pending_jobs(limit=limit)


@router.get(
    "/assessment/{assessment_id}",
    response_model=AssessmentEvaluationDashboard,
    summary="Get assessment evaluation dashboard",
    description="Returns evaluation KPIs, leaderboard, jobs, and scorecards.",
)
async def get_assessment_evaluation_dashboard(
    assessment_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> AssessmentEvaluationDashboard:
    """Return the recruiter evaluation dashboard for an assessment."""

    return service.get_assessment_dashboard(assessment_id)


@router.get(
    "/assessment/{assessment_id}/leaderboard",
    response_model=list[CandidateEvaluationSummary],
    summary="Get assessment leaderboard",
    description="Returns ranked candidates using the configured tie-breakers.",
)
async def get_assessment_leaderboard(
    assessment_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> list[CandidateEvaluationSummary]:
    """Return ranked candidate evaluations."""

    return service.get_leaderboard(assessment_id)


@router.get(
    "/reports/assessment/{assessment_id}",
    response_model=AssessmentReportResponse,
    summary="Get assessment report",
    description="Returns assessment summary, leaderboard, and report metadata.",
)
async def get_assessment_report(
    assessment_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> AssessmentReportResponse:
    """Return an assessment report payload."""

    return service.get_assessment_report(assessment_id)


@router.get(
    "/reports/assessment/{assessment_id}/download",
    response_class=FileResponse,
    summary="Download assessment PDF report",
    description="Generates and downloads the assessment evaluation report PDF.",
)
async def download_assessment_report(
    assessment_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> FileResponse:
    """Download an assessment PDF report."""

    report = service.generate_assessment_report_pdf(assessment_id)
    return FileResponse(
        path=report.path,
        filename=report.filename,
        media_type=report.media_type,
    )


@router.get(
    "/reports/assessment/{assessment_id}/candidate/{candidate_assessment_id}",
    response_model=CandidateReportResponse,
    summary="Get candidate scorecard report",
    description="Returns one candidate's final scorecard report payload.",
)
async def get_candidate_report(
    assessment_id: str,
    candidate_assessment_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> CandidateReportResponse:
    """Return one candidate report payload."""

    return service.get_candidate_report(assessment_id, candidate_assessment_id)


@router.get(
    "/reports/assessment/{assessment_id}/candidate/{candidate_assessment_id}/download",
    response_class=FileResponse,
    summary="Download candidate scorecard PDF",
    description="Generates and downloads one candidate's scorecard PDF.",
)
async def download_candidate_report(
    assessment_id: str,
    candidate_assessment_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> FileResponse:
    """Download a candidate scorecard PDF."""

    report = service.generate_candidate_report_pdf(
        assessment_id,
        candidate_assessment_id,
    )
    return FileResponse(
        path=report.path,
        filename=report.filename,
        media_type=report.media_type,
    )


@router.post(
    "/reports/assessment/{assessment_id}/tests/{test_id}/download",
    response_class=FileResponse,
    summary="Download scheduled test evaluation PDF",
    description="Generates a report scoped to one authorized test batch.",
)
async def download_test_report(
    request: TestReportRequest,
    assessment_id: str,
    test_id: str,
    service: Annotated[
        EvaluationService,
        Depends(evaluation_service_dependency),
    ],
) -> FileResponse:
    """Download a scheduled test-batch evaluation report."""

    normalized_request = request.model_copy(update={"test_id": test_id})
    report = service.generate_test_report_pdf(assessment_id, normalized_request)
    return FileResponse(
        path=report.path,
        filename=report.filename,
        media_type=report.media_type,
    )
