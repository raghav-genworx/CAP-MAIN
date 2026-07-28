"""Every route keeps the credential it requires today.

Phase 5 replaces the API gateway's route-policy table
(``PUBLIC_CORE_ROUTES`` / ``ONBOARDING_CORE_ROUTES`` / the ``candidate/`` prefix
branch) with FastAPI dependencies. These tests pin the observable outcome of that
policy so the rewrite cannot silently open a route or lock one that must stay public.
"""

import pytest
from fastapi.testclient import TestClient

from .inventory import ENDPOINTS, UNAUTHENTICATED_STATUS, Auth, Endpoint

pytestmark = pytest.mark.contract

GUARDED = [e for e in ENDPOINTS if e.auth in UNAUTHENTICATED_STATUS]
PUBLIC = [e for e in ENDPOINTS if e.auth is Auth.PUBLIC]


def _call(client: TestClient, endpoint: Endpoint) -> int:
    """Issue an unauthenticated request and return the status code.

    A body is sent for verbs that take one so a route cannot pass merely because
    the request was malformed in some other way.
    """

    kwargs = {} if endpoint.method in {"GET", "DELETE"} else {"json": {}}
    response = client.request(endpoint.method, endpoint.concrete_path(), **kwargs)
    return response.status_code


@pytest.mark.parametrize("endpoint", GUARDED, ids=lambda e: f"{e.method} {e.path}")
def test_guarded_routes_reject_a_missing_credential(
    client: TestClient,
    endpoint: Endpoint,
) -> None:
    """Recruiter routes answer 401 and candidate routes 403 with no token.

    The distinction is not cosmetic: recruiter routes fail in
    ``FirebaseAuthService.verify_credentials`` (``AuthenticationError``) while
    candidate routes fail in ``get_current_candidate_session``
    (``AuthorizationError``). The frontend branches on these codes.
    """

    assert _call(client, endpoint) == UNAUTHENTICATED_STATUS[endpoint.auth]


@pytest.mark.parametrize("endpoint", GUARDED, ids=lambda e: f"{e.method} {e.path}")
def test_guarded_routes_reject_a_malformed_bearer_token(
    client: TestClient,
    rejecting_firebase: None,
    endpoint: Endpoint,
) -> None:
    """A syntactically valid but unverifiable token must not be accepted."""

    response = client.request(
        endpoint.method,
        endpoint.concrete_path(),
        headers={"Authorization": "Bearer not-a-real-token"},
        **({} if endpoint.method in {"GET", "DELETE"} else {"json": {}}),
    )

    assert response.status_code in {401, 403}


@pytest.mark.parametrize("endpoint", PUBLIC, ids=lambda e: f"{e.method} {e.path}")
def test_public_routes_do_not_demand_a_credential(
    client: TestClient,
    endpoint: Endpoint,
) -> None:
    """Invite verification and session start stay reachable without a token.

    These are the candidate's entry points -- if they ever start returning 401 or
    403, every invite link breaks.
    """

    assert _call(client, endpoint) not in {401, 403}


def test_auth_headers_cannot_be_spoofed_by_the_browser(client: TestClient) -> None:
    """The X-User-* header trust path must not be reachable without the token.

    ``get_current_user`` accepts identity headers when ``X-Internal-Service-Token``
    matches, because the gateway pre-verified the caller. A browser must never be
    able to reach it. Phase 5 deletes this path outright; until then, pin it.
    """

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "X-User-Id": "attacker-uid",
            "X-User-Email": "attacker@example.com",
            "X-User-Email-Verified": "true",
        },
    )

    assert response.status_code == 401
