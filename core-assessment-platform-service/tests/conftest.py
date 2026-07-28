"""Shared pytest fixtures for the core assessment platform service."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.rate_limit import limiter
from api.rest.app import create_app
from config.settings import Settings, get_settings

# Loopback port 1 is never listening, so a connection attempt is refused
# immediately instead of waiting on a timeout.
UNREACHABLE_DATABASE_URL = (
    "postgresql+psycopg://cap_test:cap_test@127.0.0.1:1/cap_test_unreachable"
)

#: Fixed value so no test depends on whichever Firebase project a developer's
#: frontend/.env happens to point at.
TEST_FIREBASE_PROJECT_ID = "cap-test-project"


@pytest.fixture(autouse=True)
def isolated_settings(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Pin external configuration for tests and reset cached settings.

    Settings are read from ``.env`` files, so without this a developer's local
    values decide what the suite talks to -- which has already meant unit tests
    opening connections to a remote database and fetching Firebase certificates
    from a personal project. An environment variable outranks the dotenv value in
    pydantic-settings, so every test that is not marked ``integration`` gets a
    refused-immediately database address and a fixed Firebase project.

    ``get_settings`` is ``lru_cache``-wrapped, so the cache is cleared on both sides
    of the test to stop one test's configuration leaking into the next.
    """

    if request.node.get_closest_marker("integration") is None:
        monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv("FIREBASE_PROJECT_ID", TEST_FIREBASE_PROJECT_ID)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def rejecting_firebase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make Firebase ID-token verification fail without touching the network.

    ``FirebaseAuthService.verify_credentials`` calls
    ``google.oauth2.id_token.verify_token``, which fetches Google's signing
    certificates over HTTPS. Left real, any test that sends a bogus token makes a
    live request per call -- slow, and broken on an offline runner. Stubbing the
    verifier keeps the assertion meaningful (a token that does not verify must be
    rejected) while staying hermetic.
    """

    def _reject(*args: object, **kwargs: object) -> dict[str, object]:
        raise ValueError("stubbed: token could not be verified")

    monkeypatch.setattr(
        "handlers.http_clients.firebase.id_token.verify_token",
        _reject,
    )


@pytest.fixture
def settings() -> Settings:
    """Return runtime settings built from the current environment."""

    return get_settings()


@pytest.fixture
def relaxed_rate_limits() -> Iterator[None]:
    """Disable slowapi during a test.

    The application registers a 120/minute default plus tighter per-route candidate
    limits. A test that issues several requests would otherwise trip them and fail
    for reasons unrelated to what it asserts. Tests that specifically verify rate
    limiting should not request this fixture.
    """

    original = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = original


@pytest.fixture
def app() -> FastAPI:
    """Return a freshly built application instance."""

    return create_app()


@pytest.fixture
def client(app: FastAPI, relaxed_rate_limits: None) -> Iterator[TestClient]:
    """Return a test client that surfaces handled error responses.

    ``raise_server_exceptions=False`` keeps the registered ``Exception`` handler in
    play so tests can assert the ``{detail, trace_id}`` envelope the frontend parses
    in ``frontend/src/lib/axios.ts`` instead of seeing the exception re-raised.
    """

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
