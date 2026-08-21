# EPIC-M1.70 — User Preference Learning

Status: DONE
Execution Status: COMPLETED

## Objective
Learn stable user preferences from repeated behavior while keeping explicit user settings authoritative.

## Scope
- Observe accepted/rejected recommendation patterns.
- Detect stable preference signals.
- Suggest preference changes to the user.
- Never silently alter explicit user settings.
- Separate personal preference learning from global model learning.

## Acceptance Criteria
- User can inspect why a preference suggestion was generated.
- Minimum evidence thresholds are explicit.
- Explicit settings always override inferred preferences.
- Personal learning cannot modify the global production model.

## Dependencies
Previous: M1.69.
Next: M1.71.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.70

### Branch

autonomous/epic-m1-70, branched cleanly from `main` (the declared dependency -- M1.69 -- is already merged).

### Objective

Learn stable user preferences from repeated behavior while keeping M1.46's explicit `UserPreference` authoritative.

### Design

"Observe accepted/rejected recommendation patterns" (scope) uses the only real, already-existing signal of a user's own reaction to a specific recommendation: M1.52's `RecommendationFeedback` -- `REASON_AGREE` is treated as "accepted," any other valid reason code as "rejected." No fabricated accept/reject action was invented. `observe_horizon_band_feedback` groups a user's own feedback by which of M1.46's fixed horizon bands (`HORIZON_BAND_DAY_RANGES`, reused unchanged) the underlying prediction falls into. `generate_preference_suggestion` only produces a suggestion when a band other than the user's current one has both sufficient sample (`MIN_SAMPLE_SIZE_FOR_COMPARISON`, M1.16, reused) and an agreement-rate edge over the current band of at least the new, explicit `PREFERENCE_SIGNAL_MARGIN` (0.20) -- otherwise it returns `None`.

### Personal Learning Cannot Modify The Global Production Model

This module has no write path to `UserPreference`, `Prediction`, `ScanCandidate`, or any scoring/selection table -- only to its own new `UserPreferenceSuggestion` table (proven directly by `test_never_writes_to_predictions_feedback_or_preferences`).

### Explicit Settings Always Override Inferred Preferences

`app.user_preferences.apply_preferences_to_scan_selection` never reads `UserPreferenceSuggestion` -- a suggestion can only ever take effect if the user explicitly calls `set_user_preference` themselves. `_latest_preference_readonly` only ever *reads* `UserPreference` (unlike M1.46's own `get_current_preference`, which lazily inserts a default) -- this module cannot write a preference under any circumstance, even a default one.

### Minimum Evidence Thresholds Are Explicit

Two explicit gates: M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON` per band, and this EPIC's own `PREFERENCE_SIGNAL_MARGIN` -- proven insufficient-sample (`test_insufficient_sample_produces_no_suggestion`) and insufficient-margin (`test_small_margin_does_not_trigger_suggestion`) cases are both correctly suppressed.

### User Can Inspect Why A Suggestion Was Generated

Every `UserPreferenceSuggestion` stores its evidence sample count, the winning band's agreement rate, the current band's own agreement rate (if any), and a human-readable `rationale` string naming the exact numbers behind the suggestion.

### Files Changed

- `app/user_preference_learning.py` — new: `observe_horizon_band_feedback`, `generate_preference_suggestion`, `get_suggestions_for_user`, constants.
- `app/models.py` — new `UserPreferenceSuggestion` model.
- `migrations/versions/0051_preference_suggestions.py` — new migration.
- `tests/test_user_preference_learning.py` — new: 8 tests.
- `docs/epics/EPIC-M1.70-user-preference-learning.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_user_preference_learning.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0051_preference_suggestions`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0050` through `0051` (verified `user_preference_suggestions` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **607 passed, 0 failed** (599 pre-existing from `main` + 8 new).
- `pytest -q tests/test_user_preference_learning.py -v`: **8 passed** — no feedback yields no suggestion; insufficient sample yields no suggestion; a genuinely stable, well-supported band preference produces a correctly-detailed suggestion; a current band that is already the user's best-supported band yields no suggestion; a margin below the explicit threshold yields no suggestion; a suggestion is immutable after creation; the pipeline never writes to `Prediction`/`RecommendationFeedback`/`UserPreference`; stored suggestions are retrievable per user and isolated between users.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] User can inspect why a preference suggestion was generated (`rationale` + evidence fields).
- [x] Minimum evidence thresholds are explicit (`MIN_SAMPLE_SIZE_FOR_COMPARISON` + `PREFERENCE_SIGNAL_MARGIN`).
- [x] Explicit settings always override inferred preferences (no write path to `UserPreference`; proven by test).
- [x] Personal learning cannot modify the global production model (no write path to any production table; proven by test).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that this module never writes to any production or explicit-preference table. It reuses M1.46's horizon-band vocabulary and M1.16's minimum-sample convention rather than inventing parallel ones, and treats M1.52's existing feedback as the only real signal of user acceptance/rejection rather than fabricating a new one. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
