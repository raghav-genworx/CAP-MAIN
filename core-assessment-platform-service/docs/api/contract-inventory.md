# CAP frontend ↔ backend contract inventory

Source of truth for the Phase 0 contract test suite and for router assembly during the
service consolidation. Every entry was extracted from the code, not from prose docs.

- **Frontend calls** — `frontend/src/features/*/services/*.ts` via the clients in
  `frontend/src/lib/axios.ts`.
- **Backend routes** — the `@router.*` decorators in each service's
  `src/api/rest/routes/`, with the `APIRouter(prefix=...)` applied and the
  `API_PREFIX=/api/v1` mount added.

Generated 2026-07-28. Regenerate before each phase and diff.

---

## 1. The path invariant

Every browser request reaches the backend as **`/api/v1/core/<path>`** in both
environments. Nothing else about the URL is stable, so this is the only invariant the
consolidation must preserve.

| | `VITE_API_GATEWAY_BASE_URL` | rewrite layer | backend receives |
|---|---|---|---|
| dev | `/api` (`frontend/.env.example`, compose `frontend.environment`) | `vite.config.ts` proxy `rewrite: /^\/api/ → /api/v1` | `/api/v1/core/<path>` |
| prod | `/api/v1` (`scripts/deploy_gcp_cloud_run.sh:390` build arg) | `frontend/nginx.conf` `location /api/v1/` → `proxy_pass ${API_GATEWAY_PROXY_URL}/` where that env var is `http://api-gateway-service:8000/api/v1` | `/api/v1/core/<path>` |

`frontend/src/config/env.ts` derives `coreApiBaseUrl = ${apiGatewayBaseUrl}/core`. The
gateway's `routes/proxy.py` then strips `core` and forwards to
`http://<core>:8000/api/v1/<path>`.

**Only `coreApiClient` is ever used.** `codeExecutionApiClient` and
`codeEvaluationApiClient` are constructed in `frontend/src/lib/axios.ts:56-64` and
referenced nowhere else — verified by grep across `frontend/src`. No browser traffic has
ever reached the execution or evaluation services directly.

---

## 2. Auth modes

Derived from `api-gateway-service/src/core/services/gateway_auth_service.py`
(`PUBLIC_CORE_ROUTES`, `ONBOARDING_CORE_ROUTES`, the `candidate/` prefix branch) and
cross-checked against the per-route dependencies in core.

| Mode | Gateway policy | Core dependency | Route count |
|---|---|---|---|
| `public` | in `PUBLIC_CORE_ROUTES` | none | 3 |
| `candidate` | `candidate/*` prefix → HMAC session verify | `get_current_candidate_session` | 6 |
| `recruiter-onboarding` | Firebase verify, subscription **not** required | `Depends(get_current_user)` | 2 |
| `recruiter` | Firebase verify + `subscription_status == free_trial` | `require_role(UserRole.RECRUITER)` | 44 |
| `infra` | n/a — not proxied for the browser | none | 1 |

### 2.1 ⚠️ The gateway and core disagree on candidate 401 vs 403

The gateway rejects a missing credential in `GatewayAuthService._bearer_token`
**before core is ever called**, raising `GatewayAuthenticationError` (401). Core's own
`get_current_candidate_session` raises `AuthorizationError` (403). Measured against a
running stack:

| Route | Via gateway (what the browser sees) | Direct to core |
|---|---|---|
| `GET /candidate/assessment` | **401** `"Missing bearer token"` | 403 `"Missing candidate bearer token"` |
| `POST /candidate/submit` | **401** | 403 |
| `GET /assessments` | 401 | 401 |
| `GET /auth/me` | 401 | 401 |
| `POST /candidate/verify-invite` | 422 | 422 |

This is load-bearing.
[`CandidateAssessmentPage.tsx:166`](../../../frontend/src/features/candidatePortal/components/CandidateAssessmentPage.tsx)
branches on `error.status !== 401` to transparently re-mint an expired candidate
session from the stored invite token and retry. If Phase 5 folds the gateway in and
starts returning core's 403 on those routes, the guard rethrows and **a candidate
whose session expires mid-exam gets a hard error instead of a silent reconnect.**

Phase 5 must preserve the *browser-observed* column. Both values are encoded in
`tests/contract/inventory.py` as `UNAUTHENTICATED_STATUS` (direct) and
`BROWSER_UNAUTHENTICATED_STATUS` (through the gateway), and asserted by
`tests/contract/test_live_gateway.py`.

