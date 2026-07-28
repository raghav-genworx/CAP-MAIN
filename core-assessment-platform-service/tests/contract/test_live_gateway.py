"""What the browser actually observes, captured against a running stack.

The in-process suite exercises this application directly. It cannot see the two
seams Phase 4 and Phase 5 change: the ``/api/v1/core`` prefix, and the API gateway's
own auth policy, which short-circuits before core is ever called and does **not**
always produce the same status code core would.

Run against a live stack:

    docker compose up -d --build api-gateway-service
    CAP_GATEWAY_BASE_URL=http://localhost:8001/api/v1 uv run pytest -q -m contract

Set ``CAP_WRITE_CONTRACT_BASELINE=1`` as well to refresh
``tests/contract/baseline/gateway_unauthenticated.json``, the "before" artifact each
migration phase is compared against.
"""

from __future__ import annotations

import json
import os
import pathlib

import httpx
import pytest

from .inventory import BROWSER_UNAUTHENTICATED_STATUS, ENDPOINTS, Auth, Endpoint

pytestmark = pytest.mark.contract

GATEWAY_BASE_URL = os.environ.get("CAP_GATEWAY_BASE_URL", "").rstrip("/")
BASELINE_PATH = (
    pathlib.Path(__file__).parent / "baseline" / "gateway_unauthenticated.json"
)

requires_live_stack = pytest.mark.skipif(
    not GATEWAY_BASE_URL,
    reason="set CAP_GATEWAY_BASE_URL to run against a live stack",
)

# The browser reaches core as /api/v1/core/<path>; the gateway strips the segment.
BROWSABLE = [e for e in ENDPOINTS if e.auth is not Auth.INFRA]
GUARDED = [e for e in BROWSABLE if e.auth in BROWSER_UNAUTHENTICATED_STATUS]
PUBLIC = [e for e in BROWSABLE if e.auth is Auth.PUBLIC]


def _browser_url(endpoint: Endpoint) -> str:
    """Return the URL the SPA would call for this endpoint."""

    path = endpoint.concrete_path().removeprefix("/api/v1")
    return f"{GATEWAY_BASE_URL}/core{path}"


def _probe(endpoint: Endpoint) -> httpx.Response:
    """Issue an unauthenticated request exactly as the browser would."""

    kwargs = {} if endpoint.method in {"GET", "DELETE"} else {"json": {}}
    return httpx.request(
        endpoint.method, _browser_url(endpoint), timeout=30.0, **kwargs
    )


@requires_live_stack
@pytest.mark.parametrize("endpoint", BROWSABLE, ids=lambda e: f"{e.method} {e.path}")
def test_every_endpoint_is_reachable_through_the_gateway(endpoint: Endpoint) -> None:
    """The /api/v1/core prefix resolves for every inventory path.

    A 404 here means the gateway hop dropped the route -- the exact failure mode
    Phase 5's path-rewrite middleware could reintroduce.
    """

    assert _probe(endpoint).status_code != 404


@requires_live_stack
@pytest.mark.parametrize("endpoint", GUARDED, ids=lambda e: f"{e.method} {e.path}")
def test_browser_sees_the_expected_unauthenticated_status(
    endpoint: Endpoint,
) -> None:
    """Candidate routes must answer 401, not core's own 403.

    The gateway rejects in ``_bearer_token`` before core runs, so the browser sees
    401 for candidate routes even though core would say 403. The candidate portal
    depends on that 401 to re-mint an expired session mid-exam.
    """

    expected = BROWSER_UNAUTHENTICATED_STATUS[endpoint.auth]

    assert _probe(endpoint).status_code == expected


@requires_live_stack
@pytest.mark.parametrize("endpoint", PUBLIC, ids=lambda e: f"{e.method} {e.path}")
def test_public_routes_stay_open_through_the_gateway(endpoint: Endpoint) -> None:
    """Invite verification and session start need no credential."""

    assert _probe(endpoint).status_code not in {401, 403}


@requires_live_stack
def test_gateway_error_envelope_matches_the_application_envelope() -> None:
    """The gateway's own errors carry the same shape the frontend parses."""

    response = httpx.get(f"{GATEWAY_BASE_URL}/core/assessments", timeout=30.0)

    assert response.status_code == 401
    payload = response.json()
    assert set(payload) == {"detail", "trace_id"}
    assert payload["trace_id"]


@requires_live_stack
def test_unknown_upstream_service_is_rejected() -> None:
    """Only registered upstreams are proxied."""

    response = httpx.get(f"{GATEWAY_BASE_URL}/not-a-service/anything", timeout=30.0)

    assert response.status_code == 404


@requires_live_stack
def test_capture_baseline() -> None:
    """Record the observed surface so later phases can be diffed against it.

    Assertion-free by design: the tests above are the gate, this only writes the
    artifact when explicitly asked.
    """

    if not os.environ.get("CAP_WRITE_CONTRACT_BASELINE"):
        pytest.skip("set CAP_WRITE_CONTRACT_BASELINE=1 to refresh the baseline")

    observed = {}
    for endpoint in BROWSABLE:
        response = _probe(endpoint)
        body = (
            response.json()
            if "json" in response.headers.get("content-type", "")
            else {}
        )
        observed[f"{endpoint.method} {endpoint.path}"] = {
            "auth": endpoint.auth.value,
            "sse": endpoint.sse,
            "unauthenticated_status": response.status_code,
            "detail": body.get("detail") if isinstance(body, dict) else None,
            "envelope_keys": sorted(body) if isinstance(body, dict) else [],
        }

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
