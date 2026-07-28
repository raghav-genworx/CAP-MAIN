"""The frontend-facing API surface, frozen as data.

This list is written by hand from ``docs/api/contract-inventory.md`` and is
deliberately **not** derived from the running application -- a generated list would
mirror whatever the app happens to do and assert nothing. Any route added, removed,
renamed, or re-verbed makes ``test_route_surface.py`` fail, which is the point: the
consolidation must not move a single frontend-visible path.

Update this file only together with a deliberate, reviewed contract change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

API_PREFIX = "/api/v1"

# The browser reaches the backend as /api/v1/core/<path> in every environment. Phase 5
# folds the gateway in and serves that prefix from this application directly.
BROWSER_PREFIX = f"{API_PREFIX}/core"


class Auth(Enum):
    """How a route authenticates the caller."""

    PUBLIC = "public"
    CANDIDATE = "candidate"
    RECRUITER_ONBOARDING = "recruiter-onboarding"
    RECRUITER = "recruiter"
    INFRA = "infra"


#: Status when calling this application directly with no credential, i.e. what
#: core's own dependencies produce.
UNAUTHENTICATED_STATUS = {
    # FirebaseAuthService.verify_credentials -> AuthenticationError (401)
    Auth.RECRUITER: 401,
    Auth.RECRUITER_ONBOARDING: 401,
    # Phase 5: aligned with what the browser has always observed. Was 403
    # (AuthorizationError); a missing credential is unauthenticated, and the
    # candidate portal's mid-exam session recovery keys on 401.
    Auth.CANDIDATE: 401,
}

#: Status the *browser* observes with no credential, i.e. through the API gateway.
#:
#: These differ for candidate routes and the difference is load-bearing. The gateway
#: short-circuits in ``GatewayAuthService._bearer_token`` and raises
#: ``GatewayAuthenticationError`` (401) before core is ever called, whereas core's
#: ``get_current_candidate_session`` raises ``AuthorizationError`` (403).
#:
#: ``frontend/.../CandidateAssessmentPage.tsx:166`` branches on ``error.status !== 401``
#: to transparently re-mint an expired candidate session from the stored invite token.
#: If Phase 5 folds the gateway in and starts returning 403 there, that recovery path
#: stops firing and a candidate whose session expires mid-exam sees a hard error
#: instead of a silent reconnect.
#:
#: Phase 5 must preserve THESE values, not the direct ones above.
BROWSER_UNAUTHENTICATED_STATUS = {
    Auth.RECRUITER: 401,
    Auth.RECRUITER_ONBOARDING: 401,
    Auth.CANDIDATE: 401,
}


@dataclass(frozen=True)
class Endpoint:
    """One frontend-visible endpoint."""

    method: str
    path: str
    auth: Auth
    sse: bool = False
    #: False for routes that exist but no frontend code calls.
    exercised: bool = True

    @property
    def key(self) -> tuple[str, str]:
        """Return the (method, path) pair used for set comparison."""

        return (self.method, self.path)

    def concrete_path(self, placeholder: str = "x") -> str:
        """Return the path with every ``{param}`` replaced by a usable value."""

        segments = [
            placeholder if part.startswith("{") and part.endswith("}") else part
            for part in self.path.split("/")
        ]
        return "/".join(segments)


def _e(
    method: str,
    path: str,
    auth: Auth,
    *,
    sse: bool = False,
    exercised: bool = True,
) -> Endpoint:
    return Endpoint(method, f"{API_PREFIX}{path}", auth, sse=sse, exercised=exercised)


ASSESSMENTS: tuple[Endpoint, ...] = (
    _e("GET", "/assessments", Auth.RECRUITER),
    _e("POST", "/assessments", Auth.RECRUITER),
    _e("PATCH", "/assessments/{assessment_id}", Auth.RECRUITER),
    _e("DELETE", "/assessments/{assessment_id}", Auth.RECRUITER),
    _e("POST", "/assessments/{assessment_id}/questions", Auth.RECRUITER),
    _e("GET", "/assessments/{assessment_id}/slots", Auth.RECRUITER),
    _e("POST", "/assessments/{assessment_id}/slots", Auth.RECRUITER),
    _e("PATCH", "/assessments/slots/{slot_id}", Auth.RECRUITER),
    _e("POST", "/assessments/slots/{slot_id}/actions", Auth.RECRUITER),
    _e("POST", "/assessments/slots/{slot_id}/candidates/import", Auth.RECRUITER),
    _e("GET", "/assessments/slots/{slot_id}/candidates", Auth.RECRUITER),
    _e("POST", "/assessments/{assessment_id}/evaluations/backfill", Auth.RECRUITER),
    _e("GET", "/assessments/{assessment_id}/evaluations/dashboard", Auth.RECRUITER),
    _e(
        "POST",
        "/assessments/{assessment_id}/evaluations/jobs/{job_id}/retry",
        Auth.RECRUITER,
    ),
    _e(
        "GET",
        "/assessments/{assessment_id}/evaluations/reports",
        Auth.RECRUITER,
        exercised=False,
    ),
    _e(
        "GET",
        "/assessments/{assessment_id}/evaluations/reports/download",
        Auth.RECRUITER,
    ),
    _e(
        "GET",
        "/assessments/{assessment_id}/evaluations/reports/candidates"
        "/{candidate_assessment_id}",
        Auth.RECRUITER,
    ),
    _e(
        "GET",
        "/assessments/{assessment_id}/evaluations/reports/candidates"
        "/{candidate_assessment_id}/download",
        Auth.RECRUITER,
    ),
    _e(
        "GET",
        "/assessments/{assessment_id}/evaluations/reports/tests/{slot_id}/download",
        Auth.RECRUITER,
    ),
    _e("POST", "/assessments/slots/{slot_id}/invites/send", Auth.RECRUITER),
    _e(
        "POST",
        "/assessments/candidate-assessments/{candidate_assessment_id}/invite/resend",
        Auth.RECRUITER,
    ),
    _e("GET", "/assessments/slots/{slot_id}/monitoring", Auth.RECRUITER),
    _e(
        "GET",
        "/assessments/slots/{slot_id}/monitoring/stream",
        Auth.RECRUITER,
        sse=True,
    ),
)

AUTH: tuple[Endpoint, ...] = (
    _e("GET", "/auth/firebase-config", Auth.PUBLIC, exercised=False),
    _e("GET", "/auth/me", Auth.RECRUITER_ONBOARDING),
    _e("POST", "/auth/start-free-trial", Auth.RECRUITER_ONBOARDING),
)

CANDIDATE_PORTAL: tuple[Endpoint, ...] = (
    _e("POST", "/candidate/verify-invite", Auth.PUBLIC),
    _e("POST", "/candidate/start", Auth.PUBLIC),
    _e("GET", "/candidate/assessment", Auth.CANDIDATE),
    _e("POST", "/candidate/checkpoint", Auth.CANDIDATE),
    _e("POST", "/candidate/proctoring-events", Auth.CANDIDATE),
    _e("POST", "/candidate/run-sample", Auth.CANDIDATE),
    _e("POST", "/candidate/hidden-check", Auth.CANDIDATE),
    _e("POST", "/candidate/submit", Auth.CANDIDATE),
)

NOTIFICATIONS: tuple[Endpoint, ...] = (
    _e("GET", "/notifications", Auth.RECRUITER),
    _e("GET", "/notifications/unread-count", Auth.RECRUITER),
    _e("GET", "/notifications/stream", Auth.RECRUITER, sse=True),
    _e("POST", "/notifications/read-all", Auth.RECRUITER),
    _e("POST", "/notifications/{notification_id}/read", Auth.RECRUITER),
    _e("GET", "/notifications/settings", Auth.RECRUITER),
    _e("PUT", "/notifications/settings", Auth.RECRUITER),
)

QUESTION_BANK: tuple[Endpoint, ...] = (
    _e("GET", "/question-bank/questions", Auth.RECRUITER),
    _e("POST", "/question-bank/questions", Auth.RECRUITER),
    _e("POST", "/question-bank/questions/bulk-import", Auth.RECRUITER),
    _e("POST", "/question-bank/questions/ai-draft", Auth.RECRUITER),
    _e("POST", "/question-bank/questions/ai-draft/stream", Auth.RECRUITER, sse=True),
    _e("POST", "/question-bank/questions/validate-draft", Auth.RECRUITER),
    _e("POST", "/question-bank/questions/refine-test-cases", Auth.RECRUITER),
    _e("POST", "/question-bank/questions/refine-solution", Auth.RECRUITER),
    _e("PATCH", "/question-bank/questions/{question_id}", Auth.RECRUITER),
    _e("DELETE", "/question-bank/questions/{question_id}", Auth.RECRUITER),
    _e("GET", "/question-bank/groups", Auth.RECRUITER),
    _e("POST", "/question-bank/groups", Auth.RECRUITER),
    _e("PATCH", "/question-bank/groups/{group_id}", Auth.RECRUITER),
    _e("DELETE", "/question-bank/groups/{group_id}", Auth.RECRUITER),
)

HEALTH: tuple[Endpoint, ...] = (_e("GET", "/health", Auth.INFRA, exercised=False),)

ENDPOINTS: tuple[Endpoint, ...] = (
    *ASSESSMENTS,
    *AUTH,
    *CANDIDATE_PORTAL,
    *NOTIFICATIONS,
    *QUESTION_BANK,
    *HEALTH,
)

#: Routes that must never be reachable from the browser. Phase 4 deletes the
#: execution and evaluation routers; Phase 5 deletes the gateway's own routes.
FORBIDDEN_BROWSER_PATHS: tuple[str, ...] = (
    f"{API_PREFIX}/executions",
    f"{API_PREFIX}/executions/batch",
    f"{API_PREFIX}/executions/languages",
    f"{API_PREFIX}/evaluations/jobs",
    f"{API_PREFIX}/evaluations/worker/process-pending",
    f"{BROWSER_PREFIX}-execution/executions",
    f"{BROWSER_PREFIX}-evaluation/evaluations/jobs",
)