Dependency counts confirm every route is covered with no gaps: `assessments.py` 23 routes
/ 23 `require_role`, `question_bank.py` 14 / 14, `notifications.py` 7 / 7,
`candidate_portal.py` 6 session-guarded + 2 public, `auth.py` 2 guarded + 1 public.

---

## 3. Core service — 56 routes

`✔` = exercised by the frontend. Auth column uses the modes above.

### 3.1 Assessments — `api/rest/routes/assessments.py` (prefix `/assessments`)

| ✔ | Method | Path (after `/api/v1`) | Auth | Frontend caller |
|---|---|---|---|---|
| ✔ | GET | `/assessments` | recruiter | `assessmentService.ts:31` |
| ✔ | POST | `/assessments` | recruiter | `assessmentService.ts:41` |
| ✔ | PATCH | `/assessments/{assessment_id}` | recruiter | `assessmentService.ts:52` |
| ✔ | DELETE | `/assessments/{assessment_id}` | recruiter | `assessmentService.ts:66` |
| ✔ | POST | `/assessments/{assessment_id}/questions` | recruiter | `assessmentService.ts:76` |
| ✔ | GET | `/assessments/{assessment_id}/slots` | recruiter | `assessmentService.ts:90` |
| ✔ | POST | `/assessments/{assessment_id}/slots` | recruiter | `assessmentService.ts:104` |
| ✔ | PATCH | `/assessments/slots/{slot_id}` | recruiter | `assessmentService.ts:119` |
| ✔ | POST | `/assessments/slots/{slot_id}/actions` | recruiter | `assessmentService.ts:134` |
| ✔ | POST | `/assessments/slots/{slot_id}/candidates/import` | recruiter | `assessmentService.ts:149` |
| ✔ | GET | `/assessments/slots/{slot_id}/candidates` | recruiter | `assessmentService.ts:163` |
| ✔ | POST | `/assessments/{assessment_id}/evaluations/backfill` | recruiter | `assessmentService.ts:177`, `codeEvaluationService.ts:25` |
| ✔ | GET | `/assessments/{assessment_id}/evaluations/dashboard` | recruiter | `codeEvaluationService.ts:14` |
| ✔ | POST | `/assessments/{assessment_id}/evaluations/jobs/{job_id}/retry` | recruiter | `codeEvaluationService.ts:42` |
| | GET | `/assessments/{assessment_id}/evaluations/reports` | recruiter | **unexercised** |
| ✔ | GET | `/assessments/{assessment_id}/evaluations/reports/download` | recruiter | `codeEvaluationService.ts:89` |
| ✔ | GET | `/assessments/{assessment_id}/evaluations/reports/candidates/{candidate_assessment_id}` | recruiter | `codeEvaluationService.ts:59`, `:76` |
| ✔ | GET | `/assessments/{assessment_id}/evaluations/reports/candidates/{candidate_assessment_id}/download` | recruiter | `codeEvaluationService.ts:101` |
| ✔ | GET | `/assessments/{assessment_id}/evaluations/reports/tests/{slot_id}/download` | recruiter | `codeEvaluationService.ts:114` |
| ✔ | POST | `/assessments/slots/{slot_id}/invites/send` | recruiter | `assessmentService.ts:192` |
| ✔ | POST | `/assessments/candidate-assessments/{candidate_assessment_id}/invite/resend` | recruiter | `assessmentService.ts:206` |
| ✔ | GET | `/assessments/slots/{slot_id}/monitoring` | recruiter | `assessmentService.ts:220` |
| ✔ | GET | `/assessments/slots/{slot_id}/monitoring/stream` **(SSE)** | recruiter | `assessmentService.ts:237` |

The three `.../download` routes return a buffered `Response` with an explicit
`Content-Disposition` header — not `FileResponse`. `frontend/.../codeEvaluationService.ts:132`
parses `filename="…"` out of that header, so the header is part of the contract.

### 3.2 Auth — `routes/auth.py` (prefix `/auth`)

| ✔ | Method | Path | Auth | Frontend caller |
|---|---|---|---|---|
| | GET | `/auth/firebase-config` | public | **unexercised** — the SPA reads `VITE_FIREBASE_*` directly via `config/env.ts` |
| ✔ | GET | `/auth/me` | recruiter-onboarding | `authService.ts:23` |
| ✔ | POST | `/auth/start-free-trial` | recruiter-onboarding | `authService.ts:32` |

`GET /auth/me` is also called server-to-server by the gateway on **every** recruiter
request (`gateway_auth_service.py:150`). Removing that hop is a goal of the consolidation.

### 3.3 Candidate portal — `routes/candidate_portal.py` (prefix `/candidate`)

