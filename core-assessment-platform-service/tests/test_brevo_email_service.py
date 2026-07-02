"""Assessment invite email delivery boundary contract tests."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from config.settings import Settings
from core.exceptions.assessment import EmailDeliveryError
from core.services.invite_mail_service import InviteMailService


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "brevo_base_url": "https://brevo.test/v3",
        "brevo_api_key": "brevo-secret",
        "brevo_sender_email": "assessments@example.com",
        "brevo_sender_name": "CAP Assessments",
    }
    values.update(overrides)
    return Settings(**values)


def _send(service: InviteMailService) -> None:
    start_at = datetime(2026, 6, 27, 9, 0, tzinfo=UTC)
    service.send_assessment_invite(
        to_email="candidate@example.com",
        to_name="Asha <img src=x onerror=alert(1)>",
        assessment_title="Backend <script>alert(1)</script>",
        slot_title="June & July",
        invite_url="https://cap.test/invite/token' onclick='alert(1)",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        duration_minutes=60,
        instructions="Use <b>Python</b> & submit.",
    )


def test_invite_request_authenticates_and_escapes_html() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"messageId": "message-1"})

    service = InviteMailService(
        _settings(),
        transport=httpx.MockTransport(handler),
    )
    _send(service)

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/v3/smtp/email"
    assert request.headers["api-key"] == "brevo-secret"
    payload = json.loads(request.content)
    assert payload["sender"] == {
        "name": "CAP Assessments",
        "email": "assessments@example.com",
    }
    assert payload["to"] == [
        {"email": "candidate@example.com", "name": "Asha <img src=x onerror=alert(1)>"}
    ]
    html = payload["htmlContent"]
    assert "<script>" not in html
    assert "<img" not in html
    assert "<b>Python</b>" not in html
    assert "Backend &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Asha &lt;img src=x onerror=alert(1)&gt;" in html
    assert "June &amp; July" in html
    assert "token&#x27; onclick=&#x27;alert(1)" in html
    assert ">Go to Assessment</a>" in html
    assert "27 Jun 2026, 02:30 PM IST" in html
    assert "27 Jun 2026, 03:30 PM IST" in html
    assert " UTC" not in html


def test_provider_response_body_is_not_exposed_or_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            400,
            text="provider-secret and candidate data",
            headers={"x-request-id": "brevo-request-42"},
        )
    )
    service = InviteMailService(_settings(), transport=transport)

    with pytest.raises(EmailDeliveryError, match=r"status 400\.$") as raised:
        _send(service)

    assert "provider-secret" not in str(raised.value)
    assert "provider-secret" not in caplog.text
    assert "brevo-request-42" in caplog.text


def test_missing_api_key_fails_before_network_call() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(201)

    service = InviteMailService(
        _settings(brevo_api_key=""),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(EmailDeliveryError, match="BREVO_API_KEY"):
        _send(service)

    assert called is False
