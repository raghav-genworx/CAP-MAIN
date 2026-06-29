"""Shared structured-completion gateway for AI tasks."""

from __future__ import annotations

import hashlib
import json
import logging
from time import perf_counter, sleep
from typing import Any

from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.settings import Settings
from data.models.postgres.ai_run_log import AIRunLogModel
from data.repositories.ai_run_log_repository import AIRunLogRepository

LOGGER = logging.getLogger(__name__)


class AIGatewayService:
    """Wrap the LLM client, retries, and trace logging."""

    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._run_log_repository = AIRunLogRepository(session)
        self._client = self._build_client()

    def structured_completion(
        self,
        *,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        task_name: str,
        recruiter_uid: str = "",
        prompt_version: str = "v1",
        workflow_mode: str = "interactive",
    ) -> Any:
        """Run a schema-validated completion with retries and trace logging."""

        if self._client is None:
            raise RuntimeError(
                "Groq API client is not configured. Set GROQ_API_KEY and restart "
                "the backend service."
            )

        attempts = max(1, self._settings.groq_retry_count)
        backoff = max(0.0, self._settings.groq_retry_backoff_seconds)
        last_error: Exception | None = None
        retries_used = 0
        started = perf_counter()

        for attempt in range(1, attempts + 1):
            try:
                response = self._create_structured_completion(
                    schema_name=schema_name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema_model=schema_model,
                    use_json_schema=True,
                )
                parsed = schema_model.model_validate(
                    json.loads(response.choices[0].message.content or "{}")
                )
                self._log_run(
                    recruiter_uid=recruiter_uid,
                    task_name=task_name,
                    prompt_version=prompt_version,
                    schema_name=schema_name,
                    workflow_mode=workflow_mode,
                    retry_count=retries_used,
                    latency_ms=int((perf_counter() - started) * 1000),
                    success=True,
                    error_message="",
                    request_payload=self._request_audit_payload(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                    ),
                    response_payload=parsed.model_dump(mode="json"),
                )
                return parsed
            except Exception as exc:  # pragma: no cover - network/model dependent
                last_error = exc
                retries_used = attempt - 1
                try:
                    response = self._create_structured_completion(
                        schema_name=schema_name,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        schema_model=schema_model,
                        use_json_schema=False,
                    )
                    parsed = schema_model.model_validate(
                        json.loads(response.choices[0].message.content or "{}")
                    )
                    self._log_run(
                        recruiter_uid=recruiter_uid,
                        task_name=task_name,
                        prompt_version=prompt_version,
                        schema_name=schema_name,
                        workflow_mode=workflow_mode,
                        retry_count=retries_used,
                        latency_ms=int((perf_counter() - started) * 1000),
                        success=True,
                        error_message="",
                        request_payload=self._request_audit_payload(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                        ),
                        response_payload=parsed.model_dump(mode="json"),
                    )
                    return parsed
                except (
                    Exception
                ) as fallback_exc:  # pragma: no cover - network/model dependent
                    last_error = fallback_exc
                    if attempt < attempts:
                        LOGGER.warning(
                            "Groq API attempt %s/%s failed for %s; retrying "
                            "error_type=%s",
                            attempt,
                            attempts,
                            schema_name,
                            type(fallback_exc).__name__,
                        )
                        if backoff:
                            sleep(backoff * attempt)
                        continue

        error_detail = type(last_error).__name__ if last_error else "unknown error"
        self._log_run(
            recruiter_uid=recruiter_uid,
            task_name=task_name,
            prompt_version=prompt_version,
            schema_name=schema_name,
            workflow_mode=workflow_mode,
            retry_count=max(0, attempts - 1),
            latency_ms=int((perf_counter() - started) * 1000),
            success=False,
            error_message=error_detail,
            request_payload=self._request_audit_payload(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ),
            response_payload={},
        )
        raise RuntimeError(
            f"Groq generation failed for {schema_name} after {attempts} attempt(s)."
        )

    def _create_structured_completion(
        self,
        *,
        schema_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[BaseModel],
        use_json_schema: bool,
    ) -> Any:
        client = self._client
        if client is None:
            raise RuntimeError("Groq API client is not configured.")

        messages = [
            {
                "role": "system",
                "content": (
                    f"{system_prompt} Return valid JSON only. The JSON object "
                    "must match this schema: "
                    f"{json.dumps(schema_model.model_json_schema())}"
                    if not use_json_schema
                    else system_prompt
                ),
            },
            {"role": "user", "content": user_prompt},
        ]
        kwargs: dict[str, Any] = {
            "model": self._settings.groq_model,
            "messages": messages,
        }
        if use_json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema_model.model_json_schema(),
                },
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kwargs)

    def _build_client(self) -> OpenAI | None:
        if not self._settings.groq_api_key.strip():
            LOGGER.warning("GROQ_API_KEY is not configured")
            return None
        return OpenAI(
            api_key=self._settings.groq_api_key,
            base_url=self._settings.groq_base_url,
            timeout=self._settings.groq_request_timeout_seconds,
        )

    @staticmethod
    def _request_audit_payload(
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, object]:
        """Return useful prompt audit metadata without retaining prompt content."""

        return {
            "system_prompt_length": len(system_prompt),
            "system_prompt_fingerprint": hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest()[:16],
            "user_prompt_length": len(user_prompt),
            "user_prompt_fingerprint": hashlib.sha256(
                user_prompt.encode("utf-8")
            ).hexdigest()[:16],
        }

    def _log_run(
        self,
        *,
        recruiter_uid: str,
        task_name: str,
        prompt_version: str,
        schema_name: str,
        workflow_mode: str,
        retry_count: int,
        latency_ms: int,
        success: bool,
        error_message: str,
        request_payload: dict[str, object],
        response_payload: dict[str, object],
    ) -> None:
        try:
            self._run_log_repository.add_run_log(
                AIRunLogModel(
                    recruiter_uid=recruiter_uid,
                    task_name=task_name,
                    prompt_version=prompt_version,
                    model_name=self._settings.groq_model,
                    schema_name=schema_name,
                    workflow_mode=workflow_mode,
                    retry_count=retry_count,
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_message,
                    request_payload=request_payload,
                    response_payload=response_payload,
                )
            )
        except SQLAlchemyError:
            self._run_log_repository.rollback()
            LOGGER.warning("Unable to persist AI gateway run log", exc_info=True)
