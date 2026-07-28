"""Candidate invite and portal routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from api.rate_limit import limiter
from api.rest.dependencies import (
    get_assessment_service,
    get_current_candidate_session,
)
from core.services.assessments.assessment_service import AssessmentService
from schemas.assessments import HiddenCheckResponse, SampleRunResponse
from schemas.candidate_portal import (
    CandidateAssessmentPortalResponse,
    CandidateCheckpointRequest,
    CandidateCheckpointResponse,
    CandidateCodeRunRequest,
    CandidateInviteVerificationRequest,
    CandidateInviteVerificationResponse,
    CandidateProctorEventRequest,
    CandidateProctorEventResponse,
    CandidateSessionClaims,
    CandidateStartRequest,
    CandidateStartResponse,
    CandidateSubmitRequest,
    CandidateSubmitResponse,
)

router = APIRouter(prefix="/candidate", tags=["candidate"])


@router.post(
    "/verify-invite",
    response_model=CandidateInviteVerificationResponse,
    summary="Verify invite token",
    description="Validates an opaque candidate invite token before test start.",
)
@limiter.limit("10/minute")
async def verify_invite(
    request: Request,
    payload: CandidateInviteVerificationRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> CandidateInviteVerificationResponse:
    return await run_in_threadpool(service.verify_invite, payload.token)


@router.post(
    "/start",
    response_model=CandidateStartResponse,
    summary="Start candidate test",
    description="Starts a candidate session from a valid invite token.",
)
@limiter.limit("5/minute")
async def start_candidate(
    request: Request,
    payload: CandidateStartRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> CandidateStartResponse:
    return await run_in_threadpool(service.start_candidate_session, payload.token)


@router.get(
    "/assessment",
    response_model=CandidateAssessmentPortalResponse,
    summary="Load active candidate assessment",
    description="Loads the assessment visible to the authenticated candidate.",
)
async def get_assessment(
    claims: Annotated[
        CandidateSessionClaims,
        Depends(get_current_candidate_session),
    ],
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> CandidateAssessmentPortalResponse:
    return await run_in_threadpool(service.get_candidate_assessment, claims)


@router.post(
    "/checkpoint",
    response_model=CandidateCheckpointResponse,
    summary="Save candidate checkpoint",
    description="Persists a candidate answer draft during an active assessment.",
)
@limiter.limit("60/minute")
async def checkpoint(
    request: Request,
    claims: Annotated[
        CandidateSessionClaims,
        Depends(get_current_candidate_session),
    ],
    payload: CandidateCheckpointRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> CandidateCheckpointResponse:
    return await run_in_threadpool(service.save_checkpoint, claims, payload)


@router.post(
    "/proctoring-events",
    response_model=CandidateProctorEventResponse,
    summary="Record candidate proctoring event",
    description="Idempotently stores one violation and returns server-owned totals.",
)
@limiter.limit("120/minute")
async def record_proctor_event(
    request: Request,
    claims: Annotated[
        CandidateSessionClaims,
        Depends(get_current_candidate_session),
    ],
    payload: CandidateProctorEventRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> CandidateProctorEventResponse:
    return await run_in_threadpool(service.record_proctor_event, claims, payload)


@router.post(
    "/run-sample",
    response_model=SampleRunResponse,
    summary="Run sample test cases",
    description="Runs candidate code against public sample test cases.",
)
@limiter.limit("30/minute")
async def run_sample(
    request: Request,
    claims: Annotated[
        CandidateSessionClaims,
        Depends(get_current_candidate_session),
    ],
    payload: CandidateCodeRunRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> SampleRunResponse:
    return await run_in_threadpool(service.run_sample, claims, payload)


@router.post(
    "/hidden-check",
    response_model=HiddenCheckResponse,
    summary="Run hidden test summary",
    description="Runs hidden tests and returns an aggregate pass summary.",
)
@limiter.limit("5/minute")
async def hidden_check(
    request: Request,
    claims: Annotated[
        CandidateSessionClaims,
        Depends(get_current_candidate_session),
    ],
    payload: CandidateCodeRunRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> HiddenCheckResponse:
    return await run_in_threadpool(service.run_hidden_check, claims, payload)


@router.post(
    "/submit",
    response_model=CandidateSubmitResponse,
    summary="Submit candidate assessment",
    description="Finalizes the candidate assessment and records submissions.",
)
@limiter.limit("5/minute")
async def submit(
    request: Request,
    claims: Annotated[
        CandidateSessionClaims,
        Depends(get_current_candidate_session),
    ],
    payload: CandidateSubmitRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> CandidateSubmitResponse:
    return await run_in_threadpool(service.submit_assessment, claims, payload)
