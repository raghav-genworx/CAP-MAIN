# Docker Platform

This root Compose stack starts the CAP frontend, core assessment API, code
execution API, code evaluation API and worker, PostgreSQL, Redis, and Judge0.

## Start

```sh
cp .env.example .env
cp api-gateway-service/.env.example api-gateway-service/.env
cp code-evaluation-service/.env.example code-evaluation-service/.env
cp code-execution-service/.env.example code-execution-service/.env
cp core-assessment-platform-service/.env.example core-assessment-platform-service/.env
cp frontend/.env.example frontend/.env
docker compose up --build
```

Open the frontend at http://localhost:5173.

## Services

- Frontend: http://localhost:5173
- Core Assessment Platform Service: http://localhost:8002/api/v1/health
- Code Execution Service: http://localhost:8003/api/v1/health
- Code Evaluation Service: http://localhost:8004/api/v1/health
- Judge0: http://localhost:12358
- Postgres: localhost:55432
- Redis: localhost:6379

## Configuration

The stack runs with local development defaults. Root `.env` values control
shared infrastructure, published ports, and the common internal-service token.
Each backend also loads its own `.env` file; Compose overrides host-only URLs
with Docker network names where required. Core-only Groq and Brevo credentials belong in
`core-assessment-platform-service/.env`. Do not commit populated `.env` files.

Firebase `VITE_*` values belong in `frontend/.env`. Compose supplies that file
to the Vite build through a BuildKit secret, so it is not copied into an image
layer. Docker builds always use same-origin `/api/core`, `/api/execution`, and
`/api/evaluation` routes. Nginx sends all three route families to the API
gateway, which authorizes the caller before forwarding to the internal service
network.

Recruiter requests require a valid Firebase bearer token with an active
platform role. Candidate portal requests require a signed candidate session
token after the public invite verification and start calls. The gateway removes
browser-supplied internal-service headers and injects the trusted shared token
only for execution and evaluation services.

The frontend API URLs are baked into the production Vite build, so rebuild the frontend container after changing any `VITE_*` value:

```sh
docker compose build frontend
docker compose up frontend
```

The root `docker-compose.yml` is the single Compose entry point. It uses `docker/judge0/judge0.conf` so Judge0 connects to the shared Compose `postgres` and `redis` services.

## Evaluation Persistence

Evaluation jobs, source evidence, scorecards, and report metadata are stored in
the `evaluation` schema inside the shared `cap_core` PostgreSQL database. Core
tables remain in the default `public` schema. Evaluation has its own Alembic
version table, so both migration streams can safely use the same database. The
evaluation API runs migrations before starting, and its readiness endpoint
returns `503` until PostgreSQL is reachable. The worker uses row locking and
processing leases so multiple workers cannot evaluate the same pending job
concurrently.

Completed and failed evaluation evidence is retained for 365 days by default.
Override `EVALUATION_RETENTION_DAYS` and `EVALUATION_JOB_LEASE_SECONDS` in the
root `.env` when deployment policy requires different values.

`INTERNAL_SERVICE_TOKEN` must be the same for core, execution, and evaluation.
The documented local value is rejected whenever `APP_ENV` is not local,
development, or test.

## Judge0 Slim Image

The Compose stack builds a local `cap/judge0-slim:local` image from `docker/judge0/Dockerfile` instead of pulling the full `judge0/judge0:latest` image. The slim image seeds Judge0 with only four language IDs:

- `50`: C
- `54`: C++
- `62`: Java
- `71`: Python 3

The first build needs network access to download Judge0 source, Ruby gems, npm packages, and the Isolate sandbox source:

```sh
docker compose build judge0-server judge0-worker
```

Set `JUDGE0_REF` in the root `.env` if you want to build from a specific Judge0 branch, tag, or commit. The default is `master`.

If you previously ran the full Judge0 image, recreate Judge0's database state so the language table is reseeded with the slim set:

```sh
docker compose down -v
docker compose up --build
```

## Reset Data

```sh
docker compose down -v
```

This removes the local Postgres and Redis volumes.
