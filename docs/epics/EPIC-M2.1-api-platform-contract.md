# EPIC-M2.1 — MRA API Platform & Contract Foundation [API]

**Status:** SUPERSEDED BY M3.1
**Execution Status:** NOT_EXECUTED
**Priority:** P0
**Parallel Track:** API

> **2026-08-22 — superseded, not implemented (explicit user decision).** `EPIC-M3.1-mra-application-platform-foundation.md`
> recreates this same API contract + Flutter design system + app shell foundation as part of the combined M3.1-M3.15
> vertical-slice roadmap (see `EPIC-M3-ROADMAP-NOTE.md`). Implementing this EPIC would duplicate that foundation work.
> M3 is the authoritative application/UI roadmap going forward. This file is preserved for history, not deleted.

## Objective
Establish the stable API foundation consumed by Flutter Web, Android and iOS without coupling UI code to internal MRA services or database schemas.

## Scope
- REST/JSON API baseline with versioned `/api/v1` namespace.
- OpenAPI as the contract source of truth.
- Consistent envelope for success, errors, pagination and metadata.
- Cursor-based pagination for historical/large collections.
- ISO-8601 timestamps and explicit timezone semantics.
- Stable IDs and immutable prediction/revision IDs.
- Request correlation ID and API version headers.
- Idempotency keys for mutation endpoints.
- Authentication/authorization contract.
- Cache/freshness metadata where relevant.
- Contract validation and generated Dart client compatibility checks.

## Contract Rules
### Success
`200/201/202` with typed JSON payloads.

### Error
```json
{
  "error": {
    "code": "PREDICTION_NOT_FOUND",
    "message": "Prediction was not found",
    "details": {},
    "correlationId": "..."
  }
}
```

### Pagination
```json
{
  "items": [],
  "nextCursor": "...",
  "hasMore": true
}
```

### Common resource metadata
`id`, `createdAt`, `updatedAt`, `asOf`, `sourceVersion` where applicable.

## Acceptance Criteria
- OpenAPI document covers every released endpoint.
- Breaking contract changes require explicit API versioning.
- Flutter client can be generated/validated from the contract.
- Error, pagination, timestamp and ID conventions are consistent.
- Contract tests run independently of UI tests.

## Dependencies
M1.90, M1.93, M1.115.
