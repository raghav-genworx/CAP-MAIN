"""Candidate public-entry rate-limit tests."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from api.rest.app import create_app
from api.rest.dependencies import get_assessment_service
from schemas.assessments import CandidateAssessmentStatus
from schemas.candidate_portal import CandidateInviteVerificationResponse


class _InviteService:
    def verify_invite(self, _token: str) -> CandidateInviteVerificationResponse:
        now = datetime.now(UTC)
        return CandidateInviteVerificationResponse(
            candidate_name="Candidate One",
            candidate_email="candidate@example.com",
            assessment_id="assessment-1",
            assessment_title="Backend Assessment",
            slot_id="slot-1",
            slot_title="Morning Batch",
            instructions="Read each question carefully.",
            duration_minutes=60,
            start_at=now - timedelta(minutes=5),
            end_at=now + timedelta(minutes=55),
            allow_resume=True,
            status=CandidateAssessmentStatus.NOT_STARTED,
            can_start=True,
        )


def test_invite_verification_is_rate_limited() -> None:
    app = create_app()
    app.dependency_overrides[get_assessment_service] = lambda: _InviteService()

    with TestClient(app) as client:
        responses = [
            client.post(
                "/api/v1/candidate/verify-invite",
                json={"token": "opaque-invite-token"},
            )
            for _ in range(11)
        ]

    assert all(response.status_code == 200 for response in responses[:10])
    assert responses[10].status_code == 429
