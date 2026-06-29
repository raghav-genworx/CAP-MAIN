"""Structured AI gateway boundary contract tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from config.settings import Settings
from core.services import ai_gateway_service
from core.services.ai_gateway_service import AIGatewayService


class _Answer(BaseModel):
    value: str


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _service(*, attempts: int = 1) -> tuple[AIGatewayService, MagicMock]:
    service = AIGatewayService(
        Settings(
            groq_api_key="groq-secret",
            groq_retry_count=attempts,
            groq_retry_backoff_seconds=0,
        ),
        MagicMock(),
    )
    create = MagicMock()
    service._client = SimpleNamespace(  # type: ignore[assignment]
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    service._run_log_repository = MagicMock()
    return service, create


def _run(service: AIGatewayService) -> _Answer:
    return service.structured_completion(
        schema_name="answer_contract",
        schema_model=_Answer,
        system_prompt="system prompt with private rubric",
        user_prompt="user prompt with recruiter content",
        task_name="contract-test",
        recruiter_uid="recruiter-1",
    )


def test_structured_request_uses_strict_schema_and_minimal_audit_payload() -> None:
    service, create = _service()
    create.return_value = _completion('{"value":"accepted"}')

    result = _run(service)

    assert result == _Answer(value="accepted")
    request = create.call_args.kwargs
    assert request["model"] == service._settings.groq_model
    assert request["messages"][0] == {
        "role": "system",
        "content": "system prompt with private rubric",
    }
    response_format = request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    run_log = service._run_log_repository.add_run_log.call_args.args[0]
    assert run_log.success is True
    assert run_log.request_payload["system_prompt_length"] == 33
    assert run_log.request_payload["user_prompt_length"] == 34
    assert "system prompt" not in str(run_log.request_payload)
    assert "recruiter content" not in str(run_log.request_payload)


def test_gateway_falls_back_to_json_object_when_schema_mode_is_rejected() -> None:
    service, create = _service()
    create.side_effect = [
        RuntimeError("json_schema unsupported"),
        _completion('{"value":"fallback"}'),
    ]

    assert _run(service) == _Answer(value="fallback")
    assert create.call_count == 2
    assert create.call_args_list[0].kwargs["response_format"]["type"] == "json_schema"
    fallback_request = create.call_args_list[1].kwargs
    assert fallback_request["response_format"] == {"type": "json_object"}
    assert "must match this schema" in fallback_request["messages"][0]["content"]


def test_provider_failure_is_sanitized_in_error_and_audit_record() -> None:
    service, create = _service()
    create.side_effect = RuntimeError("provider-secret response body")

    with pytest.raises(RuntimeError, match=r"after 1 attempt\(s\)\.$") as raised:
        _run(service)

    assert "provider-secret" not in str(raised.value)
    run_log = service._run_log_repository.add_run_log.call_args.args[0]
    assert run_log.success is False
    assert run_log.error_message == "RuntimeError"
    assert "private rubric" not in str(run_log.request_payload)


def test_openai_client_uses_configured_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(ai_gateway_service, "OpenAI", client_factory)

    AIGatewayService(
        Settings(
            groq_api_key="groq-secret",
            groq_base_url="https://groq.test/openai/v1",
            groq_request_timeout_seconds=17,
        ),
        MagicMock(),
    )

    client_factory.assert_called_once_with(
        api_key="groq-secret",
        base_url="https://groq.test/openai/v1",
        timeout=17,
    )