| ✔ | Method | Path | Auth | Rate limit | Frontend caller |
|---|---|---|---|---|---|
| ✔ | POST | `/candidate/verify-invite` | **public** | `10/minute` | `candidatePortalService.ts:25` |
| ✔ | POST | `/candidate/start` | **public** | `5/minute` | `candidatePortalService.ts:35` |
| ✔ | GET | `/candidate/assessment` | candidate | — | `candidatePortalService.ts:45` |
| ✔ | POST | `/candidate/checkpoint` | candidate | `60/minute` | `candidatePortalService.ts:58` |
| ✔ | POST | `/candidate/proctoring-events` | candidate | `120/minute` | `candidatePortalService.ts:76` |
| ✔ | POST | `/candidate/run-sample` | candidate | `30/minute` | `candidatePortalService.ts:88` |
| ✔ | POST | `/candidate/hidden-check` | candidate | `5/minute` | `candidatePortalService.ts:102` |
| ✔ | POST | `/candidate/submit` | candidate | `5/minute` | `candidatePortalService.ts:116` |

Per-route limits are the real abuse controls and must survive verbatim. `GET /candidate/assessment`
is the hidden-test containment boundary: its `CandidateAssessmentPortalResponse` must never
carry hidden test cases or reference solutions.

### 3.4 Notifications — `routes/notifications.py` (prefix `/notifications`)

| ✔ | Method | Path | Auth | Frontend caller |
|---|---|---|---|---|
| ✔ | GET | `/notifications` | recruiter | `notificationService.ts:20` |
| ✔ | GET | `/notifications/unread-count` | recruiter | `notificationService.ts:92` |
| ✔ | GET | `/notifications/stream` **(SSE)** | recruiter | `notificationService.ts:38` |
| ✔ | POST | `/notifications/read-all` | recruiter | `notificationService.ts:114` |
| ✔ | POST | `/notifications/{notification_id}/read` | recruiter | `notificationService.ts:103` |
| ✔ | GET | `/notifications/settings` | recruiter | `notificationService.ts:125` |
| ✔ | PUT | `/notifications/settings` | recruiter | `notificationService.ts:136` |

⚠️ `docs/CODEBASE_GUIDE.md` documents `PATCH /notifications/{id}/read` and omits
`read-all`. The code is **POST** for both, and frontend and backend agree. The guide is
wrong; trust this table.

### 3.5 Question bank — `routes/question_bank.py` (prefix `/question-bank`)

| ✔ | Method | Path | Auth | Frontend caller |
|---|---|---|---|---|
| ✔ | GET | `/question-bank/questions` | recruiter | `questionBankService.ts:157` |
| ✔ | POST | `/question-bank/questions` | recruiter | `questionBankService.ts:176` |
| ✔ | POST | `/question-bank/questions/bulk-import` | recruiter | `questionBankService.ts:190` |
| ✔ | POST | `/question-bank/questions/ai-draft` | recruiter | `questionBankService.ts:229` |
| ✔ | POST | `/question-bank/questions/ai-draft/stream` **(SSE, POST)** | recruiter | `questionBankService.ts:248` |
| ✔ | POST | `/question-bank/questions/validate-draft` | recruiter | `questionBankService.ts:346` |
| ✔ | POST | `/question-bank/questions/refine-test-cases` | recruiter | `questionBankService.ts:362` |
| ✔ | POST | `/question-bank/questions/refine-solution` | recruiter | `questionBankService.ts:378` |
| ✔ | PATCH | `/question-bank/questions/{question_id}` | recruiter | `questionBankService.ts:205` |
| ✔ | DELETE | `/question-bank/questions/{question_id}` | recruiter | `questionBankService.ts:219` |
| ✔ | GET | `/question-bank/groups` | recruiter | `questionBankService.ts:393` |
| ✔ | POST | `/question-bank/groups` | recruiter | `questionBankService.ts:410` |
| ✔ | PATCH | `/question-bank/groups/{group_id}` | recruiter | `questionBankService.ts:425` |
| ✔ | DELETE | `/question-bank/groups/{group_id}` | recruiter | `questionBankService.ts:439` |

The AI draft stream is the only **POST** SSE endpoint — route-ordering and body handling
both matter when it moves to `routes/sse.py`.

### 3.6 Health — `routes/health.py` (no prefix)

| ✔ | Method | Path | Auth | Consumer |
|---|---|---|---|---|
| | GET | `/health` | infra | `compose.backend.yml` `x-api-healthcheck`, Cloud Run probes |

---

## 4. Routes to be deleted (no browser consumer)

None of these are reachable from `frontend/src`. All disappear in Phases 4–5.

