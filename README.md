# Coding Assessment Platform

CAP is a service-oriented coding assessment platform for recruiter workflows,
candidate test sessions, sandboxed execution, evaluation, ranking, and PDF
reporting.

## Architecture Guide

For a full codebase walkthrough with diagrams, service map, data model, and
"where to start reading" paths, see **[Codebase Architecture Guide](docs/CODEBASE_GUIDE.md)**
([PDF](docs/CODEBASE_GUIDE.pdf)).

## Services

The four backends were consolidated into one modular FastAPI application. It
serves every browser route, reaches code execution and evaluation in-process, and
runs long jobs in a separate Celery worker.

| Folder | Service | Local port | Responsibility |
| --- | --- | ---: | --- |
| `core-assessment-platform-service/` | Core platform | 8002 | Every `/api/v1` route: assessments, candidates, auth, question bank, notifications, execution, evaluation |
| `core-assessment-platform-service/` | Evaluation worker | — | Celery worker and beat: scoring, PDF reports, retention |
| `core-assessment-platform-service/` | PostgreSQL | 55432 | Core, evaluation, and Judge0 databases |
| `core-assessment-platform-service/` | Redis | 6380 | Judge0 queue, notification pub/sub, Celery broker |
| `core-assessment-platform-service/` | Judge0 | 12358 | Sandboxed compilation and execution |
| `frontend/` | Frontend | 5173 | Recruiter and candidate React application |

The pre-consolidation gateway (8001), execution (8003) and evaluation (8004)
services are still defined, behind the backend's `legacy` Compose profile. Nothing
calls them; they exist as the rollback target and do not start by default.

## Local Start

```bash
cp .env.example .env
cp core-assessment-platform-service/.env.example core-assessment-platform-service/.env
cp frontend/.env.example frontend/.env

cd core-assessment-platform-service && docker compose up -d --build   # database, sandbox, API, worker
cd ../frontend && docker compose up -d --build                        # the SPA
```

Each folder owns its own Compose file and is self-contained: no shared network or
volume to create first, and no root entry point. Open either folder and run
`docker compose up`.

The backend file carries PostgreSQL, Redis and Judge0 alongside the application,
so `depends_on` gates start-up properly and the migration jobs wait for a healthy
database. The frontend reaches the backend over the host on the port it publishes
(8002) rather than a shared Docker network, which is what keeps both runnable
without a setup step.

| Task | Command |
| --- | --- |
| Start the backend | `cd core-assessment-platform-service && docker compose up -d` |
| Start the SPA | `cd frontend && docker compose up -d` |
| Rebuild only the API | `cd core-assessment-platform-service && docker compose up -d --build core-assessment-platform-service` |
| Roll back to the old topology | `docker compose --profile legacy up -d` then set `EXECUTION_TRANSPORT=http EVALUATION_TRANSPORT=http` |
| Stop, keeping data | `docker compose down` in each folder |

Root `.env` values
control shared infrastructure, published ports, and shared tokens. Each
application keeps its standalone settings in its own ignored `.env` file. The
frontend build uses same-origin `/api/*` routes and reads Firebase configuration
from `frontend/.env` through a Docker build secret.

All browser API traffic passes through the API gateway. Recruiter requests are
validated against Firebase identity and the active core-platform role before
forwarding. Candidate portal requests use gateway-verified candidate session
tokens; invite verification and session start are the only public exceptions.

The core and evaluation schemas are upgraded by one-shot migration services
before either API becomes ready. Both jobs also reject model/schema drift.

Run the core migration manually from `core-assessment-platform-service/` with:

```bash
make migrate
make migration-check
```

The core baseline safely adopts a complete schema created by older CAP builds.
It rejects partial legacy schemas, and the subsequent drift check must pass
before application startup.

## Quality Gates

Run each backend service from its own directory:

```bash
uv sync --dev --frozen
uv run ruff check src
PYTHONPATH=src uv run mypy src
```

Run the frontend gates from `frontend/`:

```bash
npm ci
npm run lint
npm run build
```

Validate deployment wiring from the repository root:

```bash
docker compose config --quiet
```

Use the guarded candidate and evaluation-worker performance harness described in
[Load testing](docs/load-testing.md) for staging capacity evidence.

## Production Invariants

- Replace all documented local-only service tokens and candidate secrets.
- Configure explicit HTTPS CORS origins and an HTTPS application base URL.
- Apply both core and evaluation Alembic migrations before service startup;
  application processes never mutate database schemas.
- Keep execution and evaluation APIs behind the internal service-token boundary.
- Never expose hidden inputs, expected outputs, invite tokens, source code, or
  credentials in validation logs or candidate-facing responses.
- Run the frontend behind HTTPS. Its Nginx configuration emits CSP, frame,
  referrer, permissions, HSTS, and content-type protection headers.

See [COE readiness](docs/coe-readiness.md) for verified controls and remaining
work.
