# EPIC-M1.143 — Authentication & User Session

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Provide secure, versioned authentication and user-session handling for Flutter mobile/web clients without coupling UI to authentication-provider implementation.

## UI Scope
- Login/logout.
- Session-expiry handling.
- Secure error states.
- Remembered session where policy permits.
- Responsive authentication layouts.
- No secrets in logs or UI.

## API Contract
`POST /api/v1/auth/login`
`POST /api/v1/auth/logout`
`POST /api/v1/auth/refresh`
`GET /api/v1/auth/session`

Contract must define token/session lifecycle, expiry, refresh, invalid-session response, correlation ID and safe error codes.

## Acceptance Criteria
- Expired sessions recover or redirect cleanly.
- Authentication failures do not leak sensitive information.
- Web and mobile use the same API contract.
- API authorization is enforced independently of Flutter route visibility.
