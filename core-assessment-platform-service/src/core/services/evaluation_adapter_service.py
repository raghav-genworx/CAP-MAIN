"""Adapter used by the core service to call code-evaluation-service."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from config.settings import Settings
from core.exceptions.assessment import (
    EvaluationAdapterError,
    EvaluationResourceNotFoundError,
)
from schemas.evaluation_reports import (
    AssessmentEvaluationDashboard,
    AssessmentReportResponse,
    CandidateReportResponse,
    RetryEvaluationResponse,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluationReportDownload:
    """Downloaded report bytes and safe response metadata."""

    content: bytes
    filename: str
    media_type: str


class EvaluationScores(BaseModel):
    """Scores returned by the evaluation service."""

    test_case_score: float
    coding_score: float
    ai_score: float
    final_score: float
    percentage: float


class EvaluationResult(BaseModel):
    """Candidate scorecard subset consumed by core."""

    rank: int | None = None
    scores: EvaluationScores
    hidden_passed: int
    hidden_total: int
    total_execution_time_ms: float
    peak_memory_kb: int
    ai_quality: dict[str, Any] = Field(default_factory=dict)
    question_breakdown: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationJobResult(BaseModel):
    """Evaluation job response returned by code-evaluation-service."""

    job_id: str
    assessment_id: str
    candidate_assessment_id: str
    status: str
    attempt_count: int
    error_message: str | None = None
    result: EvaluationResult | None = None


class CandidateEvaluationScorecard(BaseModel):
    """Leaderboard row returned by code-evaluation-service."""

    candidate_assessment_id: str
    rank: int | None = None
    scores: EvaluationScores


class EvaluationAdapterService:
    """Submit final hidden execution evidence to code-evaluation-service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_job(self, payload: dict[str, Any]) -> EvaluationJobResult:
        """Create an evaluation job and return the normalized response."""

        url = (
            f"{self._settings.code_evaluation_api_base_url.rstrip('/')}"
            "/evaluations/jobs"
        )
        try:
            with httpx.Client(
                timeout=self._settings.code_evaluation_request_timeout_seconds,
                headers=self._service_headers(),
            ) as client:
                response = client.post(url, json=payload)
                if response.status_code == 404:
                    logger.info(
                        "evaluation_service_job_not_found status_code=%s "
                        "payload_shape=%s",
                        response.status_code,
                        self._payload_shape(payload),
                    )
                    raise EvaluationResourceNotFoundError(
                        "Evaluation service resource not found"
                    )
                if response.is_error:
                    logger.error(
                        "evaluation_service_job_error status_code=%s "
                        "response_text=%s payload_shape=%s",
                        response.status_code,
                        response.text,
                        self._payload_shape(payload),
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EvaluationAdapterError("Evaluation service request failed") from exc

        return EvaluationJobResult.model_validate(response.json())

    def get_leaderboard(self, assessment_id: str) -> list[CandidateEvaluationScorecard]:
        """Return authoritative ranked scorecards for one assessment."""

        url = (
            f"{self._settings.code_evaluation_api_base_url.rstrip('/')}"
            f"/evaluations/assessment/{assessment_id}/leaderboard"
        )
        try:
            with httpx.Client(
                timeout=self._settings.code_evaluation_request_timeout_seconds,
                headers=self._service_headers(),
            ) as client:
                response = client.get(url)
                if response.status_code == 404:
                    logger.info(
                        "evaluation_service_leaderboard_not_found "
                        "status_code=%s assessment_id=%s",
                        response.status_code,
                        assessment_id,
                    )
                    raise EvaluationResourceNotFoundError(
                        "Evaluation leaderboard not found"
                    )
                if response.is_error:
                    logger.error(
                        "evaluation_service_leaderboard_error status_code=%s "
                        "response_text=%s assessment_id=%s",
                        response.status_code,
                        response.text,
                        assessment_id,
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EvaluationAdapterError(
                "Evaluation leaderboard request failed"
            ) from exc

        return [
            CandidateEvaluationScorecard.model_validate(item)
            for item in response.json()
        ]

    def get_dashboard(self, assessment_id: str) -> AssessmentEvaluationDashboard:
        """Return the complete evaluation workspace for one assessment."""

        response = self._get(f"/evaluations/assessment/{assessment_id}")
        return AssessmentEvaluationDashboard.model_validate(response.json())

    def get_assessment_report(self, assessment_id: str) -> AssessmentReportResponse:
        """Return report metadata for one assessment."""

        response = self._get(f"/evaluations/reports/assessment/{assessment_id}")
        return AssessmentReportResponse.model_validate(response.json())

    def get_candidate_report(
        self,
        assessment_id: str,
        candidate_assessment_id: str,
    ) -> CandidateReportResponse:
        """Return an authorized candidate scorecard payload."""

        response = self._get(
            f"/evaluations/reports/assessment/{assessment_id}/candidate/"
            f"{candidate_assessment_id}"
        )
        return CandidateReportResponse.model_validate(response.json())

    def retry_job(self, job_id: str) -> RetryEvaluationResponse:
        """Retry one failed evaluation job."""

        response = self._post(f"/evaluations/jobs/{job_id}/retry")
        return RetryEvaluationResponse.model_validate(response.json())

    def download_assessment_report(
        self,
        assessment_id: str,
    ) -> EvaluationReportDownload:
        """Download the assessment PDF through the trusted service channel."""

        response = self._get(
            f"/evaluations/reports/assessment/{assessment_id}/download"
        )
        return self._download_from(response, f"assessment-{assessment_id}.pdf")

    def download_candidate_report(
        self,
        assessment_id: str,
        candidate_assessment_id: str,
    ) -> EvaluationReportDownload:
        """Download one candidate scorecard through the trusted service channel."""

        response = self._get(
            f"/evaluations/reports/assessment/{assessment_id}/candidate/"
            f"{candidate_assessment_id}/download"
        )
        return self._download_from(
            response,
            f"candidate-{candidate_assessment_id}.pdf",
        )

    def download_test_report(
        self,
        assessment_id: str,
        test_id: str,
        payload: dict[str, Any],
    ) -> EvaluationReportDownload:
        """Download one scheduled test report through the trusted channel."""

        response = self._request(
            "POST",
            f"/evaluations/reports/assessment/{assessment_id}/tests/{test_id}/download",
            json_payload=payload,
        )
        return self._download_from(response, f"test-{test_id}.pdf")

    def _get(self, path: str) -> httpx.Response:
        return self._request("GET", path)

    def _post(self, path: str) -> httpx.Response:
        return self._request("POST", path)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._settings.code_evaluation_api_base_url.rstrip('/')}{path}"
        try:
            with httpx.Client(
                timeout=self._settings.code_evaluation_request_timeout_seconds,
                headers=self._service_headers(),
            ) as client:
                request_kwargs: dict[str, Any] = {}
                if json_payload is not None:
                    request_kwargs["json"] = json_payload
                response = client.request(method, url, **request_kwargs)
                if response.status_code == 404:
                    logger.info(
                        "evaluation_service_not_found method=%s path=%s "
                        "status_code=%s",
                        method,
                        path,
                        response.status_code,
                    )
                    raise EvaluationResourceNotFoundError(
                        "Evaluation data not found"
                    )
                if response.is_error:
                    logger.error(
                        "evaluation_service_request_error method=%s path=%s "
                        "status_code=%s",
                        method,
                        path,
                        response.status_code,
                    )
                response.raise_for_status()
                return response
        except httpx.HTTPError as exc:
            raise EvaluationAdapterError("Evaluation service request failed") from exc

    def _service_headers(self) -> dict[str, str]:
        return {
            "X-Internal-Service-Token": self._settings.internal_service_token,
        }

    @staticmethod
    def _download_from(
        response: httpx.Response,
        fallback_filename: str,
    ) -> EvaluationReportDownload:
        disposition = response.headers.get("content-disposition", "")
        match = re.search(r'filename="?([^";]+)', disposition)
        filename = match.group(1) if match else fallback_filename
        return EvaluationReportDownload(
            content=response.content,
            filename=filename.replace("/", "-").replace("\\", "-"),
            media_type=response.headers.get("content-type", "application/pdf"),
        )

    @staticmethod
    def _payload_shape(payload: dict[str, Any]) -> dict[str, Any]:
        """Return diagnostic request metadata without logging candidate code."""

        hidden_results = payload.get("hidden_results")
        source_code = str(payload.get("source_code") or "")
        return {
            "keys": sorted(payload.keys()),
            "assessment_id": payload.get("assessment_id"),
            "candidate_assessment_id": payload.get("candidate_assessment_id"),
            "source_code_length": len(source_code),
            "hidden_result_count": (
                len(hidden_results) if isinstance(hidden_results, list) else 0
            ),
            "has_weights": "weights" in payload,
        }
