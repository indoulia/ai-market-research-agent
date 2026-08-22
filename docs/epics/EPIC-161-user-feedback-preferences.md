# EPIC-161 — User Feedback & Preferences

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Allow users to control recommendation preferences and provide structured feedback that becomes an auditable learning signal without directly changing production models.

## UI Scope
- Default horizon preference with short-term default (1–7 trading days).
- Market/sector/size preferences.
- Recommendation display preferences.
- Simple useful/not-useful feedback.
- Structured feedback reasons.
- Optional free-text note.
- Feedback history.
- Clear statement that feedback enters controlled learning, not immediate model mutation.

## API Contract
`GET /api/v1/preferences`
`PUT /api/v1/preferences`
`POST /api/v1/recommendations/{recommendationId}/feedback`
`GET /api/v1/feedback/history`

Preference model:
`defaultHorizon`, `markets[]`, `sectors[]`, `industries[]`, `marketCaps[]`, `minTrust`, `notificationPreferences`.

Feedback model:
`feedbackId`, `recommendationId`, `predictionVersionId`, `rating`, `reasonCode`, `note`, `createdAt`.

## Acceptance Criteria
- User preferences affect selection/presentation, not global prediction truth.
- Feedback is immutable after submission.
- Duplicate accidental submissions are handled idempotently.
- Feedback always references the exact prediction version.
- Unsafe model controls are not exposed to ordinary users.

## Completion Report (2026-08-22)

**Context:** see `docs/epics/EPIC-M3-ROADMAP-NOTE.md` -- like every other
M3.x EPIC, this restates product surface already built by the older
split-track chain. EPIC-144 (API) and EPIC-145 (UI) already
implemented almost all of this EPIC's scope; this session's job was to
find and close the genuine gap, not rebuild a second, parallel
screen/API.

**Already satisfied by existing, merged work -- verified, not
reimplemented:**
- `GET`/`PUT /api/v1/preferences` (`api/routers/preferences.py`,
  `api/services/preferences.py`, `api/schemas/preferences.py`) --
  `defaultHorizon` (1-7 trading days, validated against
  `VALID_HORIZON_DAYS`), `markets`/`sectors`/`industries`/
  `marketCapBuckets`/`watchlist`, `notificationPreferences`
  (`mutedAlertTypes`), `displayPreferences` (free-form), plus
  `riskPreference`/`minConfidenceThreshold`. Field names
  (`marketCapBuckets` vs. this doc's illustrative `marketCaps`,
  `minConfidenceThreshold` vs. `minTrust`) differ cosmetically from this
  EPIC's own "Preference model" list -- kept as-is rather than renamed,
  since EPIC-144's names are the real, already-shipped, tested contract
  the Flutter app (`flutter_app/lib/features/preferences/`) already
  consumes; renaming for cosmetic parity would be a breaking,
  purely-nominal change with no functional benefit.
- `POST /api/v1/recommendations/{recommendationId}/feedback`
  (`api/routers/recommendation_detail.py`, `api/services/feedback.py`)
  -- structured `type` (`useful`/`not_useful`/`target_realistic`/
  `target_too_high`/`target_too_low`/`reason`), optional `comment`,
  mandatory `predictionVersion` checked against the recommendation's
  *active* version (409 `MRA_STALE_PREDICTION_VERSION` on mismatch),
  `Idempotency-Key`-based dedup for accidental duplicate submissions,
  `learningImpact` always `queued`/`informational` -- feedback is
  appended via EPIC-047's `submit_feedback` (immutable after creation,
  enforced by a SQLAlchemy `before_update` listener that raises on any
  attempted mutation) and never touches a production model.
- Flutter: `QuickPreferencesScreen` (default horizon, market-cap scope,
  watchlist, sectors, notification mute chips) and
  `RecommendationFeedbackSection` (one-tap useful/not-useful, structured
  reason chips, optional comment, explicit "queued for
  learning/analysis... will not change ... immediately" disclosure
  before *and* after submission, no modal dialog) -- both already wired
  into the app (`PreferencesSettingsScreen`'s "Preferences" tab,
  `RecommendationDetailScreen`).
