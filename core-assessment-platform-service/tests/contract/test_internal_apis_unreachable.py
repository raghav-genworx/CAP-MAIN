"""The browser must not be able to reach the execution or evaluation APIs.

Before this change the gateway proxied ``/api/v1/code-execution/*`` and
``/api/v1/code-evaluation/*`` and *injected* ``X-Internal-Service-Token`` on the
way through, so any recruiter with an active trial could submit code to Judge0 or
read evaluation data directly. Both upstream services are additionally deployed
``--allow-unauthenticated``.

No frontend code ever called those paths, so closing them changed no contract --
which is exactly why this needs a test: nothing else would notice a regression.
"""

import os

import httpx
import pytest

pytestmark = pytest.mark.contract

GATEWAY_BASE_URL = os.environ.get("CAP_GATEWAY_BASE_URL", "").rstrip("/")

requires_live_stack = pytest.mark.skipif(
    not GATEWAY_BASE_URL,
    reason="set CAP_GATEWAY_BASE_URL to run against a live stack",
)

#: Paths that used to be proxied. Includes the token-guarded write endpoints and
#: the report reads, since both leak.
FORBIDDEN = [
    ("POST", "/code-execution/executions"),
    ("POST", "/code-execution/executions/batch"),
    ("GET", "/code-execution/executions/languages"),
    ("POST", "/code-evaluation/evaluations/jobs"),
    ("POST", "/code-evaluation/evaluations/worker/process-pending"),
    ("GET", "/code-evaluation/evaluations/assessment/any/leaderboard"),
]


@requires_live_stack
@pytest.mark.parametrize(
    ("method", "path"), FORBIDDEN, ids=[f"{m} {p}" for m, p in FORBIDDEN]
)
def test_internal_apis_are_not_proxied(method: str, path: str) -> None:
    """The gateway rejects the route outright rather than forwarding it.

    404 is the expected answer: the upstream is no longer registered, so the
    gateway cannot route there regardless of what credential is presented.
    """

    response = httpx.request(
        method,
        f"{GATEWAY_BASE_URL}{path}",
        json={} if method == "POST" else None,
        timeout=30.0,
    )

    assert response.status_code == 404


@requires_live_stack
def test_a_valid_looking_recruiter_token_still_cannot_reach_them() -> None:
    """Authentication is not the control here -- the route simply does not exist.

    Guards against a future change that re-registers the upstream and relies on
    auth alone, which is the arrangement that produced the hole.
    """

    response = httpx.post(
        f"{GATEWAY_BASE_URL}/code-execution/executions/batch",
        headers={"Authorization": "Bearer looks-like-a-firebase-token"},
        json={"source_code": "print(1)", "language": "python", "test_cases": []},
        timeout=30.0,
    )

    assert response.status_code == 404


@requires_live_stack
def test_the_core_upstream_is_still_reachable() -> None:
    """The one upstream the browser does use must keep working."""

    response = httpx.get(f"{GATEWAY_BASE_URL}/core/assessments", timeout=30.0)

    # 401 because unauthenticated -- proving the route resolved and reached auth.
    assert response.status_code == 401
