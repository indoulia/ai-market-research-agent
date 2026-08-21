# EPIC-M1.145 — Authentication, Session & User Context API

**Track:** API
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Provide a secure, platform-neutral authentication/session boundary for Flutter mobile and web without leaking identity concerns into recommendation APIs.

## Contract
`POST /api/v1/auth/session` — establish/refresh application session.
`POST /api/v1/auth/logout` — terminate session.
`GET /api/v1/me` — current user/application context.
`GET /api/v1/me/permissions` — allowed capabilities if authorization is required.

## Rules
- Authentication mechanism remains configurable at deployment level.
- API returns no secrets or provider credentials to Flutter.
- Recommendation APIs enforce authorization server-side.
- Session expiry and refresh behavior are explicit.
- Request IDs and security audit IDs are available for support.

## Acceptance Criteria
- Mobile and web use the same API contract.
- Expired sessions produce a deterministic error code.
- Logout invalidates session according to policy.
- Unauthorized users cannot access recommendation data.
- No domain API contains platform-specific authentication logic.

## Parallelization
API security team.

## Dependencies
M1.132.
