# EPIC-163 — Authentication & User Session

**Status:** DONE
**Execution Status:** COMPLETED
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

## Completion Report (2026-08-22)

**Context:** this EPIC number was renumbered from `EPIC-146` (see
`docs/epics/EPIC-M3-ROADMAP-NOTE.md`). The older split track already
shipped almost all of this scope: `EPIC-148` (API, `DONE`, PR #196)
built a real, persisted, expiring/revocable/rotatable session lifecycle
(`app/auth_session.py`) behind an auth router, and `EPIC-149` (UI,
`DONE`) built the full Flutter sign-in/splash/session-expiry/logout flow
on top of it, including a global mid-session `MRA_SESSION_EXPIRED`
redirect hook and deep-link return-to-original-screen after login. This
session's job was to diff EPIC-163's exact scope against that existing,
merged code, not build a second, parallel auth system.

**Already satisfied by existing EPIC-148/EPIC-149 work -- verified, not
reimplemented:**
- Real, persisted, expiring, revocable, rotatable session token lifecycle
  -- `app/auth_session.py` (`create_session`, `refresh_session`,
  `revoke_session`, `get_session_status`), unchanged.
- Deterministic invalid-session responses and safe error codes --
  `api/errors.py`'s `MRA_UNAUTHENTICATED`/`MRA_VALIDATION_FAILED`, plus
  `api/deps.py::SessionExpiredApiError` (`MRA_SESSION_EXPIRED`, 401) --
  an expired-but-real token is always distinguished from a
  missing/unknown/revoked one, which is deliberately *not* further
  distinguished (an attacker can't use the error code to probe which
  tokens ever existed).
- Correlation ID on every response -- `api/request_context.py`
  (`X-Request-Id` propagation/generation) plus `meta.requestId` on every
  envelope (`api/envelope.py`), already wired through
  `UserContext.requestId`.
- `POST /api/v1/auth/logout` -- idempotent revoke, unchanged
  (`api/routers/auth.py`, `api/services/auth.py::logout`).
- Flutter UI: login/logout, loading/authenticated/expired/unauthenticated
  states, secure error states (no password field to leak, inline error
  text only), remembered session (`shared_preferences`, deliberately not
  secure-storage since the backend auth is an explicitly-documented
  self-asserted placeholder with no real credential to protect yet),
  responsive auth layout, deep-link return-to-original-screen, and a
  global mid-session-expiry redirect hook that fires regardless of which
  screen's request surfaced `MRA_SESSION_EXPIRED` -- all in
  `flutter_app/lib/core/auth/*`, `flutter_app/lib/features/auth/*`,
  `flutter_app/lib/app_shell/app_router.dart`. No secrets/tokens are ever
  logged or rendered (only a session token used solely as an
  `Authorization` header value, matching the existing convention).

**Genuine gap found and implemented this session:** EPIC-148 shipped one
combined `POST /api/v1/auth/session` endpoint that did double duty as
both "establish" and "refresh" (distinguished only by whether the request
happened to carry a currently-valid bearer token). EPIC-163's API Contract
names four distinct endpoints instead -- `POST /auth/login`,
`POST /auth/logout`, `POST /auth/refresh`, `GET /auth/session` -- and
neither `/auth/login`, `/auth/refresh`, nor a `GET /auth/session` existed
under those exact names/verbs. Implemented, reusing the existing
`app/auth_session.py` lifecycle rather than duplicating it:
- `api/schemas/auth.py` -- `SessionRequest` (optional `userId`) replaced
  with `LoginRequest` (required `userId`), matching login's "always needs
  a credential" semantics instead of session-establish's former
  double-duty optionality.
- `api/services/auth.py` -- `establish_or_refresh_session` split into two
  explicit functions: `login()` (always creates a brand-new session from
  the credential, never silently refreshes) and `refresh()` (always
  rotates the caller's currently-live session; raises the deterministic
  `MRA_SESSION_EXPIRED` for an expired token instead of silently
  re-issuing one, and the generic `MRA_UNAUTHENTICATED` for anything else
  invalid, per the same anti-probing rationale EPIC-148 already
  established for `GET /me`).
- `api/routers/auth.py` -- `POST /auth/login`, `POST /auth/refresh`,
  `GET /auth/session` (the last mirrors `GET /me`'s existing
  `require_active_session`-gated `UserContext` response, satisfying the
  contract's explicit `GET /api/v1/auth/session` read endpoint). The
  legacy combined `POST /auth/session` establish-or-refresh endpoint was
  removed rather than kept alongside the new split endpoints as a second,
  parallel mechanism doing the same thing under a different name; `GET
  /me`/`GET /me/permissions` (EPIC-148 scope, not part of EPIC-163's four) are
  unchanged and still present.
- `flutter_app/lib/core/auth/auth_repository.dart` updated to call the
  new `/auth/login`/`/auth/refresh` endpoints (previously both mapped to
  the old combined `/auth/session`), plus a new `fetchSession()` method
  wrapping `GET /auth/session` for API-contract completeness (not yet
  wired into a call site -- an honest, documented gap, matching this same
  repository's pre-existing `refresh()` pattern from EPIC-149's own
  completion report).
- `docs/api/openapi.json` regenerated (`python scripts/export_openapi.py`).

**Tests (TDD):**
- `tests/test_api_auth.py` rewritten for the new contract: login requires/
  rejects blank `userId`, login returns a real token, `GET /me` and the
  new `GET /auth/session` both require auth and both return the same
  `UserContext` shape for a valid session and both reject an unknown
  token, permissions/logout/idempotent-logout unchanged, `POST
  /auth/refresh` requires auth, rejects an unknown token, rejects a
  revoked token, rotates a valid token and invalidates the old one, and
  returns the deterministic `MRA_SESSION_EXPIRED` for an expired token
  (both from `refresh` directly and from `GET /me`/`GET /auth/session`).
- `tests/test_openapi_contract_freshness.py`'s `FLUTTER_DEPENDENT_PATHS`
  updated to include `/api/v1/auth/login` and `/api/v1/auth/refresh`.
- `flutter_app/test/core/auth/auth_repository_test.dart` updated to
  assert `signIn` posts to `/api/v1/auth/login` (was `/api/v1/auth/session`).
- `flutter_app/test/e2e/end_to_end_journey_test.dart`'s scripted mock
  server updated (`POST /api/v1/auth/session` -> `POST /api/v1/auth/login`)
  in all four scenarios (happy path, session-expired, rate-limited,
  network-failure) -- unchanged assertions otherwise, since the sign-in
  flow's UI behavior didn't change, only which endpoint it calls.
- `flutter_app/tool/mock_api_server.dart` (manual/dev-server tooling, not
  part of the automated test suite) updated to serve
  `/auth/login`/`/auth/refresh`/`GET /auth/session`.

**Validation run:**
```
python -m pytest tests/test_api_auth.py tests/test_openapi_contract_freshness.py -q
# 24 passed

python -m pytest -q
# 1454 passed, 9 skipped -- full existing suite, no regressions

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# Formatted 138 files (0 changed)

cd flutter_app && flutter test
# All tests passed! (177 tests)
```

**Deliberately not done (rationale):**
- No proactive refresh-before-expiry background timer was added --
  unchanged, honestly-documented gap from EPIC-149's own completion report
  (sessions are re-validated at cold start and reactively on
  `MRA_SESSION_EXPIRED`).
- `AuthController.restore()` still trusts the locally-cached session's
  expiry timestamp rather than calling the new `GET /auth/session` to
  validate against the server on every cold start. Wiring that in would
  force a network round-trip before the app can ever show a "remembered
  session" and would break offline cold-start restoration entirely --
  directly against this EPIC's own "Remembered session where policy
  permits" UI scope item. The new endpoint exists for contract
  completeness and for callers (future EPICs, external tooling) that
  need a read-only session check without that offline tradeoff.
- A revoked-but-not-yet-locally-expired session does not proactively
  redirect to sign-in until the next real API call returns
  `MRA_UNAUTHENTICATED` (only `MRA_SESSION_EXPIRED` triggers the existing
  global redirect hook in `ApiClient`/`AuthController`). This is a
  pre-existing EPIC-149 behavior, not introduced or worsened by this
  session's changes, and widening the hook to also treat
  `MRA_UNAUTHENTICATED` as a redirect trigger is a separate, larger
  behavior change (it currently also covers cases like a stale/malformed
  token) left for a future EPIC rather than folded in here.
- Real credential verification (password/OAuth/SSO) remains
  `SelfAssertedCredentialVerifier`, an explicit EPIC-148 placeholder until
  this platform has an identity provider -- unchanged, out of scope for
  a session-lifecycle/contract EPIC.

**Conclusion:** EPIC-163's scope was almost entirely already satisfied
by the existing, merged EPIC-148/EPIC-149 work. The one concrete gap -- the
API contract's exact endpoint verbs (`login`/`refresh`/`GET session`
instead of one combined `POST session`) -- has been implemented, tested
and verified above, with the legacy combined endpoint retired rather than
left running in parallel. Marking this EPIC `DONE`.
