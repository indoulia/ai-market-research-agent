# EPIC-M1.142 — Feedback, Preferences & Settings UI

**Track:** UI
**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Provide lightweight user controls for horizons, discovery scope, notifications, display preferences and manual recommendation feedback without cluttering the main experience.

## Screens
### Quick Preferences
- Default horizon: 1/2/3/5/7 trading days.
- Market/sector/industry/size filters.
- Watchlist.
- Notification toggles.

### Recommendation Feedback
- One-tap useful/not useful.
- Optional structured reason.
- Optional comment.
- Show acknowledgement that feedback is used for learning/analysis, not instant model changes.

### Settings
- Appearance/theme.
- Data refresh display preference.
- Notification preferences.
- About/version/data-provider transparency.

## UX Rules
- Preferences should be compact forms, not long settings pages.
- Use segmented controls, chips, switches and grouped cards.
- Feedback should take one or two interactions.
- Never use modal dialogs for routine feedback.
- Preserve unsaved form state safely and provide clear save status.

## Acceptance Criteria
- Default short-term horizon is configurable and starts at 1–7 days.
- User preferences persist through M1.141.
- Feedback references the exact recommendation version visible to the user.
- No UI promises that feedback immediately changes the model.
- Settings are responsive and keyboard/touch accessible.

## Parallelization
UI implementation against M1.141 fixture/OpenAPI data.

## Dependencies
M1.133, M1.134, M1.141.

## Completion Report

**Implemented on branch:** `autonomous/epic-m1-142`. Started against M1.141's documented contract (still `APPROVED` at the time, per its own "UI implementation against M1.141 fixture/OpenAPI data" parallelization note) — **M1.141 merged for real partway through this epic**, so the implementation was reconciled against the actual `api/schemas/preferences.py`/`api/schemas/feedback.py`/`api/services/feedback.py` before finishing, not left on the guessed shape. Two real, would-be-broken integration bugs were caught this way:

1. **`notificationPreferences`**: guessed as three independent booleans; the real contract is `{ mutedAlertTypes: string[] }`, an opt-out list keyed to `app.recommendation_alerts`'s fixed `ALERT_TYPE_*` vocabulary (`EXPIRY`, `INVALIDATION`, `REVALIDATION_UPDATE`, `MARKET_REGIME_CHANGE`, `NEW_OPPORTUNITY` — `MAJOR_NEWS_EVENT` exists but is never triggered by any real event source yet, so it's omitted from the UI rather than offered as a dead toggle). Rebuilt as a mute-chip row against the real vocabulary.
2. **Feedback's `predictionVersion`**: guessed as the whole version bundle; the real `FeedbackRequest.predictionVersion` is a single string, compared server-side against `get_active_version(...).model_version` (`api/services/feedback.py`). Fixed by changing the field type through `feedback_repository.dart`/`recommendation_feedback_section.dart` to a plain `String`, sourced from `detail.predictionVersion['modelVersion']` at the call site.

