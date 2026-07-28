"""Code execution routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from api.rest.dependencies import (
    code_execution_service_dependency,
    require_internal_service,
)
from core.services.execution.code_execution_service import CodeExecutionService
from schemas.execution import (
    BatchExecutionRequest,
    BatchExecutionResponse,
    ExecutionRequest,
    ExecutionResponse,
    LanguageResponse,
)

router = APIRouter(
    prefix="/executions",
    tags=["executions"],
    dependencies=[Depends(require_internal_service)],
)


@router.post(
    "",
    response_model=ExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute code with Judge0",
    description="Runs submitted source code with stdin and returns the Judge0 result.",
)
async def execute_code(
    request: ExecutionRequest,
    service: Annotated[
        CodeExecutionService,
        Depends(code_execution_service_dependency),
    ],
) -> ExecutionResponse:
    """Execute source code and return the normalized result."""

    return await service.execute(request)


@router.post(
    "/batch",
    response_model=BatchExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute code against multiple test cases",
    description=(
        "Runs one source submission against a list of stdin/expected-output pairs."
    ),
)
async def execute_code_batch(
    request: BatchExecutionRequest,
    service: Annotated[
        CodeExecutionService,
        Depends(code_execution_service_dependency),
    ],
) -> BatchExecutionResponse:
    """Execute one source against multiple test cases."""

    return await service.execute_batch(request)


@router.get(
    "/languages",
    response_model=list[LanguageResponse],
    summary="List Judge0 languages",
    description="Returns languages supported by the configured Judge0 deployment.",
)
async def get_languages(
    service: Annotated[
        CodeExecutionService,
        Depends(code_execution_service_dependency),
    ],
) -> list[LanguageResponse]:
    """Return supported Judge0 languages."""

    return await service.get_languages()
