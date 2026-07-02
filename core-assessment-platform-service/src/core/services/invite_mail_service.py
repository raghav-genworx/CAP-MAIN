"""Assessment invitation email delivery service."""

# ruff: noqa: E501

from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import httpx

from config.settings import Settings
from core.exceptions.assessment import EmailDeliveryError

LOGGER = logging.getLogger(__name__)
INVITE_TIMEZONE = ZoneInfo("Asia/Kolkata")


class InviteMailService:
    """Build and send candidate assessment invitation emails."""

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
        """Send one candidate invite email through the configured provider."""

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
            "subject": f"You're invited: {assessment_title}",
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
                "invite_mail_delivery_failed status_code=%s request_id=%s",
                status_code,
                exc.response.headers.get("x-request-id", ""),
            )
            raise EmailDeliveryError(
                f"Invite email delivery failed with status {status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise EmailDeliveryError("Invite email delivery failed.") from exc

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
        safe_start_at = escape(_format_invite_time(start_at))
        safe_end_at = escape(_format_invite_time(end_at))
        safe_instructions = escape(instructions).replace("\n", "<br>")
        instruction_html = (
            f"""
            <tr>
              <td style="padding:0 40px 28px;">
                <div style="border-left:4px solid #2563eb;background:#eff6ff;padding:16px 18px;">
                  <p style="margin:0 0 6px;color:#1e3a8a;font-size:13px;font-weight:700;">INSTRUCTIONS</p>
                  <p style="margin:0;color:#334155;font-size:14px;line-height:1.6;">{safe_instructions}</p>
                </div>
              </td>
            </tr>
            """
            if instructions.strip()
            else ""
        )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_assessment_title}</title>
  <style>
    @media only screen and (max-width: 620px) {{
      .email-card {{ width: 100% !important; }}
      .content-cell {{ padding-left: 24px !important; padding-right: 24px !important; }}
      .detail-label, .detail-value {{ display: block !important; width: 100% !important; }}
      .detail-value {{ padding-top: 4px !important; text-align: left !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f1f5f9;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" class="email-card" width="600" cellspacing="0" cellpadding="0" border="0" style="width:600px;max-width:600px;background:#ffffff;border:1px solid #e2e8f0;">
          <tr>
            <td style="height:6px;background:#2563eb;font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td class="content-cell" style="padding:36px 40px 24px;">
              <p style="margin:0 0 12px;color:#2563eb;font-size:13px;font-weight:700;letter-spacing:.5px;">ASSESSMENT INVITATION</p>
              <h1 style="margin:0 0 18px;color:#0f172a;font-size:28px;line-height:1.25;font-weight:700;">{safe_assessment_title}</h1>
              <p style="margin:0 0 12px;color:#334155;font-size:16px;line-height:1.6;">Hello {safe_name},</p>
              <p style="margin:0;color:#334155;font-size:16px;line-height:1.6;">You have been invited to complete <strong>{safe_slot_title}</strong>. Review the schedule below before starting.</p>
            </td>
          </tr>
          <tr>
            <td class="content-cell" style="padding:0 40px 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f8fafc;border:1px solid #e2e8f0;">
                <tr>
                  <td class="detail-label" style="padding:16px 18px;color:#64748b;font-size:13px;font-weight:700;border-bottom:1px solid #e2e8f0;">STARTS</td>
                  <td class="detail-value" align="right" style="padding:16px 18px;color:#0f172a;font-size:14px;font-weight:600;border-bottom:1px solid #e2e8f0;">{safe_start_at}</td>
                </tr>
                <tr>
                  <td class="detail-label" style="padding:16px 18px;color:#64748b;font-size:13px;font-weight:700;border-bottom:1px solid #e2e8f0;">ENDS</td>
                  <td class="detail-value" align="right" style="padding:16px 18px;color:#0f172a;font-size:14px;font-weight:600;border-bottom:1px solid #e2e8f0;">{safe_end_at}</td>
                </tr>
                <tr>
                  <td class="detail-label" style="padding:16px 18px;color:#64748b;font-size:13px;font-weight:700;">DURATION</td>
                  <td class="detail-value" align="right" style="padding:16px 18px;color:#0f172a;font-size:14px;font-weight:600;">{duration_minutes} minutes</td>
                </tr>
              </table>
            </td>
          </tr>
          {instruction_html}
          <tr>
            <td class="content-cell" align="center" style="padding:0 40px 30px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td align="center" bgcolor="#2563eb" style="background:#2563eb;">
                    <a href="{safe_invite_url}" target="_blank" style="display:inline-block;padding:15px 28px;color:#ffffff;font-size:16px;font-weight:700;text-decoration:none;">Go to Assessment</a>
                  </td>
                </tr>
              </table>
              <p style="margin:18px 0 0;color:#64748b;font-size:13px;line-height:1.5;">Use a laptop or desktop browser and submit before the assessment window closes.</p>
            </td>
          </tr>
          <tr>
            <td class="content-cell" style="padding:22px 40px;background:#f8fafc;border-top:1px solid #e2e8f0;">
              <p style="margin:0 0 8px;color:#64748b;font-size:12px;line-height:1.5;">If the button does not work, open this link:</p>
              <p style="margin:0;word-break:break-all;font-size:12px;line-height:1.5;"><a href="{safe_invite_url}" style="color:#2563eb;text-decoration:underline;">{safe_invite_url}</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _format_invite_time(value: datetime) -> str:
    """Render an assessment instant in the candidate-facing IST timezone."""
    return f"{value.astimezone(INVITE_TIMEZONE):%d %b %Y, %I:%M %p} IST"
