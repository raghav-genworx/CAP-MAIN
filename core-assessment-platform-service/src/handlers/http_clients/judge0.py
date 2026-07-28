"""HTTP client for Judge0 code execution."""

import asyncio
import base64
import binascii
import hashlib
import logging

import httpx
from pydantic import ValidationError

from config.settings import Settings
from core.exceptions.execution import CodeExecutionTimeoutError, Judge0ServiceError
from schemas.execution import Judge0Payload, Judge0SubmissionResult, LanguageResponse

logger = logging.getLogger(__name__)

PENDING_STATUS_IDS = {1, 2}


class Judge0Client:
    """Small async client for the Judge0 HTTP API."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize the client with runtime settings."""

        self._settings = settings
        self._base_url = settings.judge0_base_url.rstrip("/")
        self._timeout = settings.judge0_request_timeout_seconds
        self._poll_interval = settings.judge0_poll_interval_seconds
        self._max_poll_attempts = settings.judge0_max_poll_attempts
        self._transport = transport
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = (settings.judge0_api_key or "").strip()
        if api_key:
            self._headers[settings.judge0_auth_header] = api_key

    async def execute(self, payload: Judge0Payload) -> Judge0SubmissionResult:
        """Create a Judge0 submission and wait for the final result."""

        async with self._client() as client:
            token = await self._create_submission(client, payload)
            return await self._wait_for_submission(
                client,
                token,
                cpu_time_limit=float(payload.get("cpu_time_limit") or 0),
            )

    async def execute_batch(
        self,
        payloads: list[Judge0Payload],
    ) -> list[Judge0SubmissionResult]:
        """Create Judge0 batch submissions and wait for every final result."""

        if not payloads:
            return []
        async with self._client() as client:
            tokens = await self._create_batch_submission(client, payloads)
            max_cpu_time = max(
                (float(payload.get("cpu_time_limit") or 0) for payload in payloads),
                default=0,
            )
            return await self._wait_for_batch_submission(
                client,
                tokens,
                cpu_time_limit=max_cpu_time,
            )

    async def get_languages(self) -> list[LanguageResponse]:
        """Fetch supported languages from Judge0."""

        try:
            async with self._client() as client:
                response = await client.get("/languages")
        except httpx.HTTPError as exc:
            raise Judge0ServiceError("Unable to reach Judge0.") from exc
        self._raise_for_judge0_error(response)
        data = self._json_body(response)
        if not isinstance(data, list):
            raise Judge0ServiceError("Judge0 returned an invalid languages response.")
        try:
            return [LanguageResponse.model_validate(language) for language in data]
        except ValidationError as exc:
            raise Judge0ServiceError(
                "Judge0 returned an invalid languages response."
            ) from exc

    async def _create_submission(
        self,
        client: httpx.AsyncClient,
        payload: Judge0Payload,
    ) -> str:
        encoded_payload = self._encode_payload(payload)
        try:
            response = await client.post(
                "/submissions",
                params={"base64_encoded": "true", "wait": "false"},
                json=encoded_payload,
            )
        except httpx.HTTPError as exc:
            raise Judge0ServiceError("Unable to reach Judge0.") from exc
        self._raise_for_judge0_error(response)
        data = self._json_body(response)
        token = data.get("token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise Judge0ServiceError("Judge0 did not return a submission token.")
        logger.info(
            "judge0_submission_created token_fingerprint=%s",
            hashlib.sha256(token.encode("utf-8")).hexdigest()[:12],
        )
        return token

    async def _create_batch_submission(
        self,
        client: httpx.AsyncClient,
        payloads: list[Judge0Payload],
    ) -> list[str]:
        encoded_payloads = [self._encode_payload(payload) for payload in payloads]
        try:
            response = await client.post(
                "/submissions/batch",
                params={"base64_encoded": "true"},
                json={"submissions": encoded_payloads},
            )
        except httpx.HTTPError as exc:
            raise Judge0ServiceError("Unable to reach Judge0.") from exc
        self._raise_for_judge0_error(response)
        data = self._json_body(response)
        tokens = self._extract_batch_tokens(data)
        if len(tokens) != len(payloads):
            raise Judge0ServiceError("Judge0 returned an invalid batch token response.")
        logger.info(
            "judge0_batch_submission_created count=%s first_token_fingerprint=%s",
            len(tokens),
            hashlib.sha256(tokens[0].encode("utf-8")).hexdigest()[:12],
        )
        return tokens

    async def _wait_for_submission(
        self,
        client: httpx.AsyncClient,
        token: str,
        cpu_time_limit: float = 0,
    ) -> Judge0SubmissionResult:
        result: Judge0SubmissionResult | None = None
        for _ in range(self._poll_attempt_budget(cpu_time_limit)):
            result = await self._get_submission(client, token)
            if result.status is not None and result.status.id not in PENDING_STATUS_IDS:
                return self._decode_result(result)
            await asyncio.sleep(self._poll_interval)
        raise CodeExecutionTimeoutError()

    async def _wait_for_batch_submission(
        self,
        client: httpx.AsyncClient,
        tokens: list[str],
        cpu_time_limit: float = 0,
    ) -> list[Judge0SubmissionResult]:
        token_set = set(tokens)
        latest_by_token: dict[str, Judge0SubmissionResult] = {}
        for _ in range(
            self._poll_attempt_budget(
                cpu_time_limit,
                submission_count=len(tokens),
            )
        ):
            results = await self._get_batch_submission(client, tokens)
            latest_by_token = {
                result.token: result for result in results if result.token in token_set
            }
            if len(latest_by_token) != len(tokens):
                raise Judge0ServiceError(
                    "Judge0 returned an incomplete batch submission response."
                )
            if all(
                result.status is not None and result.status.id not in PENDING_STATUS_IDS
                for result in latest_by_token.values()
            ):
                return [self._decode_result(latest_by_token[token]) for token in tokens]
            await asyncio.sleep(self._poll_interval)
        raise CodeExecutionTimeoutError()

    def _poll_attempt_budget(
        self,
        cpu_time_limit: float,
        submission_count: int = 1,
    ) -> int:
        """Allow queued batch submissions enough aggregate processing time."""

        configured_window = self._max_poll_attempts * self._poll_interval
        normalized_count = max(1, submission_count)
        required_window = max(
            configured_window,
            (cpu_time_limit + self._settings.judge0_poll_margin_seconds)
            * normalized_count,
        )
        return max(1, int(required_window / self._poll_interval) + 1)

    async def _get_submission(
        self,
        client: httpx.AsyncClient,
        token: str,
    ) -> Judge0SubmissionResult:
        try:
            response = await client.get(
                f"/submissions/{token}",
                params={"base64_encoded": "true"},
            )
        except httpx.HTTPError as exc:
            raise Judge0ServiceError("Unable to reach Judge0.") from exc
        self._raise_for_judge0_error(response)
        try:
            return Judge0SubmissionResult.model_validate(self._json_body(response))
        except ValidationError as exc:
            raise Judge0ServiceError(
                "Judge0 returned an invalid submission response."
            ) from exc

    async def _get_batch_submission(
        self,
        client: httpx.AsyncClient,
        tokens: list[str],
    ) -> list[Judge0SubmissionResult]:
        try:
            response = await client.get(
                "/submissions/batch",
                params={
                    "tokens": ",".join(tokens),
                    "base64_encoded": "true",
                },
            )
        except httpx.HTTPError as exc:
            raise Judge0ServiceError("Unable to reach Judge0.") from exc
        self._raise_for_judge0_error(response)
        data = self._json_body(response)
        submissions = (
            data.get("submissions")
            if isinstance(data, dict)
            else data
            if isinstance(data, list)
            else None
        )
        if not isinstance(submissions, list):
            raise Judge0ServiceError("Judge0 returned an invalid batch response.")
        try:
            return [
                Judge0SubmissionResult.model_validate(submission)
                for submission in submissions
            ]
        except ValidationError as exc:
            raise Judge0ServiceError(
                "Judge0 returned an invalid batch submission response."
            ) from exc

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
            transport=self._transport,
        )

    def _encode_payload(self, payload: Judge0Payload) -> Judge0Payload:
        encoded = payload.copy()
        for field in ("source_code", "stdin", "expected_output"):
            value = encoded.get(field)
            if isinstance(value, str):
                encoded[field] = self._encode_text(value)
        return encoded

    def _decode_result(
        self,
        submission: Judge0SubmissionResult,
    ) -> Judge0SubmissionResult:
        result = submission.model_copy()
        for field in ("stdout", "stderr", "compile_output", "message"):
            value = getattr(result, field)
            if value is not None:
                setattr(result, field, self._decode_text(value))
        return result

    def _extract_batch_tokens(self, data: object) -> list[str]:
        submissions = (
            data.get("submissions")
            if isinstance(data, dict)
            else data
            if isinstance(data, list)
            else None
        )
        if not isinstance(submissions, list):
            raise Judge0ServiceError("Judge0 returned an invalid batch token response.")
        tokens: list[str] = []
        for submission in submissions:
            token = submission.get("token") if isinstance(submission, dict) else None
            if not isinstance(token, str) or not token:
                raise Judge0ServiceError(
                    "Judge0 returned an invalid batch token response."
                )
            tokens.append(token)
        return tokens

    def _raise_for_judge0_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        logger.warning(
            "judge0_request_failed status_code=%s",
            response.status_code,
        )
        message = (
            "Judge0 rejected the execution request."
            if response.status_code < 500
            else "Judge0 service is unavailable."
        )
        raise Judge0ServiceError(message, status_code=502)

    def _json_body(self, response: httpx.Response) -> object:
        try:
            return response.json()
        except ValueError as exc:
            raise Judge0ServiceError(
                "Judge0 returned an invalid JSON response."
            ) from exc

    def _encode_text(self, value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    def _decode_text(self, value: str) -> str:
        try:
            encoded = value.encode("ascii")
            normalized = b"".join(encoded.split())
            decoded = base64.b64decode(normalized, validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise Judge0ServiceError(
                "Judge0 returned an invalid encoded response."
            ) from exc
        return decoded.decode("utf-8", errors="replace")