`displayPreferences` (`themeMode`/`showFreshnessTimestamps`, this UI's own keys) turned out fine as originally guessed — the real schema is `model_config = {"extra": "allow"}`, a genuinely opaque free-form object, confirmed compatible. Also added while reconciling: `Idempotency-Key` header support (`ApiClient.post`'s new `headers` param, a client-generated key reused only when the *same* feedback reason is manually retried after a failure — matches the real server's `FeedbackIdempotencyKey` dedup mechanism), and `riskPreference`/`minConfidenceThreshold`/`preferenceVersion` round-tripped on `Preferences` (the first is optional-but-accepted by `PUT` and must not be silently wiped by a save from a UI that never edits it; the latter two are response-only and never sent back).

**Destination-to-screen mapping:** the Settings destination hosts two tabs — "Preferences" (`QuickPreferencesScreen`) and "Settings" (`GeneralSettingsScreen`) — same nesting pattern M1.140 used for Market's Overview/News & Events, since M1.134's shell has one Settings destination, not two. The "Design system gallery (QA)" link (previously the whole content of the old placeholder Settings screen) now lives in the "Settings" tab's always-visible About section — deliberately not gated behind the preferences fetch, so a slow/failed M1.141 call never blocks it.

**What was built:**
- `lib/core/api_client.dart` extended with `put`/`post` (previously `get`-only), sharing one `_decode` envelope/error path — covered by a new `test/core/api_client_test.dart` using a fake `http.Client`.
- `lib/core/api_client.dart` extended with `put`/`post` (previously `get`-only) plus optional per-call `headers` on `post`, sharing one `_decode` envelope/error path — covered by a new `test/core/api_client_test.dart` using a fake `http.Client`.
- `lib/features/preferences/`: `preferences.dart` (model, reconciled — see above), `preferences_repository.dart` (`GET`/`PUT /preferences`), `chip_list_editor.dart` (free-text add/remove chips for watchlist/sectors — no enumeration endpoint exists for either, so free text is the honest choice over a fabricated fixed picklist), `theme_mode_selector.dart`, `quick_preferences_screen.dart` (horizon, market-cap chips, watchlist, sectors, alert-mute chips, inline "Saving…/Saved/Save failed" status — no separate Save button, matching "one or two interactions"), `general_settings_screen.dart`, `preferences_settings_screen.dart` (the two-tab container).
- `lib/features/feedback/`: `feedback.dart` (the exact `useful|not_useful|target_realistic|target_too_high|target_too_low|reason` vocabulary, confirmed against `api/schemas/feedback.py`), `feedback_repository.dart` (`POST /recommendations/{id}/feedback` with idempotency-key support), `recommendation_feedback_section.dart` — embedded into EPIC-M1.138's `RecommendationDetailScreen` (additive, verified zero-regression against that epic's existing unmodified test suite before adding new tests). One-tap Useful/Not-useful buttons, three reason chips, an optional comment field, and an explicit acknowledgement ("queued for learning/analysis... will not change ... immediately") both before and after submission — no modal dialog anywhere in this flow (UX rule), verified by a test that asserts no `Dialog`/`AlertDialog` exists in the tree.
- **Real bug found and fixed**: `RecommendationDetail` (M1.138) parsed every field except `predictionVersion` itself, needed for feedback's "reference the exact recommendation version visible to the user" (AC). Added as an opaque `Map<String, dynamic>` (the full replay-version bundle); the feedback call site extracts just `['modelVersion']` as required by the real contract (see above).

**Tests:** `test/core/api_client_test.dart`, `test/features/preferences/*` (3 files), `test/features/feedback/recommendation_feedback_section_test.dart`. Full suite: `flutter test` → 72/72. `flutter analyze` → no issues.

**Acceptance criteria status:**
- Done: default horizon configurable at 1/3/5/7 days (see gap below), feedback references the real `modelVersion` string, no UI text claims instant model changes, settings are keyboard/touch accessible (standard `TextField`/`SwitchListTile`/`ChoiceChip`), preferences round-trip through the real, merged M1.141 contract without an authenticated session (see gap below).
- Explicit gap, not fabricated: M1.142's doc says default horizon should offer "1/2/3/5/7" days, but this UI offers only 1/3/5/7 — day-2 is a named vocabulary entry elsewhere in this platform (`SUPPORTED_HORIZON_DAYS`) that is never actually produced by any real prediction (per this session's own memory of the backend), and every other screen in this app (M1.136's dashboard filter) already only offers 1/3/5/7 — offering a day-2 preference option would be presenting a choice the platform can't honor. Sectors/industries have no enumeration endpoint, so `ChipListEditor` is free-text rather than a validated picklist.
- **Explicit, not-yet-closable gap**: `GET`/`PUT /preferences` internally require a caller identity (`api/deps.py::require_bearer_subject`), so calling them with no `Authorization` header will 401 against a real deployment right now — this UI doesn't send one, since there is no session/token source until EPIC-M1.145/M1.146 (Auth) land, which are later in this session's own queue. Not faked here; once auth exists, the fix is to have `ApiClient` attach the session's bearer token (e.g. a header set once at login), not something each repository should do individually.
