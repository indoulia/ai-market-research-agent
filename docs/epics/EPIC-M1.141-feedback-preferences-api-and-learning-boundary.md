# EPIC-M1.141 — Feedback, Preferences & Learning Boundary API

**Track:** API
**Status:** DONE
**Execution Status:** MERGED (PR #184, commit ddcb525)
**Priority:** P0

## Objective
Expose user preferences and manual feedback without allowing individual user behavior to corrupt global prediction truth. Feedback becomes an auditable learning signal, not an immediate model mutation.

## Contracts
`GET /api/v1/preferences`

Response: `defaultHorizon,markets,sectors,industries,marketCapBuckets,watchlist,notificationPreferences,displayPreferences`.

`PUT /api/v1/preferences`

Request uses the same fields with server-side validation and versioning.

`POST /api/v1/recommendations/{id}/feedback`

Request: `{ "type": "useful|not_useful|target_realistic|target_too_high|target_too_low|reason", "comment": "optional", "predictionVersion": "..." }`

Response: `{ "feedbackId": "...", "accepted": true, "recordedAt": "...", "learningImpact": "queued|informational" }`

## Rules
- Feedback is immutable after submission; corrections create a new record.
- Feedback must reference a prediction version.
- User preference changes affect selection/presentation policy, not historical prediction truth.
- Feedback never directly updates a production model.
- Learning impact is queued for the controlled learning pipeline.

## Acceptance Criteria
- API validates allowed feedback types.
- Duplicate submissions are idempotent where client request ID is reused.
- Feedback is auditable and versioned.
- User-specific preferences are isolated from global model training unless explicitly aggregated through governed learning.
- Contract tests cover invalid, stale-version and duplicate feedback.

## Parallelization
API implementation. UI M1.142 consumes this exact contract.

## Dependencies
M1.132, M1.88, M1.130, M1.110.

**Dependency note (2026-08-21):** M1.132/M1.88 are `DONE`. M1.130
(prediction abstention quality) and M1.110 (prediction lifecycle/capacity
control) are still `APPROVED`/not implemented, but neither gates this
EPIC's actual scope: feedback/preferences are a user-facing surface over
already-existing M1.46/M1.52/M1.60 domain modules, not consumers of
abstention or capacity signals.

## Completion Report (2026-08-21)

**Implemented:**
- `GET`/`PUT /api/v1/preferences` — composes M1.46's `app.user_preferences`
  (horizon/risk/min-confidence/sectors/market-cap-buckets, reused
  unchanged), M1.60's `app.recommendation_alerts` (`muted_alert_types` for
  `notificationPreferences`), and a new domain module,
  `app.user_api_preference_profile` (+ migration `0083_api_pref_profile`,
  table `user_api_preference_profiles`), for the fields neither existing
  module owns: `markets`/`industries`/`watchlist`/`displayPreferences`.
  Mirrors `UserPreference`'s exact append-only, immutable-row-per-change
  pattern. `defaultHorizon` (a single day count) is a deliberate
  simplification of M1.46's richer `horizon_band` concept: every `PUT`
  sets `horizon_band=CUSTOM, custom_horizon_days=defaultHorizon`, so the
  value round-trips exactly and is still validated against M1.9's real
  `VALID_HORIZON_DAYS` vocabulary (`MRA_VALIDATION_FAILED` for e.g. `2`).
  Preferences require a caller identity (`api/deps.py::require_bearer_
  subject` — the M1.132-established, not-yet-verified bearer-token
  extraction point; real verification is M1.145) since they are
  inherently per-user state, isolated per user (verified by test).
- `POST /api/v1/recommendations/{id}/feedback` — composes M1.52's
  `app.recommendation_feedback.submit_feedback` (deliberately
  non-idempotent by design — every call inserts a new row) with a new
  API-layer idempotency mechanism: an `Idempotency-Key` header maps
  (via the new `feedback_idempotency_keys` table, same migration) to the
  feedback row it originally created, so a client retry with the same
  key returns the identical `feedbackId` instead of a duplicate record
  (AC: "duplicate submissions are idempotent where client request ID is
  reused" — verified by test that a repeat call with the same key
  produces exactly one `RecommendationFeedback` row, while a repeat
  without a key correctly produces two, preserving M1.52's own "multiple
  feedback events are retained" guarantee for the no-key case).
  `predictionVersion` is validated against the recommendation's *active*
  version (via M1.55's `get_active_version`, matching M1.137's
  detail/history semantics) — a stale/mismatched version is rejected
  with a new `409 MRA_STALE_PREDICTION_VERSION` (added to
  `api/errors.py::ConflictError`), not a generic validation error, since
  it's a precondition-failed rather than a malformed-request case.
  The API's single `type` enum (`useful`/`not_useful`/`target_realistic`/
  `target_too_high`/`target_too_low`/`reason`) maps onto the domain's
  richer `(category, reason_code)` pair — a translation this layer owns
  explicitly (documented in `api/services/feedback.py`), since no 1:1
  domain vocabulary exists for it. `learningImpact` is `"queued"` for the
  three target-related types, `"informational"` otherwise — a labeling
  policy this API defines, not a claim that any learning pipeline is
  actually wired to consume it (Rule: "feedback never directly updates a
  production model" — nothing here does).
- `bootstrap.capabilities.feedback`/`preferences` flipped to `true`.

**Tests:** `tests/test_api_preferences_feedback.py` (12 new tests) —
auth required for preferences, real defaults for a never-set user,
full PUT round-trip across all fields, invalid-horizon rejection,
per-user isolation, feedback accepted with correct `learningImpact`,
unknown-type rejection, stale-prediction-version 409, not-found
recommendation, duplicate-idempotency-key producing one record, and
no-key repeats producing two (per M1.52's own guarantee). Plus 1 updated
assertion in `tests/test_api_contract.py` (bootstrap capabilities).

**Validation run:**
```
DATABASE_URL="postgresql+psycopg://ci:ci@localhost/market_agent" python -m pytest -q
# 1042 passed, 6 skipped -- full existing suite plus the 12 new tests, no regressions.
python -m alembic heads
# 0083_api_pref_profile (head) -- single head, chain resolves cleanly from 0001_initial.
```
Migration upgrade/downgrade/upgrade could not be validated against real
Postgres in this environment (none available) — per this repo's own
documented convention, that check only ever ran against a real Postgres
instance, not SQLite (several pre-existing, unrelated migrations use
Postgres-only `ALTER COLUMN ... DROP DEFAULT` syntax that SQLite's
`ALTER TABLE` doesn't support at all, so a full chain replay fails on
SQLite regardless of this EPIC's own migration). Named here rather than
fabricated as "tested."

**Explicitly deferred (named, not fabricated):** real authentication
(the bearer token is a self-asserted, unverified identity until M1.145);
any actual learning-pipeline consumption of `learningImpact="queued"`
feedback (M1.130/M1.110 don't exist yet, and wiring feedback into
model training is explicitly out of this EPIC's scope by its own Rules).