| Service | Routes | Note |
|---|---|---|
| `code-execution-service` | `POST /executions`, `POST /executions/batch`, `GET /executions/languages` | Reachable today by any subscribed recruiter: the gateway falls through to recruiter auth for `code-execution` and then injects `X-Internal-Service-Token` (`gateway_service.py:168-171`) |
| `code-evaluation-service` | 12 routes under `/evaluations` incl. `POST /evaluations/worker/process-pending` | Same exposure path |
| `api-gateway-service` | `/{service_name}/{path:path}` proxy, `GET /gateway/services`, `GET /gateway/services/health`, `GET /auth/firebase-config` | Proxy and catalog become unnecessary; `/gateway/*` has no frontend reference |

Both internal services are additionally deployed `--allow-unauthenticated`
(`scripts/deploy_gcp_cloud_run.sh:242`), so they are internet-facing today.

---

## 5. Contract drift found while building this inventory

| # | Finding | Impact | Action |
|---|---|---|---|
| 1 | `recruiterService.ts:5` calls `GET /recruiters`. **No such backend route exists** in any of the four services. | Would 404. `useRecruiters.ts` is the only consumer and is imported by no component — dead code. | Delete `recruiterService.ts` + `useRecruiters.ts` in Phase 6, or add the route if the dashboard needs it. Do **not** add it to the contract suite. |
| 2 | `codeExecutionApiClient` / `codeEvaluationApiClient` unused. | None today; they document a browser→internal path that must never work. | Delete in Phase 6 along with their `env.ts` base URLs. |
| 3 | `GET /assessments/{id}/evaluations/reports` unexercised — only the `/download` variant is called. | Dead endpoint. | Keep through Phase 5 (zero-risk), decide in Phase 6. |
| 4 | `GET /auth/firebase-config` exists in **both** core and the gateway; the SPA uses neither. | Dead in both. | Core's copy is retained (public, harmless); the gateway's is deleted with the gateway. |
| 5 | `CODEBASE_GUIDE.md` §API Surface lists `PATCH /notifications/{id}/read`, omits `read-all`, and shows `/candidate/save-draft` instead of `/candidate/checkpoint`. | Docs only. | Correct the guide in Phase 6. |
| 6 | `CODEBASE_GUIDE.md` links `docs/coe-readiness.md` and `docs/load-testing.md`; neither file exists. | Broken links. | Create or delink in Phase 6. |
| 7 | Gateway returns 401 where core returns 403 on unauthenticated candidate routes (§2.1). | Breaks mid-exam session recovery if Phase 5 gets it wrong. | Encoded in `inventory.py` and asserted by the live contract tests. |

---

## 6. Cross-cutting response contracts

These are consumed by shared frontend code and must stay byte-identical.

**Error envelope** — every handler in `api/middleware/error_handler.py` returns:

```json
{ "detail": "<string | validation-error array>", "trace_id": "<request id>" }
```

`frontend/src/lib/axios.ts:78-94` reads `body.detail` (string, or an array of
`{msg}` objects joined with `"; "`), `body.trace_id`, and falls back to the
`x-request-id` response header. Status codes: `COEApplicationError.status_code`,
`422` for `RequestValidationError` (with `input`/`ctx`/`url` stripped by
`_safe_validation_errors`), `500` for anything unhandled with a fixed
`"Internal server error"` detail.

**Request correlation** — `X-Request-ID` echoed on every response by
`api/middleware/logging.py`; a client-supplied value is honoured only if it matches
`^[A-Za-z0-9._-]{1,128}$`, otherwise a fresh `uuid4().hex` is used.

**SSE framing** — all three streams are consumed with `fetch` + `response.body.getReader()`
and an `Authorization` header, **not** `EventSource`. Each client asserts
`content-type` contains `text/event-stream` (e.g. `assessmentService.ts:255`).
Required response headers, currently added by the gateway's `_proxy_headers` and
becoming the app's responsibility in Phase 5:

```
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no
```

`frontend/nginx.conf` already sets `proxy_buffering off` and `proxy_read_timeout 300s`.

---

## 7. Totals

| Scope | Count |
|---|---|
| Core routes defined | 56 |
| Core routes exercised by the frontend | 53 |
| Core routes unexercised | 3 (`/health` infra-only, `/auth/firebase-config`, `/assessments/{id}/evaluations/reports`) |
| SSE endpoints | 3 |
| Frontend calls with no backend route | 1 (`GET /recruiters`, dead) |
| Internal routes to delete | 19 (3 execution + 12 evaluation + 4 gateway) |
