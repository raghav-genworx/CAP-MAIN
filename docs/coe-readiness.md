# COE Readiness

This checklist is evidence for the repository-wide engineering objective. It is
not a substitute for executable gates.

## Verified Controls

- Strict Ruff and mypy checks pass across all four Python services.
- CI enforces Ruff formatting as well as linting, uses declared and locked pytest
  runners for every backend service, pins backend gates to production-aligned
  Python 3.11, treats warnings as errors, and applies bounded job timeouts; the
  exact standardized commands pass locally across all four services.
- Backend unit and contract tests cover authorization boundaries, request IDs,
  safe validation errors, execution verdict normalization, idempotent final
  submission, candidate rate limits, readiness, evaluation persistence, report
  scoping, and PDF generation.
- Core has an opt-in PostgreSQL integration contract and CI service job covering
  recruiter ownership, invite lookup, candidate context, and submission persistence.
- Core and evaluation schemas have versioned Alembic migrations, one-shot Compose
  migration jobs, and CI drift detection; application startup does not execute DDL.
- Every Python service declares its `src` test import path and test directory in
  `pyproject.toml`, so local and CI test commands are identical and require no
  shell-specific `PYTHONPATH` or test-time `sys.path` mutation.
- The core migration was verified against fresh and complete legacy PostgreSQL
  schemas, through downgrade/upgrade, and from its built non-root container image.
- Frontend lint, TypeScript build, production bundle, authenticated report
  downloads, application error recovery, candidate scorecards, safe session
  receipt recovery, invite-to-portal, save/run/review/final-submit, timer-expiry,
  and recruiter leaderboard-to-scorecard/report component journeys pass.
- The evaluation results view uses real recruiter-owned assessments only, presents
  a truthful empty state instead of fabricated candidate data, and keeps its
  tested data shaping and analytics in a dedicated view-model module.
- The recruiter assessment library is isolated from the legacy page behind a
  typed component boundary. Component tests cover loading and empty states,
  creation and keyboard navigation, test expansion semantics, column labeling,
  and prevention of nested-control events opening the assessment unexpectedly.
- The production test results workflow is no longer embedded or labeled as a
  placeholder. Its typed component owns leaderboard ordering, evaluation backfill,
  scorecard selection, and candidate/test PDF actions; focused tests verify each
  path, and candidate changes clear stale scorecard content while loading.
- Demo evaluation seeding is disabled by default in code and Compose, requires an
  explicit local opt-in, is rejected by production settings validation, and is
  confirmed disabled in the running evaluation API and worker containers.
- Evaluation workspace styling is owned by the code-evaluation feature instead of
  the global stylesheet; the exact cascade is retained and verified by lint,
  component tests, TypeScript compilation, and the production CSS bundle.
- Recruiter assessment CSV, payload, question-ordering, scoring-allocation, and
  timezone logic is isolated in a tested view-model; London and New York schedules
  use date-aware daylight-saving offsets, reject nonexistent spring-transition
  times, and preserve deterministic fall-transition behavior.
- Core independently validates assessment schedules: start and end must be
  timezone-aware and ordered, IANA timezone names must resolve, UTC storage is
  normalized, and the effective start offset is derived server-side.
- Core slot lifecycle calculation and API projection are isolated from workflow
  orchestration behind a deterministic, clock-injectable module. Tests cover
  exact start/end boundaries, manual draft/pause/close overrides, countdowns,
  aggregate assessment status precedence, and final-submission counting.
- Recruiter-only evaluation and execution traffic uses trusted internal tokens.
- Candidate final-submit responses do not serialize hidden execution evidence.
- Deterministic provider contracts cover Judge0 encoding, polling and malformed
  responses, Brevo authentication and escaped HTML, and Groq schema fallback,
  timeout configuration, sanitized failures, and prompt-minimized audit records.
- Core evaluation payload construction is isolated as a pure tested boundary;
  verdict normalization covers accepted, compilation, runtime, time-limit,
  memory-limit, execution-failure, and wrong-answer outcomes.
- Candidate CSV parsing is isolated from persistence and strictly validates
  headers, malformed quoting, email shape, duplicates, field limits, control
  characters, extra values, and the 5,000-row import ceiling.
- Printable-report text formatting is isolated from ReportLab rendering and
  directly covers path-safe filenames, source line wrapping, question analytics,
  executive summaries, schedules, durations, and memory labels.
- Third-party HTTP transport loggers are restricted to warnings so provider URLs
  cannot expose opaque execution tokens under normal service logging.
- A typed, threshold-enforcing asynchronous load harness covers candidate
  checkpoint, sample, guarded final-submit, and evaluation-worker scenarios while
  suppressing tokens, code, URLs, and response bodies from output.
- PostgreSQL and Judge0 participate in readiness instead of static health.
- Core and evaluation migrations run as one-shot Compose jobs before API startup.
- Docker build contexts exclude virtual environments, caches, local environment
  files, and Git metadata.
- Compose configuration validates with gateway, core, execution, evaluation,
  worker, database, Redis, Judge0, and frontend services.
- The final local source audit passes frontend lint, 30 component tests, TypeScript
  compilation and production bundling; backend Ruff and formatting checks, strict
  mypy across 270 source files, and 102 tests also pass, with three explicitly
  opt-in PostgreSQL integration tests skipped when their database URLs are absent.
- Final application images build successfully; both migration jobs exit cleanly,
  every API and infrastructure health check passes, and the production Nginx
  response includes CSP, COOP, HSTS, permissions, referrer, MIME-sniffing, and
  frame-denial headers.
- The production frontend uses same-origin `/api/core`, `/api/execution`, and
  `/api/evaluation` reverse proxies, keeps local-development endpoints out of its
  CSP, accepts the bounded 3 MB candidate import payload, and passed Nginx syntax,
  container health, response-header, and all three proxied service health checks.

## Remaining Completion Evidence

The full COE goal remains active until these items have authoritative evidence:

1. Add browser-level recruiter and candidate journey tests covering assessment
   creation, invite verification, autosave, timer expiry, submission, evaluation,
   leaderboard selection, and real report download; component coverage now proves
   the critical candidate and evaluation state transitions without a live browser.
2. Capture a successful CI run of the core PostgreSQL integration job; local suites
   skip that opt-in test when `CORE_TEST_DATABASE_URL` is absent. Workflow commands
   are locally verified, but an authoritative hosted-run result is still required.
3. Capture credentialed sandbox smoke evidence for Brevo and Groq; deterministic
   provider contracts are covered without external network calls.
4. Run the load harness against a production-like staging environment and retain
   capacity evidence for checkpoint, sample, final-submit, and worker throughput.
5. Continue decomposing the remaining legacy assessment pages, global stylesheet,
   and core assessment service into smaller ownership-focused modules; the
   assessment library, test results workflow, evaluation view logic and styling,
   recruiter assessment utilities, core payload and slot lifecycle projections,
   and PDF text formatting are now isolated.
6. Run authorized vulnerability scans of the final private images and frontend
   dependency lockfile, then retain the results. Docker Scout and `npm audit`
   were not executed because they may transmit private image or dependency
   metadata outside the development environment without explicit approval.
