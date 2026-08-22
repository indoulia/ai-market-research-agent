# EPIC-056 — Multi-Horizon Recommendation Resolution

Status: DONE
Execution Status: COMPLETED

## Objective
Represent short-, medium-, and long-term views independently and clearly resolve conflicting horizon outcomes.

## Scope
- Preserve horizon-specific scores, confidence, target, and SL.
- Detect conflicts between horizons.
- Define deterministic presentation priority based on user preference.
- Never hide a material conflicting view.

## Acceptance Criteria
- Default user horizon remains short term (1–7 days).
- Other horizons are opt-in/configurable.
- Conflicts are explicitly surfaced.
- Historical horizon decisions remain immutable.

## Dependencies
Previous: EPIC-055.
Next: EPIC-057.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-056

### Branch

autonomous/epic-m1-61, branched cleanly from `main` (the declared dependency -- EPIC-055 -- is already merged).

### Objective

Represent short-, medium-, and long-term views of one stock independently and deterministically resolve which one to present when more than one is currently open, without ever hiding a material conflicting view.

### Design

This platform's horizon selection (EPIC-010) only ever produces short-term (1-7 day) predictions today; "multi-horizon" in practice means comparing several currently-open predictions for the same stock made at different times with different EPIC-010-selected horizons (1, 3, 5, or 7 days). `get_horizon_views` preserves each one's own already-immutable score/confidence (`Prediction`) and horizon independently (scope: "preserve horizon-specific scores, confidence, target, and SL" -- target/SL remain queryable per prediction via EPIC-042, not duplicated here).

### Conflict Detection

`resolve_multi_horizon_view` flags any other currently-open prediction whose `opportunity_score` differs from the chosen primary's by at least `CONFLICT_SCORE_MARGIN` (20 points on the 0-100 scale) as a conflicting view -- explicitly recorded in `conflicting_prediction_ids`, never silently dropped (AC: "conflicts are explicitly surfaced").

### Presentation Priority From User Preference

Reuses EPIC-041's `UserPreference.horizon_band`/`custom_horizon_days` directly: among currently-open predictions matching the user's preferred band, the highest-scoring one is chosen as primary; if none match, the single best-scoring prediction overall is still surfaced rather than returning nothing (scope: "never hide a material conflicting view"). Because this composes EPIC-041's own preference system, "default user horizon remains short term" and "other horizons are opt-in/configurable" (AC) are inherited for free -- EPIC-041 already established `SHORT` as the default and `MEDIUM`/`LONG`/`CUSTOM` as explicit opt-ins.

### Historical Immutability

Every resolution is a new, independent row -- re-resolving as new predictions arrive never edits a prior decision, only supersedes it with a later one (AC: "historical horizon decisions remain immutable"). `get_resolution_history` retains every decision ever made for a `(user_id, stock_id)` pair. `test_resolution_never_writes_to_predictions` proves the underlying `Prediction` rows are never touched.

### Files Changed

- `app/multi_horizon_resolution.py` — new: `resolve_multi_horizon_view`, `get_horizon_views`, `get_resolution_history`, `HorizonView` dataclass, `NoOpenRecommendationError`.
- `app/models.py` — new `MultiHorizonResolution` model.
- `migrations/versions/0043_multi_horizon_resolution.py` — new migration.
- `tests/test_multi_horizon_resolution.py` — new: 9 tests.
- `docs/epics/EPIC-056-multi-horizon-resolution.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_multi_horizon_resolution.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0043_multi_horizon_resolution`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0042` through `0043` (verified `multi_horizon_resolutions` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **539 passed, 0 failed** (530 pre-existing from `main` + 9 new).
- `pytest -q tests/test_multi_horizon_resolution.py -v`: **9 passed** — a single open horizon has no conflict; no open recommendation raises `NoOpenRecommendationError`; divergent scores across two horizons are flagged as a conflict with the higher-scoring one winning by default; the default preference prioritizes the short horizon even when it scores lower; an explicit user preference for a different horizon overrides the default and correctly surfaces the outvoted short horizon as a conflict; when no open horizon matches the user's preference the single best-available one is still surfaced, never hidden; horizon views preserve each prediction independently; resolution history retains every decision; resolution never writes to `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Default user horizon remains short term (1-7 days) (inherited from EPIC-041's `DEFAULT_HORIZON_BAND = SHORT`, proven by test).
- [x] Other horizons are opt-in/configurable (inherited from EPIC-041's `MEDIUM`/`LONG`/`CUSTOM` bands; proven by test with a custom-horizon preference).
- [x] Conflicts are explicitly surfaced (`conflicting_prediction_ids`/`has_conflict`, proven by test).
- [x] Historical horizon decisions remain immutable (every resolution is a new row; `Prediction` never touched; proven by test).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof that a user's explicit preference can override the default and still honestly surface the outvoted view as a conflict. This EPIC composes EPIC-041's preference system and EPIC-042's already-immutable per-prediction scoring/target-SL without duplicating either, and never fabricates coverage for horizon bands (medium/long) this platform's own pipeline has never populated. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
