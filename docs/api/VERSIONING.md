# API Contract & Versioning Policy (EPIC-M1.132)

This is the policy referenced by `api/versioning.py`. It governs every
`/api/v1` endpoint and every future `api/*` package.

## Namespace

All contracts live under `/api/{version}` (currently `/api/v1`). Endpoints
outside this namespace (`/health`, `/api/models`) are legacy/internal and
are not part of the Flutter-facing contract.

## Source of truth

`docs/api/openapi.json` is generated from the live FastAPI app via
`python scripts/export_openapi.py` and committed. It is the artifact the
Flutter team generates a typed client from — never hand-author a second
copy of the contract.

## Envelope

Every response is one of:

- Success: `{ "data": <T>, "meta": { "requestId", "timestamp" } }`
  (list endpoints add `page`, `pageSize`, `totalItems`, `totalPages` to `meta`)
- Error: `{ "error": { "code": "MRA_*", "message", "details", "retryable" }, "meta": { "requestId", "timestamp" } }`

`requestId` echoes (or generates) the `X-Request-Id` request header.

## Pagination, sorting, filtering

Two pagination styles are supported, chosen per endpoint by what the data
actually needs — never mixed on the same endpoint:

- **Page-based** (`api/pagination.py::PageParams`): `page` (1-indexed,
  default 1), `pageSize` (default 20, max 100). `meta` carries `page`,
  `pageSize`, `totalItems`, `totalPages`. Use for bounded, rarely-changing
  collections where "jump to page N" and a total count are useful.
- **Cursor-based** (`api/envelope.py::cursor_paginated`, first used by
  M1.135's `/recommendations`): `pageSize` plus an opaque `cursor` from
  the previous page's `meta.nextCursor`. `meta` carries `pageSize` and
  `nextCursor` (`null` on the last page) — no `page`/`totalItems`, since
  those aren't cheap or stable for a live-ranked feed. Use for a
  server-ranked/live feed where new rows can appear between requests and
  results must not shift or duplicate across pages (AC: "pagination is
  stable during a query session").

Sorting: `sort=<field>` (single field per M1.135; a future multi-field
list endpoint may extend this to comma-separated, `-` prefix for
descending — not yet needed) plus a separate `direction=asc|desc` for
cursor-paginated endpoints. Endpoints reject unknown sort fields with
`MRA_VALIDATION_FAILED` rather than ignoring them.

Filters are individual query params, documented per endpoint. Unknown
filter params are rejected the same way.

## Errors

`MRA_*` codes are the stable contract; HTTP status is secondary. Standard
codes: `MRA_NOT_FOUND` (404), `MRA_VALIDATION_FAILED` (422),
`MRA_UNAUTHENTICATED` (401), `MRA_FORBIDDEN` (403), `MRA_RATE_LIMITED`
(429, with `Retry-After` header), `MRA_INTERNAL` (500). New codes are
added in `api/errors.py`, never invented ad hoc in a router.

## Rate limits

A fixed-window limiter (120 requests/60s per caller by default) is
enforced on every `/api/v1` request. Exceeding it returns
`MRA_RATE_LIMITED` with `retryable: true` and a `Retry-After` header. The
current implementation is single-process/in-memory
(`api/rate_limit.py::RateLimiter`) — a multi-instance deployment needs a
shared backing store behind the same interface before this becomes the
production limiter.

## Caching

Endpoints that return slowly-changing data may set `ETag`/`Last-Modified`
and honor `If-None-Match`/`If-Modified-Since` with `304 Not Modified`.
Not yet applied to any endpoint as of M1.132; the first data-bearing
endpoint to need it (M1.135+) should establish the concrete helper.

## Authentication/authorization

`api/deps.py::get_optional_bearer_subject` extracts a raw bearer token as
an opaque identity for rate-limiting/observability only — it does not
verify anything. Real session/token verification is EPIC-M1.145's scope;
until it lands, no endpoint may claim to enforce authentication.

## Compatibility rules

- Additive, backward-compatible changes ship in-place in the current version.
- Breaking changes (removed/renamed fields, changed types, removed
  endpoints, stricter validation) require a new version namespace.
- A contract scheduled for removal is marked with `Deprecation`/`Sunset`
  response headers (see `api/versioning.py::deprecation_headers`) before
  removal, never removed silently.

## Contract tests

`tests/test_api_contract.py` asserts the envelope/error/pagination shapes
independently of any Flutter code and must stay green for every future
`api/*` change.
