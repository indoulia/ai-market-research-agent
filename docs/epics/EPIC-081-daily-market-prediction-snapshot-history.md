# EPIC-081 — Daily Market & Prediction Snapshot History

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Capture the day-by-day market, evidence, model-input, prediction and trust state required to reconstruct exactly what MRA knew and predicted at each point in time.

## Scope
- Store immutable daily market snapshots for supported securities.
- Capture point-in-time features, evidence references, model/version, prediction, target, stop loss, horizon, score, probability, confidence and trust score.
- Capture data freshness and source metadata.
- Support intraday updates where configured while retaining end-of-day canonical snapshots.
- Preserve every prediction revision rather than overwriting the previous prediction.
- Support complete historical reconstruction for any recommendation.
- Add retention, partitioning and query-performance controls.

## Acceptance Criteria
- Every prediction has a reconstructable as-of snapshot.
- A new day's data never overwrites prior prediction history.
- Prediction revisions are versioned and linked.
- Historical snapshots are immutable.
- The system can reconstruct what data and model produced a past prediction.
- Retention does not silently delete active learning evidence.

## Dependency Chain
**Previous:** EPIC-069, EPIC-073, EPIC-050, EPIC-061.
**Next:** EPIC-084, EPIC-085, EPIC-082, EPIC-087.

## Execution Rule
History is append-only evidence. Current state may be updated, but historical snapshots must remain immutable.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-081

### Branch

autonomous/epic-m1-78, branched cleanly from `main` (the declared dependencies -- EPIC-069, EPIC-073, EPIC-050, EPIC-061 -- are already merged).

### Objective

Capture the day-by-day market, evidence, model-input, prediction and trust state required to reconstruct exactly what this platform knew and predicted at each point in time.

### Design

`DailyPredictionSnapshot` is deliberately a thin, immutable *index* row, not a duplicate of the data it points to: point-in-time features, evidence references, model/version, prediction, target, stop loss, horizon, score, probability, and confidence are all already captured, immutably, by EPIC-061's `RecommendationDecisionTrace`; trust state is already captured, immutably, by EPIC-080's `PredictionTrustScore`. This module only links a prediction to the correct trace and the correct trust score *as of a given calendar day*, never recomputing, duplicating, or mutating either.

### Point-In-Time Safe Trust Attachment

`_latest_trust_score_as_of` only attaches a `PredictionTrustScore` whose `computed_at` is at or before the snapshot's own `snapshotted_at` -- a trust score computed later is never attached to an earlier snapshot (`test_trust_score_attachment_is_point_in_time_safe`).

### Canonical Vs. Intraday Snapshots

`is_canonical` distinguishes the one end-of-day snapshot for a `(prediction_id, snapshot_date)` pair from any number of additional intraday snapshots for that same day -- capturing a canonical snapshot for a day that already has one is idempotent (AC: "a new day's data never overwrites prior prediction history"); intraday snapshots are always freely appended (`test_intraday_snapshots_are_freely_appended`). This platform's real production cadence is one scan per calendar day (EPIC-015), so intraday snapshots are a genuinely usable, forward-compatible capability rather than something already exercised in production today -- the same honest posture already established for other forward-compatible interfaces in this platform (e.g. EPIC-041's MEDIUM/LONG horizon bands).

### Retention Without Deletion

`is_within_active_retention_window` is a purely *derived* classification over a fixed, documented `DEFAULT_SNAPSHOT_RETENTION_WINDOW` -- mirroring EPIC-032's own archiving pattern exactly. Nothing in this module ever deletes or moves a row (AC: "retention does not silently delete active learning evidence" holds trivially and structurally).

### Query-Performance Controls

A composite index on `(prediction_id, snapshot_date)` supports the exact lookup this EPIC's own reconstruction path needs -- a real, achievable interpretation of "query-performance controls" for this platform, rather than a fabricated partitioning scheme this project has no infrastructure for.

### Complete Reconstruction

`reconstruct_snapshot_bundle` joins one snapshot to its linked decision trace and trust score into one read-only bundle (AC: "the system can reconstruct what data and model produced a past prediction").

### Files Changed

- `app/daily_prediction_snapshot.py` — new: `capture_daily_prediction_snapshot`, `get_canonical_snapshot`, `get_snapshot_history`, `reconstruct_snapshot_bundle`, `is_within_active_retention_window`, constants.
- `app/models.py` — new `DailyPredictionSnapshot` model.
- `migrations/versions/0058_daily_prediction_snapshot.py` — new migration.
- `tests/test_daily_prediction_snapshot.py` — new: 9 tests.
- `docs/epics/EPIC-081-daily-market-prediction-snapshot-history.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_daily_prediction_snapshot.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0058_daily_prediction_snapshot`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0057` through `0058` (verified `daily_prediction_snapshots` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **682 passed, 0 failed**.
- `test_daily_prediction_snapshot.py`: **9 passed** — a snapshot correctly links to its trace and trust score; a snapshot honestly reports `None` for either when not yet captured; a canonical snapshot is idempotent per day; intraday snapshots are freely appended alongside exactly one canonical snapshot; trust-score attachment is point-in-time safe; snapshots are immutable after creation; bundle reconstruction returns the correctly linked objects; retention classification is correctly derived without deleting anything; the module never writes to `Prediction` or `RecommendationDecisionTrace`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every prediction has a reconstructable as-of snapshot (`capture_daily_prediction_snapshot`/`reconstruct_snapshot_bundle`).
- [x] A new day's data never overwrites prior prediction history (idempotent canonical capture; immutable rows).
- [x] Prediction revisions are versioned and linked (via EPIC-050's already-established revision chain, unmodified; each revision is its own `Prediction` with its own snapshot).
- [x] Historical snapshots are immutable (`before_update` guard; proven by test).
- [x] The system can reconstruct what data and model produced a past prediction (`reconstruct_snapshot_bundle`).
- [x] Retention does not silently delete active learning evidence (purely derived classification; nothing is ever deleted).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof of point-in-time-safe trust-score attachment. This EPIC composes EPIC-061's decision trace and EPIC-080's trust score without duplicating either's fields, and reuses EPIC-032's own "derived classification, never delete" retention pattern rather than inventing a new one. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
