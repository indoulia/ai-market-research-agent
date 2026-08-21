# EPIC-M2.1 — MRA API Platform & Contract Foundation [API]

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0
**Parallel Track:** API

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
