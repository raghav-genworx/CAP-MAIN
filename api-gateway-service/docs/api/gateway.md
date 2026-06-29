# API Gateway Service

The API Gateway is the public backend edge for the Coding Assessment Platform.
It is intentionally thin: it does not own business data or database tables.

Design alignment:

- Recruiter UI and candidate UI should call one backend entrypoint.
- Firebase remains the recruiter identity provider.
- Candidate invite-token and session flows pass through the gateway.
- Judge0/code execution must stay backend-only and must not be exposed directly
  to the frontend.
- PostgreSQL remains owned by backend domain services, not the gateway.

Current routes:

- `GET /api/v1/health`
- `GET /api/v1/gateway/services`
- `GET /api/v1/gateway/services/health`
- `GET /api/v1/auth/firebase-config`
- `/api/v1/core/*` -> core platform workflows
- `/api/v1/code-execution/*` -> code execution workflows
- `/api/v1/code-evaluation/*` -> evaluation workflows

Authorization policy:

- Recruiter requests require a Firebase bearer token and active recruiter role.
- Candidate session requests require a valid signed candidate JWT.
- Candidate invite verification, candidate session start, and Firebase browser
  configuration are public bootstrap routes.
- Browser-supplied internal service tokens are discarded. The gateway injects
  its trusted token only when forwarding to execution or evaluation.
