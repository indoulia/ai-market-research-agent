# EPIC-MARKSY-0001 — Upstox OAuth & Market Data Integration

**Status:** DONE (core OAuth flow, S1-S4/S8/S9/S10) — real-provider validation blocked pending Upstox account credentials (see Completion Report)
**Execution Status:** COMPLETED (core), CONTROLLED REAL-PROVIDER VALIDATION PENDING
**Source:** GitHub issue #302 — this doc mirrors that issue (the primary spec, per `project_marksy_rebrand_and_upstox_oauth_20260822` memory: new Marksy-namespace epics are specified as GitHub Issues, not authored fresh as `docs/epics/*.md`) plus this repo's completion-report convention.
**Track:** Backend/API
**Priority:** HIGH
**Product:** Marksy — Market Intelligence
**Merged via:** PR #306, branch `feat/epic-marksy-0001-upstox`

## Objective

Establish a secure, testable Upstox integration for Marksy, initially for authentication and market-data access, integrated with the existing provider abstraction and normalized market-data layer rather than coupling prediction/business logic directly to Upstox. **Trading/order execution is explicitly out of scope.**

## Scope (from issue #302)

In scope: OAuth authorization-code flow, client id/secret config, verified redirect/callback endpoint, OAuth state/CSRF protection, authorization-code exchange, access-token lifecycle handling, secure token persistence, isolated Upstox API client abstraction, instrument/master-data integration, historical market-data retrieval/normalization/idempotent persistence, retry/timeout/rate-limit handling, auth/data-provider health diagnostics, local Docker Compose docs, integration tests.

Out of scope: automated trading, order placement/modification/cancellation, GTT/order automation, trading strategy execution, portfolio management through Upstox, model-driven buy/sell execution, prediction/scoring algorithm changes.

## Completion Report (2026-08-22)

### S1 — Repository OAuth due diligence (evidence, not guessed)

