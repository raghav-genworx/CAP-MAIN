"""The API surface must not drift while the four services are consolidated.

This is the acceptance gate for every migration phase. It compares the application's
own OpenAPI document against the hand-written inventory in ``inventory.py``, so a
route that is added, removed, renamed, or re-verbed fails here before it can reach
the frontend.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from .inventory import API_PREFIX, BROWSER_PREFIX, ENDPOINTS, Endpoint

pytestmark = pytest.mark.contract


def _openapi_surface(app: FastAPI) -> set[tuple[str, str]]:
    """Return every documented (method, path) pair the application serves.

    Read from the OpenAPI document rather than ``app.routes`` because FastAPI
    defers included routers behind ``_IncludedRouter`` wrappers, so ``app.routes``
    reports only the handful of routes registered directly on the app.
    """

    paths = app.openapi()["paths"]
    return {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
    }


def test_surface_matches_the_inventory_exactly(app: FastAPI) -> None:
    """No route may appear or disappear without updating the frozen inventory."""

    served = _openapi_surface(app)
    declared = {endpoint.key for endpoint in ENDPOINTS}

    assert served == declared, (
        f"undeclared routes being served: {sorted(served - declared)}; "
        f"declared routes missing from the app: {sorted(declared - served)}"
    )


def test_inventory_has_no_duplicate_entries() -> None:
    """A copy-paste slip in the inventory would silently weaken the gate above."""

    keys = [endpoint.key for endpoint in ENDPOINTS]

    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    "endpoint",
    [e for e in ENDPOINTS if e.sse],
    ids=lambda e: f"{e.method} {e.path}",
)
def test_sse_endpoints_are_declared_on_the_expected_method(
    app: FastAPI,
    endpoint: Endpoint,
) -> None:
    """The three streams keep their paths and verbs.

    ``ai-draft/stream`` is the only POST stream, so a refactor that assumes every
    SSE route is a GET would break the question builder.
    """

    assert endpoint.key in _openapi_surface(app)


def test_exactly_three_streams_exist() -> None:
    """Guards against a fourth stream appearing without a contract decision."""

    assert sum(1 for endpoint in ENDPOINTS if endpoint.sse) == 3


def test_browser_prefix_resolves_to_the_same_handler(client: TestClient) -> None:
    """Every inventory path answers identically under both prefixes.

    The rewrite happens in ASGI middleware, so the aliased paths deliberately do
    *not* appear in the OpenAPI document -- one operation, two spellings. Routing
    is therefore asserted by calling, not by reading the schema.
    """

    for endpoint in ENDPOINTS:
        canonical = endpoint.concrete_path()
        aliased = canonical.replace(API_PREFIX, BROWSER_PREFIX, 1)
        kwargs = {} if endpoint.method in {"GET", "DELETE"} else {"json": {}}

        direct = client.request(endpoint.method, canonical, **kwargs)
        through_prefix = client.request(endpoint.method, aliased, **kwargs)

        assert through_prefix.status_code == direct.status_code, (
            f"{endpoint.method} {aliased} answered "
            f"{through_prefix.status_code}, {canonical} answered "
            f"{direct.status_code}"
        )
        assert through_prefix.status_code != 404


def test_the_browser_prefix_is_not_duplicated_in_the_schema(app: FastAPI) -> None:
    """One operation per route, so the OpenAPI document stays single-sourced."""

    assert not [p for p in _openapi_surface(app) if p[1].startswith(BROWSER_PREFIX)]


def test_an_unknown_path_under_the_browser_prefix_still_404s(
    client: TestClient,
) -> None:
    """The rewrite must not turn the prefix into a catch-all."""

    assert client.get(f"{BROWSER_PREFIX}/not-a-real-route").status_code == 404
