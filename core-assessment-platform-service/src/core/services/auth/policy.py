"""Who may call what.

Replaces the gateway's route-matching table (``PUBLIC_CORE_ROUTES``,
``ONBOARDING_CORE_ROUTES``, and the ``candidate/`` prefix branch) with FastAPI
dependencies declared on the routes themselves.

The table matched on strings, so a renamed route silently changed its own
authorization -- moving a path out of ``PUBLIC_CORE_ROUTES`` by accident would have
locked out every candidate, and moving one in would have opened it to the world.
A dependency travels with the handler and cannot drift from it.

The policy itself is unchanged:

* ``POST /candidate/verify-invite`` and ``POST /candidate/start`` -- no credential;
  a candidate has none yet.
* ``GET /auth/firebase-config`` -- no credential; public browser configuration.
* ``GET /auth/me`` and ``POST /auth/start-free-trial`` -- Firebase identity, with
  the subscription check deliberately skipped.
* All other ``/candidate/*`` -- a valid candidate session token.
* Everything else -- Firebase identity plus an active free trial.

The onboarding exemption matters: ``/auth/me`` is how the frontend discovers
whether a trial is active, and ``start-free-trial`` is how one begins. Requiring a
subscription for either would deadlock a new recruiter out of their own signup.
"""

from schemas.roles import UserRole

#: Route dependencies live in ``api.rest.dependencies``; this module holds the
#: policy those dependencies express, so the rule and its rationale stay together.
RECRUITER_ROLE = UserRole.RECRUITER

#: Routes reachable with no credential at all. Kept as data purely for the
#: contract tests to assert against -- enforcement is the absence of a dependency
#: on the handler, not a lookup here.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/candidate/verify-invite"),
        ("POST", "/candidate/start"),
        ("GET", "/auth/firebase-config"),
    }
)

#: Recruiter routes exempt from the active-subscription requirement.
ONBOARDING_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/auth/me"),
        ("POST", "/auth/start-free-trial"),
    }
)
