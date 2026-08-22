# EPIC-034 — Historical Outcome Learning

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Turn completed recommendation history into a clean learning dataset that explains which conditions correlate with successful outcomes.

## Scope
- Build point-in-time-safe learning records.
- Join recommendation features to finalized outcomes.
- Preserve model, score, probability, horizon, market regime, sector, size, and discovery source.
- Prevent future-data leakage.
- Segment historical performance by relevant dimensions.
- Version dataset construction rules.

## Acceptance Criteria
- [ ] Every included record has a known information cutoff.
- [ ] No post-recommendation information enters features.
- [ ] Outcomes are linked deterministically.
- [ ] Dataset construction is reproducible.
- [ ] Dataset versions are immutable.
- [ ] Excluded/incomplete records have explicit reasons.

## Dependencies
**Previous:** EPIC-033, EPIC-020
**Next:** EPIC-035

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-034

### Branch

autonomous/epic-m1-39, branched cleanly from `main` (both declared dependencies -- EPIC-033 and EPIC-020 -- are already merged). This EPIC completes the `EPIC-028 → ... → EPIC-034` continuous-discovery chain.

### Objective

Turn completed recommendation history into a clean, point-in-time-safe, versioned learning dataset -- one immutable row per prediction per dataset version, joining recommendation-time features to the finalized outcome label plus available segment context.

### Feature Cutoff Rules & Leakage Controls

Every feature column (`predicted_probability`, `opportunity_score`, `sma20_distance`, `volume_ratio_20d`, `atr_percent`) is copied from `Prediction`/`ScanCandidate` -- values EPIC-015/EPIC-016 already computed only from information available as of `Prediction.as_of_timestamp` (`information_cutoff` on every row, satisfying AC "every included record has a known information cutoff"). The label (`outcome_classification`, `realized_return`) comes from EPIC-033's `OutcomeMeasurement`, which by construction only exists after the horizon window has closed. This module never treats the label as a feature and never derives a feature from anything dated after the cutoff -- there is no code path in `build_learning_record` that reads `MarketPrice`, `PredictionOutcome`, or any other post-cutoff data into a feature column.

### Dataset Schema

`historical_learning_records`, one row per `(dataset_version, prediction_id)`: `information_cutoff`, five feature columns, `horizon_days`, three "where available" segment columns (`market_regime` via EPIC-021, `sector`/`market_cap_bucket` via EPIC-029), `discovery_source` via EPIC-020, the label (`outcome_classification`/`realized_return`) via EPIC-033, and `included`/`exclusion_reason`.

### Design Decisions

- **Composes rather than duplicates**: regime via EPIC-021's `MarketRegime`, sector/market-cap via EPIC-029's `DiscoverySegment`, discovery source via EPIC-020's `DiscoveryRecord`, and the outcome label via EPIC-033's `OutcomeMeasurement` -- all "where available," the same honest-partial-coverage pattern this platform uses consistently. No existing module is modified.
- **Three distinct, explicit exclusion reasons**, never a silent drop: `NOT_YET_COMPLETED` (no `PredictionOutcome` at all), `OUTCOME_NOT_YET_MEASURED` (an outcome exists but EPIC-033 hasn't classified it -- this module deliberately does *not* call `measure_outcome` itself, keeping dataset construction and outcome measurement as separate responsibilities rather than a surprising cross-module write), and `INSUFFICIENT_DATA_OUTCOME` (measured, but the classification itself is EPIC-033's `INSUFFICIENT_DATA` -- the classification is still recorded on the row for transparency, even though `included=False`).
- **Immutable, versioned dataset rows**: `build_learning_record` is idempotent by `(dataset_version, prediction_id)` uniqueness -- a version, once constructed for a prediction, is never re-derived or mutated (AC: "dataset versions are immutable"). A *different* `dataset_version` string produces entirely separate rows, proven directly by test -- a future construction-rule change ships as a new version, never a mutation of history.
- **Outcomes are linked deterministically** (AC): every join (`Prediction` → `RecommendationGeneration` → `ScanCandidate`/`DiscoveryRecord` → `DiscoverySegment`/`MarketRegime`, and `Prediction` → `PredictionOutcome` → `OutcomeMeasurement`) is a plain, deterministic foreign-key traversal with no ambiguity or randomness.
- **Dataset construction is reproducible** (AC): `build_learning_dataset` iterates every `Prediction` in the system and calls the same deterministic `build_learning_record` for each; running it twice for the same version yields the identical row set (idempotency).

### Sample Dataset Evidence

`test_fully_completed_record_is_included_with_full_context` builds one fully-realized row and asserts every column: `included=True`, `information_cutoff` matching the original `as_of_timestamp`, `predicted_probability=0.72`, a real `opportunity_score`, `sma20_distance=0.03`, `horizon_days=1`, `sector="Energy"`, `market_cap_bucket="LARGE_CAP"`, `discovery_source="CHATGPT"`, and a non-null `market_regime` -- a concrete, verified sample row demonstrating the full join.

### Files Changed

- `app/historical_learning_dataset.py` — new: `build_learning_record`, `build_learning_dataset`, `get_learning_dataset`, exclusion-reason constants, `HistoricalLearningRecordImmutableError`.
- `app/models.py` — new `HistoricalLearningRecord` model.
- `migrations/versions/0028_historical_learning_records.py` — new migration.
- `tests/test_historical_learning_dataset.py` — new: 8 tests.
- `docs/epics/EPIC-034-historical-outcome-learning.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_historical_learning_dataset.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0028_historical_learning_records`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0027` through `0028` (verified `historical_learning_records` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **337 passed, 0 failed** (329 pre-existing from `main` + 8 new).
- `pytest -v tests/test_historical_learning_dataset.py`: **8 passed** — an incomplete recommendation is excluded `NOT_YET_COMPLETED`; a completed-but-unmeasured one is excluded `OUTCOME_NOT_YET_MEASURED`; a measured `INSUFFICIENT_DATA` outcome is excluded `INSUFFICIENT_DATA_OUTCOME` with the classification preserved; a fully completed, measured, segmented, and regime-classified recommendation is `included=True` with every column populated correctly (the sample dataset evidence above); building the same version twice is idempotent; two different dataset versions produce genuinely separate rows; `build_learning_dataset` covers every prediction in one call; and a direct mutation attempt after creation raises `HistoricalLearningRecordImmutableError`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every included record has a known information cutoff (`information_cutoff` on every row).
- [x] No post-recommendation information enters features (feature/label separation is structural, not conventional).
- [x] Outcomes are linked deterministically (plain foreign-key joins throughout).
- [x] Dataset construction is reproducible (idempotent, deterministic `build_learning_record`/`build_learning_dataset`).
- [x] Dataset versions are immutable (`before_update` guard; distinct versions produce distinct rows).
- [x] Excluded/incomplete records have explicit reasons (three distinct, named exclusion reasons, never a silent drop).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a concrete sample fully-populated dataset row. This EPIC composes EPIC-020/EPIC-021/EPIC-029/EPIC-033's existing outputs into one clean, joined, versioned table rather than duplicating any of their logic. This completes the `EPIC-028`–`EPIC-034` continuous-discovery chain. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->