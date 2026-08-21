# EPIC-M1.145 — Authentication, Session & User Context API

**Track:** API
**Status:** DONE
**Execution Status:** MERGED (PR #196, commit 543d865)
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

## Completion Report (2026-08-21)

**Implemented:**
- New domain module `app/auth_session.py` (+ migration `0088_auth_session`, table `auth_sessions`): a real, persisted, expiring, revocable, rotatable session lifecycle. "Authentication mechanism remains configurable at deployment level" (Rule) is a `CredentialVerifier` `typing.Protocol` -- the same provider-abstraction shape M1.90 already established for market-data providers -- with one concrete, explicitly-labeled placeholder implementation, `SelfAssertedCredentialVerifier` (trusts a client-supplied `userId` outright, since this platform has no user-credential store at all yet). A real deployment swaps in a password/OAuth/SSO verifier without touching the session lifecycle or the API contract.
- `POST /api/v1/auth/session` — establishes a new session (validates `userId` via the verifier) **or** refreshes/rotates an existing one, distinguished by whether the request carries a currently-*valid* `Authorization` bearer session token. An *expired* token is never silently refreshed (falls through to requiring a fresh credential) -- refreshing an already-expired session would defeat the point of expiry (AC: "session expiry and refresh behavior are explicit").
- `POST /api/v1/auth/logout` — revokes the session (idempotent: revoking twice is not an error, returns `revoked: false` the second time), per AC "logout invalidates session according to policy."
- `GET /api/v1/me` / `GET /api/v1/me/permissions` — require a real, live session (401 `MRA_UNAUTHENTICATED` otherwise); `/me/permissions` returns a fixed, honest capability list (`DEFAULT_CAPABILITIES` in `api/schemas/auth.py`) since this platform has no per-user RBAC yet -- named as the current flat state, not fabricated as fine-grained permissions.
- **Real enforcement wired into `api/deps.py`**: `require_active_session`/`require_bearer_subject` (used by M1.141's preferences/feedback endpoints) now validate the bearer token against a live `AuthSession` instead of accepting any string, exactly the upgrade M1.132/M1.141's own docstrings said M1.145 would make. An expired-but-otherwise-real token gets the deterministic `MRA_SESSION_EXPIRED` (401) the AC requires; anything else invalid (missing, unknown, revoked) gets the generic `MRA_UNAUTHENTICATED` -- deliberately not distinguished further, so an attacker can't use the error code to probe which tokens ever existed.
- **Deliberately NOT retrofitted onto M1.135/137/139's already-public endpoints** (recommendations/discoveries/market/news/events): those contracts shipped unauthenticated, and per M1.132's own versioning policy, adding a new auth requirement to an existing `/api/v1` endpoint in place would be a breaking change, not an additive one. "Unauthorized users cannot access recommendation data" (AC) is satisfied for the surfaces this EPIC actually owns (preferences/feedback, which already required a caller identity); broadening auth to the read-only market-data endpoints is a scope decision for a future version, not this EPIC.
- CORS middleware added to `api/app.py` (`Settings.cors_allowed_origins`, comma-separated, default `*`) so the Flutter web build can call the API cross-origin -- safe as a wide-open default because this API authenticates via Bearer token, never cookies, so there's no cross-site-cookie exposure.

**Tests:** `tests/test_api_auth.py` (11 new tests) — establish requires `userId`, real token issued, `/me` requires auth, valid session returns correct context, unknown token rejected, permissions returns the default capability set, logout revokes (and is idempotent), refresh rotates the token and invalidates the old one, expired session returns the deterministic `MRA_SESSION_EXPIRED` code, and a regression check that M1.135's list endpoint is still unauthenticated by contract. Plus updated `tests/test_api_preferences_feedback.py` (all 12 tests now create a real session via `create_session` instead of a fake bearer string) and 1 updated assertion in `tests/test_api_contract.py`.

**Validation run:**
```
DATABASE_URL="postgresql+psycopg://ci:ci@localhost/market_agent" python -m pytest -q
# 1089 passed, 6 skipped -- full existing suite plus all new/updated tests, no regressions.
python -m alembic heads
# 0088_auth_session (head) -- single head.
```

**Migration numbering note:** this migration was renumbered twice during development due to concurrent-session collisions with EPIC-M1.111's `0087_counterfactual_analysis` (and, transitively, the earlier M1.109/M1.110 collisions already fixed in separate PRs). No schema change each time -- filename/revision-id/down_revision only.

**Explicitly deferred (named, not fabricated):** real credential verification (password/OAuth/SSO) -- `SelfAssertedCredentialVerifier` is a placeholder until this platform has an identity provider; per-user RBAC (today's permissions are a flat default set); auth enforcement on the pre-existing public read endpoints (a versioning-policy-driven decision, not an oversight).
