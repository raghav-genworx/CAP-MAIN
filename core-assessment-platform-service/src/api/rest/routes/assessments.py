"""Assessment recruiter routes."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from api.rest.dependencies import get_assessment_service, require_role
from core.services.assessment_service import AssessmentService
from schemas.assessments import (
    AssessmentCreateRequest,
    AssessmentListResponse,
    AssessmentQuestionAssignRequest,
    AssessmentRecord,
    AssessmentSlotActionRequest,
    AssessmentSlotCreateRequest,
    AssessmentSlotListResponse,
    AssessmentSlotRecord,
    AssessmentSlotUpdateRequest,
    AssessmentUpdateRequest,
    CandidateCSVImportRequest,
    CandidateImportResponse,
    EvaluationBackfillRequest,
    EvaluationBackfillResponse,
    InviteDispatchRequest,
    InviteDispatchResponse,
    MonitoringResponse,
    SlotCandidateListResponse,
)
from schemas.auth import AuthenticatedUser
from schemas.evaluation_reports import (
    AssessmentEvaluationDashboard,
    AssessmentReportResponse,
    CandidateReportResponse,
    RetryEvaluationResponse,
)
from schemas.roles import UserRole

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.get(
    "",
    response_model=AssessmentListResponse,
    summary="List assessments",
    description="Returns all assessments owned by the authenticated recruiter.",
)
async def list_assessments(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> AssessmentListResponse:
    return await run_in_threadpool(service.list_assessments, current_user.uid)


@router.post(
    "",
    response_model=AssessmentRecord,
    summary="Create assessment",
    description="Creates a recruiter-owned assessment template.",
)
async def create_assessment(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: AssessmentCreateRequest,
) -> AssessmentRecord:
    return await run_in_threadpool(service.create_assessment, current_user.uid, payload)


@router.patch(
    "/{assessment_id}",
    response_model=AssessmentRecord,
    summary="Update assessment",
    description="Updates editable assessment metadata for the owning recruiter.",
)
async def update_assessment(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: AssessmentUpdateRequest,
    assessment_id: str = Path(min_length=1),
) -> AssessmentRecord:
    return await run_in_threadpool(
        service.update_assessment,
        current_user.uid,
        assessment_id,
        payload,
    )


@router.delete(
    "/{assessment_id}",
    status_code=204,
    summary="Delete assessment",
    description="Permanently deletes a recruiter-owned assessment template.",
)
async def delete_assessment(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
) -> Response:
    await run_in_threadpool(service.delete_assessment, current_user.uid, assessment_id)
    return Response(status_code=204)


@router.post(
    "/{assessment_id}/questions",
    response_model=AssessmentRecord,
    summary="Replace assessment questions",
    description="Replaces the ordered question set and scoring weights.",
)
async def set_assessment_questions(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: AssessmentQuestionAssignRequest,
    assessment_id: str = Path(min_length=1),
) -> AssessmentRecord:
    return await run_in_threadpool(
        service.set_assessment_questions,
        current_user.uid,
        assessment_id,
        payload,
    )


@router.post(
    "/{assessment_id}/slots",
    response_model=AssessmentSlotRecord,
    summary="Create assessment slot",
    description="Creates a scheduled delivery slot for an assessment.",
)
async def create_slot(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: AssessmentSlotCreateRequest,
    assessment_id: str = Path(min_length=1),
) -> AssessmentSlotRecord:
    return await run_in_threadpool(
        service.create_slot,
        current_user.uid,
        assessment_id,
        payload,
    )


@router.patch(
    "/slots/{slot_id}",
    response_model=AssessmentSlotRecord,
    summary="Update assessment slot",
    description="Updates slot scheduling and delivery metadata.",
)
async def update_slot(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: AssessmentSlotUpdateRequest,
    slot_id: str = Path(min_length=1),
) -> AssessmentSlotRecord:
    return await run_in_threadpool(
        service.update_slot,
        current_user.uid,
        slot_id,
        payload,
    )


@router.post(
    "/slots/{slot_id}/actions",
    response_model=AssessmentSlotRecord,
    summary="Pause, continue, extend, or close assessment slot",
    description="Applies an operational action to an assessment slot.",
)
async def control_slot(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: AssessmentSlotActionRequest,
    slot_id: str = Path(min_length=1),
) -> AssessmentSlotRecord:
    return await run_in_threadpool(
        service.control_slot,
        current_user.uid,
        slot_id,
        payload,
    )


@router.get(
    "/{assessment_id}/slots",
    response_model=AssessmentSlotListResponse,
    summary="List assessment slots",
    description="Returns delivery slots for a recruiter-owned assessment.",
)
async def list_slots(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
) -> AssessmentSlotListResponse:
    return await run_in_threadpool(service.list_slots, current_user.uid, assessment_id)


@router.post(
    "/slots/{slot_id}/candidates/import",
    response_model=CandidateImportResponse,
    summary="Import slot candidates",
    description="Imports candidates from parsed CSV text into an assessment slot.",
)
async def import_slot_candidates(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: CandidateCSVImportRequest,
    slot_id: str = Path(min_length=1),
) -> CandidateImportResponse:
    return await run_in_threadpool(
        service.import_slot_candidates,
        current_user.uid,
        slot_id,
        payload,
    )


@router.get(
    "/slots/{slot_id}/candidates",
    response_model=SlotCandidateListResponse,
    summary="List slot candidates",
    description="Returns candidates assigned to a recruiter-owned assessment slot.",
)
async def list_slot_candidates(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    slot_id: str = Path(min_length=1),
) -> SlotCandidateListResponse:
    return await run_in_threadpool(
        service.list_slot_candidates,
        current_user.uid,
        slot_id,
    )


@router.post(
    "/{assessment_id}/evaluations/backfill",
    response_model=EvaluationBackfillResponse,
    summary="Backfill evaluation jobs",
    description=(
        "Creates evaluation jobs for previously submitted candidate assessments "
        "that already have stored final hidden execution evidence."
    ),
)
async def backfill_assessment_evaluations(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: EvaluationBackfillRequest | None = None,
    assessment_id: str = Path(min_length=1),
) -> EvaluationBackfillResponse:
    backfill_payload = payload or EvaluationBackfillRequest()
    return await run_in_threadpool(
        service.backfill_evaluations,
        current_user.uid,
        assessment_id,
        backfill_payload,
    )


@router.get(
    "/{assessment_id}/evaluations/dashboard",
    response_model=AssessmentEvaluationDashboard,
    summary="Get the recruiter evaluation dashboard",
    description="Returns evaluation analytics for a recruiter-owned assessment.",
)
async def get_evaluation_dashboard(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
) -> AssessmentEvaluationDashboard:
    return await run_in_threadpool(
        service.get_evaluation_dashboard,
        current_user.uid,
        assessment_id,
    )


@router.post(
    "/{assessment_id}/evaluations/jobs/{job_id}/retry",
    response_model=RetryEvaluationResponse,
    summary="Retry a failed evaluation job",
    description="Retries a job belonging to a recruiter-owned assessment.",
)
async def retry_evaluation_job(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
    job_id: str = Path(min_length=1),
) -> RetryEvaluationResponse:
    return await run_in_threadpool(
        service.retry_evaluation_job,
        current_user.uid,
        assessment_id,
        job_id,
    )


@router.get(
    "/{assessment_id}/evaluations/reports",
    response_model=AssessmentReportResponse,
    summary="Get assessment evaluation report data",
    description="Returns report-ready assessment analytics and leaderboard data.",
)
async def get_evaluation_report(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
) -> AssessmentReportResponse:
    return await run_in_threadpool(
        service.get_evaluation_report,
        current_user.uid,
        assessment_id,
    )


@router.get(
    "/{assessment_id}/evaluations/reports/download",
    response_class=Response,
    summary="Download assessment evaluation report PDF",
    description="Downloads the recruiter-facing assessment report as a PDF.",
)
async def download_evaluation_report(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
) -> Response:
    report = await run_in_threadpool(
        service.download_evaluation_report,
        current_user.uid,
        assessment_id,
    )
    return Response(
        content=report.content,
        media_type=report.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
        },
    )


@router.get(
    "/{assessment_id}/evaluations/reports/candidates/{candidate_assessment_id}",
    response_model=CandidateReportResponse,
    summary="Get candidate evaluation scorecard",
    description="Returns one candidate scorecard for a recruiter-owned assessment.",
)
async def get_candidate_evaluation_report(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
    candidate_assessment_id: str = Path(min_length=1),
) -> CandidateReportResponse:
    return await run_in_threadpool(
        service.get_candidate_evaluation_report,
        current_user.uid,
        assessment_id,
        candidate_assessment_id,
    )


@router.get(
    "/{assessment_id}/evaluations/reports/candidates/"
    "{candidate_assessment_id}/download",
    response_class=Response,
    summary="Download candidate scorecard PDF",
    description="Downloads one candidate evaluation scorecard as a PDF.",
)
async def download_candidate_evaluation_report(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
    candidate_assessment_id: str = Path(min_length=1),
) -> Response:
    report = await run_in_threadpool(
        service.download_candidate_evaluation_report,
        current_user.uid,
        assessment_id,
        candidate_assessment_id,
    )
    return Response(
        content=report.content,
        media_type=report.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
        },
    )


@router.get(
    "/{assessment_id}/evaluations/reports/tests/{slot_id}/download",
    response_class=Response,
    summary="Download scheduled test evaluation report PDF",
    description="Downloads evaluation results for one scheduled assessment slot.",
)
async def download_test_evaluation_report(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    assessment_id: str = Path(min_length=1),
    slot_id: str = Path(min_length=1),
) -> Response:
    report = await run_in_threadpool(
        service.download_test_evaluation_report,
        current_user.uid,
        assessment_id,
        slot_id,
    )
    return Response(
        content=report.content,
        media_type=report.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
        },
    )


@router.post(
    "/slots/{slot_id}/invites/send",
    response_model=InviteDispatchResponse,
    summary="Send slot invites",
    description="Dispatches assessment invite emails to selected slot candidates.",
)
async def send_slot_invites(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    payload: InviteDispatchRequest | None = None,
    slot_id: str = Path(min_length=1),
) -> InviteDispatchResponse:
    dispatch_payload = payload or InviteDispatchRequest()
    return await run_in_threadpool(
        service.send_slot_invites,
        current_user.uid,
        slot_id,
        candidate_assessment_ids=dispatch_payload.candidate_assessment_ids,
    )


@router.post(
    "/candidate-assessments/{candidate_assessment_id}/invite/resend",
    response_model=InviteDispatchResponse,
    summary="Resend one candidate invite",
    description="Regenerates and sends an invite for one candidate assessment.",
)
async def resend_candidate_invite(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    candidate_assessment_id: str = Path(min_length=1),
) -> InviteDispatchResponse:
    assignment = await run_in_threadpool(
        service.get_candidate_assignment,
        current_user.uid,
        candidate_assessment_id,
    )
    return await run_in_threadpool(
        service.send_slot_invites,
        current_user.uid,
        assignment.slot_id,
        candidate_assessment_id,
    )


@router.get(
    "/slots/{slot_id}/monitoring",
    response_model=MonitoringResponse,
    summary="Assessment slot monitoring",
    description="Returns live monitoring metrics for a recruiter-owned slot.",
)
async def slot_monitoring(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    slot_id: str = Path(min_length=1),
) -> MonitoringResponse:
    return await run_in_threadpool(service.monitoring, current_user.uid, slot_id)


@router.get(
    "/slots/{slot_id}/monitoring/stream",
    summary="Stream assessment slot monitoring",
    description="Streams recruiter-visible monitoring updates for a slot.",
)
async def slot_monitoring_stream(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    slot_id: str = Path(min_length=1),
) -> StreamingResponse:
    initial_payload = await run_in_threadpool(
        service.monitoring,
        current_user.uid,
        slot_id,
    )

    async def monitoring_events():
        last_payload = initial_payload.model_dump_json()
        yield f"event: monitoring\ndata: {last_payload}\n\n"

        while not await request.is_disconnected():
            await asyncio.sleep(3)
            payload = await run_in_threadpool(
                service.monitoring,
                current_user.uid,
                slot_id,
            )
            serialized = payload.model_dump_json()
            if serialized == last_payload:
                yield "event: heartbeat\ndata: {}\n\n"
                continue

            last_payload = serialized
            yield f"event: monitoring\ndata: {serialized}\n\n"

    return StreamingResponse(
        monitoring_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
