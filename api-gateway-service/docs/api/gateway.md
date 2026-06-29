# API Gateway Service

The API Gateway is the public backend edge for the Coding Assessment Platform.
It is intentionally thin: it does not own business data or database tables.

Design alignment:

- Recruiter UI and candidate UI should call one backend entrypoint.
- Firebase remains the recruiter identity provider.
- Candidate invite-token flows will be exposed through the gateway when built.
- Judge0/code execution must stay backend-only and must not be exposed directly
  to the frontend.
- PostgreSQL remains owned by backend domain services, not the gateway.

Current routes:

- `GET /api/v1/health`
- `GET /api/v1/gateway/services`
- `GET /api/v1/gateway/services/health`
- `GET /api/v1/auth/firebase-config`

Planned route groups:

- `/api/v1/recruiter/*` -> core platform workflows
- `/api/v1/candidate/*` -> invite-token candidate assessment flow
- `/api/v1/execution/*` -> backend-mediated code execution
- `/api/v1/evaluation/*` -> AI/code evaluation workflows
