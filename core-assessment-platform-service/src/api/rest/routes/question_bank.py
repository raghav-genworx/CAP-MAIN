"""Question bank routes."""

import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from api.rest.dependencies import (
    get_question_bank_service,
    require_role,
)
from api.rest.routes import sse
from core.services.question_bank.question_bank_service import (
    QuestionBankService,
    QuestionFilters,
    QuestionGroupFilters,
)
from schemas.auth import AuthenticatedUser
from schemas.question_bank import (
    DifficultyLevel,
    QuestionAIDraftRequest,
    QuestionAIDraftResponse,
    QuestionBulkImportRequest,
    QuestionBulkImportResponse,
    QuestionCreateRequest,
    QuestionDraftRefinementRequest,
    QuestionDraftRefinementResponse,
    QuestionDraftValidationRequest,
    QuestionDraftValidationResponse,
    QuestionGroupCreateRequest,
    QuestionGroupListResponse,
    QuestionGroupRecord,
    QuestionGroupStatus,
    QuestionGroupUpdateRequest,
    QuestionListResponse,
    QuestionRecord,
    QuestionStatus,
    QuestionUpdateRequest,
)
from schemas.roles import UserRole

router = APIRouter(prefix="/question-bank", tags=["question-bank"])


@router.get(
    "/questions",
    response_model=QuestionListResponse,
    summary="List recruiter questions",
    description="Returns recruiter-owned questions with optional filters.",
)
async def list_questions(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    search: Annotated[str | None, Query()] = None,
    difficulty: Annotated[DifficultyLevel | None, Query()] = None,
    status: Annotated[QuestionStatus | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
) -> QuestionListResponse:
    """Return all questions owned by the recruiter."""

    filters = QuestionFilters(
        search=search,
        difficulty=difficulty,
        status=status,
        tag=tag,
    )
    return await run_in_threadpool(
        service.list_questions,
        current_user.uid,
        filters,
    )


@router.post(
    "/questions",
    response_model=QuestionRecord,
    summary="Create a recruiter question",
    description="Creates a coding question in the recruiter question bank.",
)
async def create_question(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionCreateRequest,
) -> QuestionRecord:
    """Create a question owned by the recruiter."""

    return await run_in_threadpool(service.create_question, current_user.uid, payload)


@router.post(
    "/questions/bulk-import",
    response_model=QuestionBulkImportResponse,
    summary="Bulk import recruiter questions from CSV",
    description="Imports one or more recruiter questions from CSV content.",
)
async def bulk_import_questions(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionBulkImportRequest,
) -> QuestionBulkImportResponse:
    """Create multiple recruiter-owned questions from CSV text."""

    return await run_in_threadpool(
        service.bulk_import_questions,
        current_user.uid,
        payload,
    )


@router.post(
    "/questions/ai-draft",
    response_model=QuestionAIDraftResponse,
    summary="Generate an AI-assisted question draft",
    description="Generates a recruiter-reviewable coding question draft.",
)
async def generate_ai_draft(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionAIDraftRequest,
) -> QuestionAIDraftResponse:
    """Generate a draft recruiter can review before saving."""

    return await run_in_threadpool(
        service.generate_ai_draft,
        current_user.uid,
        payload,
    )


@router.post(
    "/questions/ai-draft/stream",
    summary="Stream AI-assisted question draft progress",
    description="Streams question-agent graph progress and returns the final draft.",
)
async def stream_ai_draft(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionAIDraftRequest,
) -> StreamingResponse:
    """Stream graph movement and final draft as server-sent events."""

    def event_stream() -> Iterator[str]:
        try:
            for event in service.stream_ai_draft_events(current_user.uid, payload):
                event_type = event.get("type", "progress")
                yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
        except Exception as exc:
            message = getattr(exc, "message", str(exc))
            event = {
                "type": "error",
                "scope": payload.generation_scope,
                "message": message,
                "progress": 100,
            }
            yield f"event: error\ndata: {json.dumps(event)}\n\n"

    return sse.event_stream(event_stream())


@router.post(
    "/questions/validate-draft",
    response_model=QuestionDraftValidationResponse,
    summary="Validate an unsaved recruiter question draft",
    description="Validates draft structure and reference solution behavior.",
)
async def validate_question_draft(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionDraftValidationRequest,
) -> QuestionDraftValidationResponse:
    """Run a draft reference solution against its test cases before saving."""

    return await run_in_threadpool(service.validate_draft, payload)


@router.post(
    "/questions/refine-test-cases",
    response_model=QuestionDraftRefinementResponse,
    summary="Repair and complete existing test cases",
    description=(
        "Completes the requested testcase count, checks the suite against generated "
        "constraints, executes the reference solution, and repairs mismatches with "
        "oracle evidence."
    ),
)
async def refine_question_test_cases(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionDraftRefinementRequest,
) -> QuestionDraftRefinementResponse:
    """Refine existing testcase outputs and return fresh execution evidence."""

    return await run_in_threadpool(
        service.refine_draft_test_cases,
        current_user.uid,
        payload,
    )


@router.post(
    "/questions/refine-solution",
    response_model=QuestionDraftRefinementResponse,
    summary="Repair the existing reference solution",
    description=(
        "Repairs the current source from the problem statement and constraints, "
        "using failing execution cases only as diagnostic evidence."
    ),
)
async def refine_question_solution(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionDraftRefinementRequest,
) -> QuestionDraftRefinementResponse:
    """Refine existing solution source and return fresh execution evidence."""

    return await run_in_threadpool(
        service.refine_draft_solution,
        current_user.uid,
        payload,
    )


@router.patch(
    "/questions/{question_id}",
    response_model=QuestionRecord,
    summary="Update a recruiter question",
    description="Updates a recruiter-owned question and its test cases.",
)
async def update_question(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionUpdateRequest,
    question_id: str = Path(min_length=1),
) -> QuestionRecord:
    """Update a question owned by the recruiter."""

    return await run_in_threadpool(
        service.update_question,
        current_user.uid,
        question_id,
        payload,
    )


@router.delete(
    "/questions/{question_id}",
    summary="Delete a recruiter question",
    description="Deletes a recruiter-owned question from the question bank.",
)
async def delete_question(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    question_id: str = Path(min_length=1),
) -> dict[str, str]:
    """Delete a question owned by the recruiter."""

    await run_in_threadpool(service.delete_question, current_user.uid, question_id)
    return {"status": "deleted"}


@router.get(
    "/groups",
    response_model=QuestionGroupListResponse,
    summary="List recruiter question groups",
    description="Returns reusable recruiter-owned question groups.",
)
async def list_groups(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    search: Annotated[str | None, Query()] = None,
    status: Annotated[QuestionGroupStatus | None, Query()] = None,
) -> QuestionGroupListResponse:
    """Return all reusable question groups owned by the recruiter."""

    filters = QuestionGroupFilters(search=search, status=status)
    return await run_in_threadpool(
        service.list_groups,
        current_user.uid,
        filters,
    )


@router.post(
    "/groups",
    response_model=QuestionGroupRecord,
    summary="Create a question group",
    description="Creates a reusable group of existing recruiter questions.",
)
async def create_group(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionGroupCreateRequest,
) -> QuestionGroupRecord:
    """Create a reusable group from existing questions."""

    return await run_in_threadpool(service.create_group, current_user.uid, payload)


@router.patch(
    "/groups/{group_id}",
    response_model=QuestionGroupRecord,
    summary="Update a question group",
    description="Updates a reusable recruiter-owned question group.",
)
async def update_group(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    payload: QuestionGroupUpdateRequest,
    group_id: str = Path(min_length=1),
) -> QuestionGroupRecord:
    """Update an existing reusable group."""

    return await run_in_threadpool(
        service.update_group,
        current_user.uid,
        group_id,
        payload,
    )


@router.delete(
    "/groups/{group_id}",
    summary="Delete a question group",
    description="Deletes a reusable recruiter-owned question group.",
)
async def delete_group(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[QuestionBankService, Depends(get_question_bank_service)],
    group_id: str = Path(min_length=1),
) -> dict[str, str]:
    """Delete a reusable group."""

    await run_in_threadpool(service.delete_group, current_user.uid, group_id)
    return {"status": "deleted"}
