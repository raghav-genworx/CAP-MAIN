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

| Compose project | Service | Local port | Responsibility |
| --- | --- | ---: | --- |
| `cap-frontend` | Frontend | 5173 | Recruiter and candidate React application |
| `cap-backend` | Core platform | 8002 | Every `/api/v1` route: assessments, candidates, auth, question bank, notifications, execution, evaluation |
| `cap-backend` | Evaluation worker | — | Celery worker and beat: scoring, PDF reports, retention |
| `cap-infra` | Judge0 | 12358 | Sandboxed compilation and execution |
| `cap-infra` | PostgreSQL | 55432 | Core, evaluation, and Judge0 databases |
| `cap-infra` | Redis | 6379 | Judge0 queue, notification pub/sub, Celery broker |

`compose.legacy.yml` still defines the pre-consolidation gateway (8001),
execution (8003) and evaluation (8004) services. Nothing calls them; they exist
as the rollback target and are not started by default.

## Local Start

```bash
cp .env.example .env
cp api-gateway-service/.env.example api-gateway-service/.env
cp code-evaluation-service/.env.example code-evaluation-service/.env
cp code-execution-service/.env.example code-execution-service/.env
cp core-assessment-platform-service/.env.example core-assessment-platform-service/.env
cp frontend/.env.example frontend/.env
make up
```

Infrastructure, backend and frontend are **independent Compose projects** sharing
one external network, so any one can be rebuilt or restarted without cycling the
others. `make up` creates the shared network and reports volume, then starts them
in order; `make ps` shows all projects and `make down` stops them.

Start order matters, because `depends_on` does not span Compose projects: the
backend blocks on the database itself (`python -m wait_for_db`) rather than
relying on a healthcheck condition it can no longer see.

| Command | Effect |
| --- | --- |
| `make up` | Network, volume, then infra + backend + frontend |
| `make up-backend` | Rebuild and restart only the backend |
| `make up-frontend` | Rebuild and restart only the SPA |
| `make up-legacy` | Start the pre-consolidation services, for rollback |
| `make down` | Stop every project, keeping volumes |
| `make nuke` | Also drop the report volume and the shared network |

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
