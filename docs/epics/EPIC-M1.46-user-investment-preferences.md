# EPIC-M1.46 — User Investment Preferences

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** M1.14

## Objective
Allow each user to define investment preferences that control recommendation discovery, scoring, ranking, and default horizon without changing the underlying historical truth or recommendation contract.

## Scope
- Default horizon: short term (1–7 days).
- Support short, medium, long, and custom horizons.
- Store risk preference and minimum confidence threshold.
- Support market-cap/sector preferences without forcing them.
- Apply preferences consistently to discovery and recommendation selection.
- Preserve the preference snapshot used when a recommendation is generated.

## Acceptance Criteria
- New users default to short-term 1–7 day recommendations.
- A user can change horizon and supported preferences.
- Recommendation generation records the effective preference snapshot.
- Preference changes do not mutate historical recommendations.
- Invalid preference combinations are rejected clearly.
- Tests cover defaults, persistence, overrides, and historical immutability.

## Dependency Chain
M1.14 → M1.46 → M1.47+

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.46

### Branch

autonomous/epic-m1-46, branched cleanly from `main` (the declared dependency -- M1.14 -- is already merged).

### Objective

Let each user define investment preferences that control which of M1.14's already-selected recommendations are surfaced to them, without changing M1.9's scoring, M1.10's horizon selection, M1.13's generation, or M1.14's system-wide daily selection in any way.

### Design

Two append-only tables:
- **`UserPreference`**: versioned per user -- the same "the log is the pointer" pattern M1.31/M1.44 already established. The most recent row for a `user_id` is that user's current effective preference; changing a preference (`set_user_preference`) always inserts a new row, never updates a prior one.
- **`RecommendationPreferenceSnapshot`**: records, immutably and idempotently per `(user_id, recommendation_generation_id)`, exactly which preference version was in effect and whether that recommendation matched it.

`apply_preferences_to_scan_selection` personalizes M1.14's already-selected, system-wide daily picks (`select_recommendations_for_scan`, reused as-is) for one user: it filters by horizon band and minimum confidence (hard filters -- `included=False` with an explicit reason if either fails), and flags a soft sector/market-cap preference match (`preference_match_boost`) that never excludes a recommendation, only marks it. `RecommendationSelection`/`Prediction`/`ScanCandidate` are never written to.

### Horizon Bands

`SHORT` (1-7 days) covers this platform's entire currently-populated `VALID_HORIZON_DAYS` range and is the default for new users (AC: "new users default to short-term 1-7 day recommendations"). `MEDIUM` (8-30) and `LONG` (31+) are defined for forward compatibility even though M1.10 has never produced a prediction in those ranges -- a user selecting them today honestly sees zero matches rather than a fabricated one, the same honesty pattern this platform uses for every not-yet-populated dimension. `CUSTOM` requires an exact day count that must be one of `VALID_HORIZON_DAYS` (M1.13) to ever be satisfiable, rejected otherwise.

### Validation

`set_user_preference` validates every field before writing anything (AC: "invalid preference combinations are rejected clearly", raising `InvalidPreferenceError`): `horizon_band` must be a known band; `custom_horizon_days` is required if and only if `horizon_band == CUSTOM`, and must be a valid horizon day count; `risk_preference` must be one of `LOW`/`MEDIUM`/`HIGH`; `min_confidence_threshold` must be within `[0, 1]`; `preferred_market_cap_buckets` must only contain known buckets (reused from M1.34's `MARKET_CAP_BUCKET_THRESHOLDS`/`BUCKET_UNCLASSIFIED`, not redefined). Sector has no fixed vocabulary to validate against (`Stock.sector` is free text) and is always soft.

### Historical Immutability

`RecommendationPreferenceSnapshot` is looked up by `(user_id, recommendation_generation_id)` before ever creating a new one -- a recommendation already snapshotted for a user returns its original snapshot unchanged even after that user's preference has since changed (AC: "preference changes do not mutate historical recommendations"), proven directly by `test_preference_change_does_not_mutate_an_existing_snapshot`. `UserPreference` itself carries a `before_update` immutability guard (`UserPreferenceImmutableError`) so a past preference version can never be edited in place, only superseded by a new row.

### Files Changed

- `app/user_preferences.py` — new: `set_user_preference`, `get_current_preference`, `apply_preferences_to_scan_selection`, band/risk/reason constants, `InvalidPreferenceError`, `UserPreferenceImmutableError`.
- `app/models.py` — new `UserPreference` and `RecommendationPreferenceSnapshot` models.
- `migrations/versions/0031_user_preferences.py` — new migration.
- `tests/test_user_preferences.py` — new: 15 tests.
- `docs/epics/EPIC-M1.46-user-investment-preferences.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_user_preferences.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0031_user_preferences`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0030` through `0031` (verified both new tables created), `downgrade -1` (verified both dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **404 passed, 0 failed** (389 pre-existing from `main` + 15 new).
- `pytest -q tests/test_user_preferences.py -v`: **15 passed** — a new user defaults to `SHORT`/`MEDIUM` risk/M1.8's `MIN_CONFIDENCE`; the default lookup is idempotent; a user can change preferences without mutating the prior version; `CUSTOM` horizon validation (missing day count, invalid day count, valid day count) and non-`CUSTOM`-with-a-day-count rejection; invalid risk preference, confidence threshold, and market-cap bucket are each rejected; a preference row is immutable after creation; a recommendation within preferences is included; one outside the horizon band and one below the confidence threshold are each excluded with the correct reason; a preferred sector produces a soft boost on one candidate without excluding the non-matching one; a preference change does not retroactively alter an existing snapshot; no `Prediction`/`ScanCandidate` row is ever mutated.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] New users default to short-term 1-7 day recommendations (`DEFAULT_HORIZON_BAND = SHORT`, lazily created on first lookup).
- [x] A user can change horizon and supported preferences (`set_user_preference` always inserts a new version).
- [x] Recommendation generation records the effective preference snapshot (`RecommendationPreferenceSnapshot`, one per user/recommendation).
- [x] Preference changes do not mutate historical recommendations (idempotent snapshot lookup; `UserPreference` immutability guard; proven by test).
- [x] Invalid preference combinations are rejected clearly (`InvalidPreferenceError` for every structurally invalid combination, validated before any write).
- [x] Tests cover defaults, persistence, overrides, and historical immutability (all covered, see Test Results).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that a preference change never alters an already-recorded snapshot. This EPIC never modifies M1.9/M1.10/M1.13/M1.14 -- it composes M1.14's own selection output and M1.34's market-cap bucket vocabulary into a purely additive, per-user personalization layer. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
