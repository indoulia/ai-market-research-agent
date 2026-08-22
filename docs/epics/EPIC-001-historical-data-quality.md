# EPIC-001 — Historical Market Data Quality & Dataset Validation

**Status:** DONE
**Priority:** P1
**Owner:** Engineering Orchestrator

## Objective

Establish a trustworthy canonical historical-market dataset on top of the completed M1.1 ingestion foundation so downstream features, backtests, and predictions operate only on validated data.

## Dependencies

- M1 Foundation — merged
- M1.1 Historical NSE Data Ingestion — merged

## Scope

1. Define data-quality rules for OHLCV records.
2. Detect missing trading sessions, duplicate rows, invalid OHLC relationships, non-positive prices/volumes, and timestamp inconsistencies.
3. Add dataset validation/reporting that can run against the canonical PostgreSQL market-price data.
4. Add automated tests for the quality rules and representative failure cases.
5. Record validation results in an auditable report suitable for downstream model/backtest gating.
6. Keep the existing provider abstraction and database contract intact unless evidence requires a narrowly scoped correction.

## Acceptance Criteria

- [x] Quality rules are explicit and machine-checkable.
- [x] Invalid OHLCV records are detected deterministically.
- [x] Duplicate and missing-session conditions are reported.
- [x] Validation results are persisted or emitted in a structured, auditable form.
- [x] Automated tests cover normal and invalid datasets.
- [x] Downstream consumers have a clear signal indicating whether a dataset is valid for modeling/backtesting.
- [x] No live trading or prediction-confidence changes are introduced.

## Completion Evidence

Implemented and merged through the autonomous engineering flow. The implementation commit was `427d5ed` and the resulting work was published as PR #6.

## Non-goals

- New prediction models.
- Autonomous trading.
- Portfolio execution.
- Changing the 1–7 day prediction objective.

## Implementation evidence

- Added the `m1.2-v1` deterministic rule engine for OHLC relationships, positive
  prices/volume, duplicate rows, missing/unexpected sessions, and NSE-local daily
  timestamp consistency.
- Added persisted `dataset_validation_runs` JSON audit reports and a CLI that gates
  downstream work with `PASSED`/`FAILED` status and process exit code.
- Added normal, invalid, missing-session, duplicate, timestamp, and custom-calendar
  test coverage. The default weekday calendar can be replaced with explicit official
  exchange sessions so holidays remain auditable.

## Validation evidence

- `python -m compileall -q app scripts tests migrations` — passed.
- `git diff --check` — passed.
- `pytest -q` — not runnable in the orchestration image because project dependencies
  (including pytest and SQLAlchemy) are not installed; the surrounding workflow must
  run the test suite after installing `requirements.txt`.
