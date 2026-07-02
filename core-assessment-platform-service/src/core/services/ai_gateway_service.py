"""Shared structured-completion gateway for AI tasks."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _AIProviderTarget:
    """One concrete model/provider/key-slot attempt in the failover sequence."""

    provider: str
    model: str
    client: OpenAI
    api_key_slot: int | None = None

    @property
    def label(self) -> str:
        if self.api_key_slot is None:
            return f"{self.provider}:{self.model}"
        return f"{self.provider}:{self.model}:key-slot-{self.api_key_slot}"


class AIGatewayService:
    """Wrap the LLM client, retries, and trace logging."""

    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._run_log_repository = AIRunLogRepository(session)
        self._provider_targets = self._build_provider_targets()

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

        if not self._provider_targets:
            raise RuntimeError(
                "No AI provider is configured. Set GROQ_API_KEY_1..4 or enable "
                "OLLAMA_ENABLED with OLLAMA_BASE_URL, then restart the backend "
                "service."
            )

        sequence_attempts = max(1, self._settings.groq_retry_count)
        backoff = max(0.0, self._settings.groq_retry_backoff_seconds)
        last_error: Exception | None = None
        last_target: _AIProviderTarget | None = None
        attempts_used = 0
        disabled_key_slots: set[int] = set()
        started = perf_counter()

        for sequence_attempt in range(1, sequence_attempts + 1):
            attempted_this_round = False
            for target in self._provider_targets:
                if (
                    target.provider == "groq"
                    and target.api_key_slot in disabled_key_slots
                ):
                    continue
                attempted_this_round = True
                attempts_used += 1
                last_target = target
                try:
                    parsed = self._target_structured_completion(
                        target=target,
                        schema_name=schema_name,
                        schema_model=schema_model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                    )
                except Exception as exc:  # pragma: no cover - network/model dependent
                    last_error = exc
                    if (
                        target.provider == "groq"
                        and target.api_key_slot is not None
                        and self._is_authentication_error(exc)
                    ):
                        disabled_key_slots.add(target.api_key_slot)
                    LOGGER.warning(
                        "AI provider target failed for %s target=%s error_type=%s",
                        schema_name,
                        target.label,
                        type(exc).__name__,
                    )
                    continue
                self._log_run(
                    recruiter_uid=recruiter_uid,
                    task_name=task_name,
                    prompt_version=prompt_version,
                    schema_name=schema_name,
                    workflow_mode=workflow_mode,
                    retry_count=max(0, attempts_used - 1),
                    latency_ms=int((perf_counter() - started) * 1000),
                    success=True,
                    error_message="",
                    model_name=target.model,
                    request_payload=self._request_audit_payload(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        target=target,
                    ),
                    response_payload=parsed.model_dump(mode="json"),
                )
                return parsed
            if not attempted_this_round:
                break
            if sequence_attempt < sequence_attempts and backoff:
                sleep(
                    self._retry_delay_seconds(
                        last_error,
                        fallback_seconds=backoff * sequence_attempt,
                    )
                )

        self._raise_generation_failure(
            schema_name=schema_name,
            task_name=task_name,
            recruiter_uid=recruiter_uid,
            prompt_version=prompt_version,
            workflow_mode=workflow_mode,
            retries_used=max(0, attempts_used - 1),
            started=started,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            last_error=last_error,
            model_name=last_target.model if last_target else "unconfigured",
            target=last_target,
            user_message=(
                f"AI generation failed for {schema_name} after trying "
                f"{attempts_used} provider target"
                f"{'' if attempts_used == 1 else 's'}."
            ),
        )

    def _target_structured_completion(
        self,
        *,
        target: _AIProviderTarget,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> BaseModel:
        try:
            response = self._create_structured_completion(
                target=target,
                schema_name=schema_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=schema_model,
                use_json_schema=True,
            )
            return schema_model.model_validate(
                json.loads(response.choices[0].message.content or "{}")
            )
        except Exception as exc:  # pragma: no cover - network/model dependent
            if self._is_target_exhaustion_error(exc):
                raise
            response = self._create_structured_completion(
                target=target,
                schema_name=schema_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=schema_model,
                use_json_schema=False,
            )
            return schema_model.model_validate(
                json.loads(response.choices[0].message.content or "{}")
            )

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) == 429

    @staticmethod
    def _is_authentication_error(exc: Exception) -> bool:
        return (
            getattr(exc, "status_code", None) == 401
            or type(exc).__name__ == "AuthenticationError"
        )

    @classmethod
    def _is_target_exhaustion_error(cls, exc: Exception) -> bool:
        return cls._is_rate_limit_error(exc) or cls._is_authentication_error(exc)

    def _raise_generation_failure(
        self,
        *,
        schema_name: str,
        task_name: str,
        recruiter_uid: str,
        prompt_version: str,
        workflow_mode: str,
        retries_used: int,
        started: float,
        system_prompt: str,
        user_prompt: str,
        last_error: Exception | None,
        model_name: str,
        target: _AIProviderTarget | None,
        user_message: str,
    ) -> None:
        error_detail = type(last_error).__name__ if last_error else "unknown error"
        self._log_run(
            recruiter_uid=recruiter_uid,
            task_name=task_name,
            prompt_version=prompt_version,
            schema_name=schema_name,
            workflow_mode=workflow_mode,
            retry_count=retries_used,
            latency_ms=int((perf_counter() - started) * 1000),
            success=False,
            error_message=error_detail,
            model_name=model_name,
            request_payload=self._request_audit_payload(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                target=target,
            ),
            response_payload={},
        )
        raise RuntimeError(user_message) from last_error

    @staticmethod
    def _retry_delay_seconds(
        exc: Exception | None,
        *,
        fallback_seconds: float,
    ) -> float:
        response = getattr(exc, "response", None) if exc is not None else None
        headers = getattr(response, "headers", {})
        try:
            if headers.get("retry-after-ms"):
                provider_delay = float(headers["retry-after-ms"]) / 1000
            elif headers.get("retry-after"):
                provider_delay = float(headers["retry-after"])
            else:
                provider_delay = 0
        except (TypeError, ValueError):
            provider_delay = 0
        return min(120.0, max(0.0, fallback_seconds, provider_delay))

    def _create_structured_completion(
        self,
        *,
        target: _AIProviderTarget,
        schema_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[BaseModel],
        use_json_schema: bool,
    ) -> Any:
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
            "model": target.model,
            "messages": messages,
            "temperature": 0,
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
        return target.client.chat.completions.create(**kwargs)

    def _build_provider_targets(self) -> list[_AIProviderTarget]:
        targets: list[_AIProviderTarget] = []
        groq_models = self._settings.groq_fallback_models
        for slot_number, api_key in self._settings.groq_api_key_slots:
            client = OpenAI(
                api_key=api_key,
                base_url=self._settings.groq_base_url,
                timeout=self._settings.groq_request_timeout_seconds,
            )
            for model in groq_models:
                targets.append(
                    _AIProviderTarget(
                        provider="groq",
                        model=model,
                        client=client,
                        api_key_slot=slot_number,
                    )
                )
            if self._settings.ollama_enabled:
                targets.append(self._build_ollama_target())

        if not self._settings.groq_api_keys:
            LOGGER.warning("No Groq API key slots are configured")
            if self._settings.ollama_enabled:
                targets.append(self._build_ollama_target())
        return targets

    def _build_ollama_target(self) -> _AIProviderTarget:
        return _AIProviderTarget(
            provider="ollama",
            model=self._settings.ollama_model,
            client=OpenAI(
                api_key=self._settings.ollama_api_key or "ollama",
                base_url=self._settings.ollama_base_url,
                timeout=self._settings.groq_request_timeout_seconds,
            ),
        )

    @staticmethod
    def _request_audit_payload(
        *,
        system_prompt: str,
        user_prompt: str,
        target: _AIProviderTarget | None = None,
    ) -> dict[str, object]:
        """Return useful prompt audit metadata without retaining prompt content."""

        payload: dict[str, object] = {
            "system_prompt_length": len(system_prompt),
            "system_prompt_fingerprint": hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest()[:16],
            "user_prompt_length": len(user_prompt),
            "user_prompt_fingerprint": hashlib.sha256(
                user_prompt.encode("utf-8")
            ).hexdigest()[:16],
        }
        if target is not None:
            payload.update(
                {
                    "ai_provider": target.provider,
                    "ai_model": target.model,
                    "api_key_slot": target.api_key_slot or "",
                }
            )
        return payload

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
        model_name: str,
        request_payload: dict[str, object],
        response_payload: dict[str, object],
    ) -> None:
        try:
            self._run_log_repository.add_run_log(
                AIRunLogModel(
                    recruiter_uid=recruiter_uid,
                    task_name=task_name,
                    prompt_version=prompt_version,
                    model_name=model_name,
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