- All 8 of this EPIC's ACs bullet-for-bullet: preferences-vs-prediction-
  truth isolation, feedback immutability, idempotent duplicate handling,
  exact-version referencing, and no model-mutation controls anywhere in
  either the API or UI surface -- all already true of the EPIC-144/EPIC-145
  implementation, verified by that EPIC's own test suite
  (`tests/test_api_preferences_feedback.py`, unchanged assertions) plus
  this session's new tests below.

**Genuine gap implemented this session:** `GET /api/v1/feedback/history`
did not exist anywhere in the codebase (confirmed by search -- no
router, service, schema, or UI screen referenced it) and "Feedback
history" is explicitly named in this EPIC's own UI Scope list.
- `api/schemas/feedback.py::FeedbackHistoryItem` -- `feedbackId`,
  `recommendationId`, `predictionVersionId`, `type`, `reasonCode`,
  `note`, `learningImpact`, `createdAt`. One deliberate field
  substitution from this doc's illustrative "Feedback model": `rating`
  is realized as `type`, reusing EPIC-144's exact submission vocabulary,
  since no numeric/boolean rating concept exists anywhere in this
  codebase -- inventing one for cosmetic parity would misrepresent what
  was actually recorded. `predictionVersionId` holds the same
  `model_version` string `predictionVersion` already uses (no separate
  surrogate id exists).
- `api/services/feedback.py::get_feedback_history` -- lists the caller's
  own `RecommendationFeedback` rows (EPIC-047's `get_feedback_for_user`),
  newest first, offset-cursor paginated (same convention as
  `/recommendations/{id}/history`). Reverses the type<->
  (category, reason_code) translation `submit_recommendation_feedback`
  already owns; documented as lossy for exactly one collision
  (`not_useful` and `reason` both submit as `(OVERALL, OTHER)` -- see
  `_CATEGORY_REASON_TO_TYPE`'s docstring) rather than silently
  fabricating a false 1:1 mapping. `recommendationId` is resolved from
  the feedback's (possibly revised) `prediction_id` back to the stable
  `RecommendationGeneration.id` via `RecommendationRevision.
  original_prediction_id` (`_recommendation_id_for_prediction`).
- `api/routers/feedback.py` -- `GET /feedback/history` (`pageSize`/
  `cursor` query params, same pattern as every other cursor-paginated
  list endpoint), wired into `api/app.py`.
- `docs/api/openapi.json` regenerated (`python scripts/export_openapi.py`).
- Flutter: `flutter_app/lib/features/feedback/{feedback_history_item,
  feedback_history_screen}.dart`, `FeedbackRepository.fetchHistory`
  (`feedback_repository.dart`) -- a "Feedback history" list (newest
  first, `TimelineEventRow` per entry, "Load more" cursor pagination,
  empty/error/retry states) with the same controlled-learning
  disclosure text repeated at the top, reached as a third "History" tab
  on the existing `PreferencesSettingsScreen` (alongside EPIC-145's
  "Preferences"/"Settings" tabs) rather than a new destination or
  duplicate screen.

**Tests (TDD):**
```
python -m pytest tests/test_api_preferences_feedback.py -q
# 20 passed (15 pre-existing EPIC-144 tests unchanged + 5 new
# GET /feedback/history tests: auth-required, empty-for-new-user,
# lists-newest-first-with-reason/note, per-user isolation,
# pageSize/cursor pagination)

python -m pytest -q
# 1435 passed, 9 skipped -- full existing suite, no regressions

cd flutter_app
flutter analyze
# No issues found!
dart format --output=none --set-exit-if-changed lib test
# Formatted 131 files (0 changed)
flutter test
# All tests passed! (171 total: 5 new in
# test/features/feedback/feedback_history_screen_test.dart, 1 new in
# test/features/preferences/preferences_settings_screen_test.dart,
# rest pre-existing and unaffected)
```

**Deliberately deferred, with rationale:**
- Renaming `marketCapBuckets`/`minConfidenceThreshold` to this doc's
  `marketCaps`/`minTrust`, and splitting `feedback.type` into separate
  `rating`/`reasonCode` fields on the *submission* contract (only added
  to the new, read-only `/history` response) -- both would be
  breaking, purely-cosmetic changes to an already-shipped, tested
  contract with real Flutter consumers, for no functional gain. Named
  here rather than silently ignored.
- No new authentication mechanism -- `GET /feedback/history` reuses the
  same `require_bearer_subject`/real `AuthSession` enforcement
  (EPIC-148) every other per-user endpoint in this API already uses.