- Backend runs as a single FastAPI process; `Dockerfile:21` — `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`; `docker-compose.yml`'s `api` service maps `ports: ["8000:8000"]`. **Real local port: 8000.**
- Every contract route is mounted under `API_PREFIX` (`api/versioning.py:16`, currently `/api/v1`).
- No OAuth callback route existed anywhere in the repository before this EPIC (verified via a repo-wide grep for `callback`/`oauth`/`redirect_uri` across `api/` and `app/` — zero matches outside this EPIC's own new files).
- Existing `/api/v1/auth/*` (`api/routers/auth.py`, EPIC-148) is Marksy's own end-user session login (self-asserted credential + server session, EPIC-148/`app/auth_session.py`) — unrelated to this broker-level OAuth connection; reused only for gating `authorize`/`status` behind an authenticated caller.
- **Verified real callback: `GET http://localhost:8000/api/v1/integrations/upstox/callback`** — served directly by the already-exposed `api` process/port, no new Docker Compose/Kubernetes port needed. Documented in `.env.example` and `app/upstox_oauth.py`'s module docstring.
- Config pattern: `pydantic-settings` `Settings` (`app/settings.py`), `.env`/`.env.example` convention, secrets never committed (`.env` gitignored). `UPSTOX_CLIENT_ID`/`UPSTOX_CLIENT_SECRET`/`UPSTOX_REDIRECT_URI`/`UPSTOX_ENVIRONMENT` added following that exact pattern — no new configuration mechanism introduced.

### S2 — OAuth authorization flow

`app/upstox_oauth.py`: `build_authorization_url` (authorization URL generation), `create_oauth_state`/`consume_oauth_state` (CSRF `state`, one-time-use, 10-minute TTL, backed by the new `upstox_oauth_states` table), `exchange_authorization_code` (POST to Upstox's v2 token endpoint). `api/routers/integrations_upstox.py`'s `GET /integrations/upstox/callback` correlates login initiation and callback purely via `state` (the browser redirect carries no Marksy bearer token) and never logs `code`/`client_secret`/the token response.

### S3 — Access token lifecycle

New append-only `upstox_oauth_tokens` table (migration `0108_upstox_oauth`) — never revoked-in-place, matching this codebase's `AuthSession` convention. `resolve_access_token` (`app/upstox_oauth.py`) is the single source of truth for "what token should a market-data call use right now."

**Explicit, flagged assumption — not repository evidence:** Upstox's OAuth v2 token endpoint has no documented `refresh_token` grant; access tokens are documented to expire at a fixed daily cutover (3:30 AM IST) regardless of issue time. `_next_daily_cutover` models expiry that way, but prefers a real `expires_in` from the token response if Upstox ever returns one. **This needs confirming against a real Upstox account** — flagged as the epic's own allowed "external-account activation blocker," not silently assumed correct.

### S4 — Upstox API client abstraction

Reused, not rebuilt: `app.market_data.UpstoxClient` (`app/market_data/upstox.py`) already existed from an earlier EPIC with `capability="MARKET_DATA"`/`source="upstox-v3"` contract fields, HTTP client, timeouts, and provider error mapping (401 → `UpstoxError`). This EPIC's job here was exclusively supplying it a *real, OAuth-obtained* token instead of a manually pasted one.

### S5-S7 — Instrument universe / historical market data / idempotent persistence

**Already implemented by an earlier EPIC, verified working, no changes needed:** `UpstoxClient.fetch_nse_instruments`/`fetch_daily_candles` (`app/market_data/upstox.py`) and `app.market_data.ingest.upsert_nse_universe`/`ingest_daily_history` (idempotent `ON CONFLICT DO NOTHING` on `(stock_id, timestamp)`, provider provenance via `source`, per-stock failure isolation via `record_fetch_attempt`). This EPIC only changed *where the access token comes from* (see S8).

### S8 — M1 pipeline integration

`scripts/ingest_market_history.py` and `scripts/ingest_upstox_history.py` now call `app.upstox_oauth.resolve_access_token(session, at=...)` instead of reading `settings.upstox_access_token` directly — a valid OAuth-obtained token takes priority, the static env var remains a supported fallback (e.g. CI, or before OAuth is configured in a given environment). The downstream `ingest_daily_history`/prediction pipeline is unchanged either way — it already only depended on the `DailyHistoryProvider` protocol, not on how the token was obtained.

### S9 — Observability & diagnostics

`GET /api/v1/integrations/upstox/status` (session-gated) returns `connected`/`isExpired`/`obtainedAt`/`expiresAt`/`environment` — derived purely from `UpstoxOAuthToken` timestamps (`api/services/integrations_upstox.py::get_status`), never `access_token` itself.

### S10 — Security & integration tests

`tests/test_upstox_oauth.py` (17 cases: config validation, state CSRF single-use/expiry, token-exchange success/HTTP-error/malformed-response, daily-cutover vs. real `expires_in` expiry, OAuth-token-priority-over-static-fallback resolution) and `tests/test_api_integrations_upstox.py` (8 contract cases: session gating, not-configured error, callback missing/unknown state, provider `error=` passthrough, full authorize→callback→status flow with a mocked Upstox token response). No real Upstox credentials are used in any test — the token exchange is mocked via `monkeypatch.setattr(httpx, "post", ...)`, following this repo's existing `tests/test_upstox_client.py` pattern.

**Verification:** full suite `pytest -q` → 1498 passed, 9 skipped, zero regressions. `alembic heads` → single head (`0108_upstox_oauth`), no branch conflict. `docs/api/openapi.json` regenerated (`PYTHONPATH=. python scripts/export_openapi.py`) and the contract-freshness test passes.

### Outstanding — controlled real-provider validation

Not completed: a live authorization-code exchange against a real Upstox developer app. **Blocker:** no Upstox `UPSTOX_CLIENT_ID`/`UPSTOX_CLIENT_SECRET` credentials were available to this session (per the issue's own "controlled real Upstox validation completed when account/API activation is available" allowance). When credentials are available: set them plus `UPSTOX_REDIRECT_URI=http://localhost:8000/api/v1/integrations/upstox/callback` in `.env`, register that exact redirect URI in the Upstox developer app, complete one real login via `GET /api/v1/integrations/upstox/authorize`, and confirm the real token response's actual field shape (particularly whether it includes `expires_in`) against the assumption recorded in S3 above.
