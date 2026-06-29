"""Transactional email adapter for Brevo invite delivery."""

from __future__ import annotations

import logging
from datetime import datetime
from html import escape

import httpx

from config.settings import Settings
from core.exceptions.assessment import EmailDeliveryError

LOGGER = logging.getLogger(__name__)


class BrevoEmailService:
    """Send invite emails through the Brevo transactional email API."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def send_assessment_invite(
        self,
        *,
        to_email: str,
        to_name: str,
        assessment_title: str,
        slot_title: str,
        invite_url: str,
        start_at: datetime,
        end_at: datetime,
        duration_minutes: int,
        instructions: str,
    ) -> None:
        """Send one candidate invite email."""

        if not self._settings.brevo_api_key.strip():
            raise EmailDeliveryError("BREVO_API_KEY is not configured")
        if not self._settings.brevo_sender_email.strip():
            raise EmailDeliveryError("BREVO_SENDER_EMAIL is not configured")

        payload = {
            "sender": {
                "name": self._settings.brevo_sender_name,
                "email": self._settings.brevo_sender_email,
            },
            "to": [{"email": to_email, "name": to_name}],
            "subject": f"{assessment_title} assessment invite",
            "htmlContent": self._html_body(
                to_name=to_name,
                assessment_title=assessment_title,
                slot_title=slot_title,
                invite_url=invite_url,
                start_at=start_at,
                end_at=end_at,
                duration_minutes=duration_minutes,
                instructions=instructions,
            ),
        }
        headers = {
            "api-key": self._settings.brevo_api_key,
            "content-type": "application/json",
            "accept": "application/json",
        }

        try:
            with httpx.Client(
                base_url=self._settings.brevo_base_url.rstrip("/"),
                timeout=self._settings.brevo_request_timeout_seconds,
                headers=headers,
                transport=self._transport,
            ) as client:
                response = client.post("/smtp/email", json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            LOGGER.warning(
                "brevo_invite_delivery_failed status_code=%s request_id=%s",
                status_code,
                exc.response.headers.get("x-request-id", ""),
            )
            raise EmailDeliveryError(
                f"Brevo invite delivery failed with status {status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise EmailDeliveryError("Brevo invite delivery failed.") from exc

    @staticmethod
    def _html_body(
        *,
        to_name: str,
        assessment_title: str,
        slot_title: str,
        invite_url: str,
        start_at: datetime,
        end_at: datetime,
        duration_minutes: int,
        instructions: str,
    ) -> str:
        safe_name = escape(to_name)
        safe_assessment_title = escape(assessment_title)
        safe_slot_title = escape(slot_title)
        safe_invite_url = escape(invite_url, quote=True)
        safe_instructions = escape(instructions)
        instruction_html = (
            f"<p style='white-space:pre-wrap'>{safe_instructions}</p>"
            if instructions
            else ""
        )
        return (
            f"<h2>{safe_assessment_title}</h2>"
            f"<p>Hello {safe_name},</p>"
            "<p>You have been invited to attend the "
            f"<strong>{safe_slot_title}</strong> coding assessment.</p>"
            f"<p><strong>Window:</strong> {start_at.isoformat()} "
            f"to {end_at.isoformat()}</p>"
            f"<p><strong>Duration:</strong> {duration_minutes} minutes</p>"
            f"{instruction_html}"
            f"<p><a href='{safe_invite_url}'>Open assessment invite</a></p>"
            "<p>Please use the invite link on a laptop or desktop browser and "
            "complete the test before the time window closes.</p>"
        )
