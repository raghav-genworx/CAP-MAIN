"""Structured AI gateway boundary contract tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from config.settings import Settings
from core.services import ai_gateway_service
from core.services.ai_gateway_service import AIGatewayService, _AIProviderTarget


class _Answer(BaseModel):
    value: str


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _mock_target(
    *,
    create: MagicMock,
    model: str = "qwen/qwen3-32b",
    provider: str = "groq",
    api_key_slot: int | None = 1,
) -> _AIProviderTarget:
    return _AIProviderTarget(
        provider=provider,
        model=model,
        client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create),
            )
        ),
        api_key_slot=api_key_slot,
    )


def _service(
    *,
    attempts: int = 1,
    targets: list[_AIProviderTarget] | None = None,
) -> tuple[AIGatewayService, MagicMock]:
    service = AIGatewayService(
        Settings(
            groq_api_key="groq-secret",
            groq_retry_count=attempts,
            groq_retry_backoff_seconds=0,
            ollama_enabled=False,
        ),
        MagicMock(),
    )
    create = MagicMock()
    service._provider_targets = targets or [_mock_target(create=create)]
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
    assert request["model"] == service._settings.groq_qwen_model
    assert request["temperature"] == 0
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
    assert run_log.request_payload["ai_provider"] == "groq"
    assert run_log.request_payload["ai_model"] == "qwen/qwen3-32b"
    assert run_log.model_name == "qwen/qwen3-32b"
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

    with pytest.raises(RuntimeError, match="after trying 1 provider target") as raised:
        _run(service)

    assert "provider-secret" not in str(raised.value)
    run_log = service._run_log_repository.add_run_log.call_args.args[0]
    assert run_log.success is False
    assert run_log.error_message == "RuntimeError"
    assert "private rubric" not in str(run_log.request_payload)


def test_authentication_failure_skips_bad_key_slot_and_uses_next_key() -> None:
    class ProviderAuthenticationError(Exception):
        status_code = 401

    first_key_create = MagicMock(side_effect=ProviderAuthenticationError("bad key"))
    second_key_create = MagicMock(return_value=_completion('{"value":"accepted"}'))
    service, _ = _service(
        targets=[
            _mock_target(create=first_key_create, api_key_slot=1),
            _mock_target(
                create=first_key_create,
                model="openai/gpt-oss-120b",
                api_key_slot=1,
            ),
            _mock_target(create=second_key_create, api_key_slot=2),
        ],
    )

    result = _run(service)

    assert result == _Answer(value="accepted")
    assert first_key_create.call_count == 1
    assert second_key_create.call_count == 1
    run_log = service._run_log_repository.add_run_log.call_args.args[0]
    assert run_log.success is True
    assert run_log.request_payload["api_key_slot"] == 2


def test_rate_limit_moves_to_next_model_without_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RateLimitedError(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "2.5"})

    qwen_create = MagicMock(side_effect=RateLimitedError("rate limited"))
    gpt_oss_create = MagicMock(return_value=_completion('{"value":"accepted"}'))
    service, _ = _service(
        targets=[
            _mock_target(create=qwen_create, model="qwen/qwen3-32b"),
            _mock_target(create=gpt_oss_create, model="openai/gpt-oss-120b"),
        ],
    )
    sleep_mock = MagicMock()
    monkeypatch.setattr(ai_gateway_service, "sleep", sleep_mock)

    result = _run(service)

    assert result.value == "accepted"
    assert qwen_create.call_count == 1
    assert gpt_oss_create.call_count == 1
    assert qwen_create.call_args.kwargs["response_format"]["type"] == "json_schema"
    sleep_mock.assert_not_called()
    run_log = service._run_log_repository.add_run_log.call_args.args[0]
    assert run_log.model_name == "openai/gpt-oss-120b"


def test_provider_targets_cycle_models_then_ollama_for_each_key_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(ai_gateway_service, "OpenAI", client_factory)

    service = AIGatewayService(
        Settings(
            groq_api_key_1="groq-key-1",
            groq_api_key_2="groq-key-2",
            groq_api_key_3="",
            groq_api_key_4="groq-key-4",
            groq_request_timeout_seconds=17,
            ollama_enabled=True,
            ollama_model="llama3.3:70b",
        ),
        MagicMock(),
    )

    assert [
        (target.provider, target.model, target.api_key_slot)
        for target in service._provider_targets
    ] == [
        ("groq", "qwen/qwen3-32b", 1),
        ("groq", "openai/gpt-oss-120b", 1),
        ("ollama", "llama3.3:70b", None),
        ("groq", "qwen/qwen3-32b", 2),
        ("groq", "openai/gpt-oss-120b", 2),
        ("ollama", "llama3.3:70b", None),
        ("groq", "qwen/qwen3-32b", 4),
        ("groq", "openai/gpt-oss-120b", 4),
        ("ollama", "llama3.3:70b", None),
    ]


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
            ollama_enabled=False,
        ),
        MagicMock(),
    )

    client_factory.assert_called_once_with(
        api_key="groq-secret",
        base_url="https://groq.test/openai/v1",
        timeout=17,
    )
