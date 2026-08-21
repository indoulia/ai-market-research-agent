# EPIC-M1.132 — API Contract & BFF Foundation

**Track:** API
**Status:** DONE
**Execution Status:** MERGED (PR #147, commit ee4f05e)
**Priority:** P0

## Objective
Create the stable API boundary consumed by the Flutter application, with versioned contracts, consistent envelopes, pagination, filtering, errors, caching and observability. The Flutter app must never depend directly on database models or internal MRA services.

## Scope
- Establish `/api/v1` contract namespace.
- Define OpenAPI as the contract source of truth.
- Define DTOs separate from persistence/domain models.
- Standardize success/error envelopes.
- Define correlation/request IDs and server timestamps.
- Define pagination, sorting and filtering conventions.
- Define ETag/Last-Modified or equivalent cache semantics where useful.
- Define rate limits and retry semantics.
- Define authentication/authorization integration points.
- Define API compatibility/versioning rules.
- Add contract tests that can run independently of Flutter.
- Publish generated client/schema artifacts for Flutter consumption.

## Canonical Envelope
Success: `{ "data": <T>, "meta": { "requestId": "...", "timestamp": "..." } }`

Error: `{ "error": { "code": "MRA_*", "message": "safe user-facing message", "details": {}, "retryable": false }, "meta": { "requestId": "...", "timestamp": "..." } }`

## Initial Contracts
- `GET /api/v1/health`
- `GET /api/v1/app/bootstrap`
- `GET /api/v1/recommendations`
- `GET /api/v1/recommendations/{recommendationId}`
- `GET /api/v1/recommendations/{recommendationId}/history`
- `GET /api/v1/recommendations/{recommendationId}/events`
- `GET /api/v1/discoveries`
- `GET /api/v1/market/summary`
- `GET /api/v1/news`
- `GET /api/v1/events`
- `POST /api/v1/recommendations/{recommendationId}/feedback`
- `GET /api/v1/preferences`
- `PUT /api/v1/preferences`

## Acceptance Criteria
- OpenAPI contract is versioned and reviewable.
- Flutter can generate/use a typed client from the contract.
- No UI depends on internal database schemas.
- Error and pagination behavior is consistent across endpoints.
- Contract tests fail on breaking changes.

## Parallelization
API team owns this EPIC first. UI EPICs may mock these contracts but must not invent alternate payload shapes.

## Dependencies
M1.90, M1.93, M1.118, M1.119, M1.120, M1.121.

**Dependency note (2026-08-21):** M1.90 and M1.93 are `DONE` on `main`. M1.118-121 (event/schedule orchestration, real-time outcome monitor, event-driven refresh, market calendar) are still `APPROVED`/not implemented. This EPIC's actual scope — the versioned contract envelope, DTO boundary, pagination/sort/error/rate-limit conventions, and the `health`/`bootstrap` endpoints — does not require M1.118-121's runtime behavior to exist; those EPICs only affect the *content* of later, data-bearing endpoints (`/events`, `/market/summary`, freshness metadata), not the foundation itself. Proceeding with foundation work now, per explicit assignment of the API track to this session. `bootstrap.capabilities` is deliberately all-`false` until each dependent domain (recommendations, discovery, market, news, events, feedback, preferences, auth, analytics) has a real implementation behind it, so Flutter never has to guess from a 404 whether a capability exists yet.

## Completion Report (2026-08-21)

**Implemented:**
- New top-level `api/` package (separate from the internal `app/` domain package, per the Flutter/DB-model isolation rule):
  - `api/versioning.py` — `/api/v1` namespace, `API_VERSION`/`CONTRACT_VERSION` constants, deprecation-header helper.
  - `api/schemas/common.py` — generic `SuccessEnvelope[T]`/`PaginatedEnvelope[T]`/`ErrorEnvelope` Pydantic DTOs implementing the canonical envelope.
  - `api/errors.py` — `ApiError` base + `NotFoundError`/`ValidationError`/`UnauthenticatedError`/`ForbiddenError`/`RateLimitedError`/`InternalError`, each mapped to a stable `MRA_*` code.
  - `api/envelope.py` — `success()`/`paginated()`/`error_body()` builders that attach `requestId`/`timestamp` to every response.
  - `api/request_context.py` — per-request correlation id (contextvar), propagates an inbound `X-Request-Id` header or generates one.
  - `api/pagination.py` — `PageParams` (`page`, `pageSize`, default 20/max 100) and `parse_sort()` (comma-separated, `-` prefix = descending; rejects unknown fields with `MRA_VALIDATION_FAILED` instead of silently ignoring them). Not yet consumed by a real list endpoint — that lands with M1.135.
  - `api/rate_limit.py` — real, enforced, in-memory fixed-window limiter (120 req/60s per caller by default), explicitly documented as single-process (needs a shared store behind the same interface for multi-instance deployment).
  - `api/deps.py` — `get_db` session dependency; `get_optional_bearer_subject`/`require_bearer_subject` as the **integration point** for auth (extracts the raw bearer token only, does not verify it — real verification is M1.145's scope, called out explicitly in the docstring so it can't be mistaken for enforcement).
  - `api/middleware.py` — `RequestContextMiddleware`: assigns/echoes the request id and enforces the rate limit for every `/api/v1` request; converts a rate-limit rejection to the canonical envelope directly (documented why: `BaseHTTPMiddleware` exceptions raised before `call_next` sit outside FastAPI's `ExceptionMiddleware`, so relying on the global handler here would silently degrade to a bare 500).
  - `api/exception_handlers.py` — registers `ApiError`, `RequestValidationError` (→ `MRA_VALIDATION_FAILED` with per-field `fieldErrors`), `StarletteHTTPException` (status-code → `MRA_*` table, covers unmatched-route 404s), and a catch-all `Exception` → `MRA_INTERNAL` handler, so every response leaving the API is envelope-shaped.
  - `api/routers/health.py`, `api/routers/bootstrap.py` + `api/schemas/health.py`, `api/schemas/bootstrap.py` — the two foundation endpoints from "Initial Contracts"; the rest of that list belongs to M1.135/137/139/141.
  - `api/app.py::register_api()` — mounts the versioned router + middleware + exception handlers onto a `FastAPI` app without touching existing routes.
- `app/main.py` now calls `register_api(app)`; the legacy `/health` and `/api/models` endpoints are untouched (verified by test).
- `scripts/export_openapi.py` — generates `docs/api/openapi.json` (committed) from the live app; this is the Flutter typed-client source of truth per the EPIC's "Publish generated client/schema artifacts" scope item.
- `docs/api/VERSIONING.md` — the full written policy (envelope, pagination/sort/filter conventions, error codes, rate limits, caching guidance, auth integration point, compatibility rules).

**Explicitly deferred (named, not fabricated):**
- ETag/Last-Modified caching: helper not yet written — no endpoint has cacheable, slowly-changing data yet. First data-bearing endpoint (M1.135+) that needs it should add the concrete helper alongside its own use, per `docs/api/VERSIONING.md`.
- Real authentication/authorization enforcement: `api/deps.py` only extracts an opaque bearer-token string for rate-limit/observability keying; it is not verified. M1.145 owns real session validation.
- The 11 domain endpoints in "Initial Contracts" beyond `health`/`bootstrap` (recommendations, discovery, market, news, events, feedback, preferences): each is explicitly out of scope for this EPIC and owned by M1.135/137/139/141 respectively. `bootstrap.capabilities` reports all of them as `false` until each lands.

**Tests:** `tests/test_api_contract.py` (13 new tests, all passing) — envelope shape for success/error/list responses, request-id propagation and generation, unmatched-route 404 → `MRA_NOT_FOUND` envelope, Pydantic validation → `MRA_VALIDATION_FAILED` with field errors, `parse_sort` accept/reject behavior, rate limiter allow/reject/window-reset behavior, and a regression check that legacy `/health`/`/api/models` are unaffected.

**Validation run:**
```
DATABASE_URL="sqlite:///:memory:" python -m pytest -q
# 916 passed, 6 skipped in 98.64s — full existing suite plus the 13 new contract tests, no regressions.
```
(`DATABASE_URL` is only needed because `app.settings.Settings()` validates eagerly at import time and this worktree has no local `.env`; the app itself still reads `.env`/real env vars in any real deployment.)

**Repo layout note:** per explicit instruction this session, the BFF/API layer lives in a new top-level `api/` package, kept separate from both the internal `app/` domain package and the future Flutter client (which is a different session/EPIC's concern and not created here).
