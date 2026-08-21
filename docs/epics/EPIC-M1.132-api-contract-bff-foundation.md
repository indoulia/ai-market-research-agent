# EPIC-M1.132 — API Contract & BFF Foundation

**Track:** API
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
