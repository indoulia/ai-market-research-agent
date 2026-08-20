# EPIC-M1.8 — Positive Consensus Engine

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** ChatGPT  
**Priority:** P1

## Objective

Define and implement the deterministic decision layer that turns model/data signals into a **positive recommendation candidate** only when the required positive criteria are satisfied.

## Why now

M1.4–M1.7 establish recommendation history, objective outcomes, performance measurement, and watchlist evaluation. We now need one explicit, testable definition of what "positive consensus" means instead of allowing individual callers to invent their own thresholds.

## Scope

1. Define a single versioned positive-consensus contract.
2. Define required signals/criteria and their minimum thresholds using the capabilities already present in the repository.
3. Produce an explainable evaluation result containing PASS/FAIL per criterion and an overall qualifying decision.
4. Ensure only qualifying candidates can enter the positive-recommendation path.
5. Persist the criteria/contract version used for a recommendation.
6. Add deterministic unit tests for qualifying, borderline, and failing cases.

## Non-goals

- New ML model development.
- LLM-based final recommendation decisions.
- Negative/sell recommendations.
- Portfolio management or trading.
- UI/dashboard work.
- Optimizing thresholds from historical data; that belongs in a later learning/calibration EPIC.

## Acceptance Criteria

- [ ] Positive consensus is represented by one explicit versioned contract.
- [ ] Every required criterion has a deterministic pass/fail rule.
- [ ] Evaluation output explains each criterion result.
- [ ] A stock cannot become a positive recommendation unless the contract qualifies it.
- [ ] The contract version is traceable for every resulting recommendation.
- [ ] Tests cover positive, borderline, and failing candidates.
- [ ] No subjective LLM decision is required for final qualification.

## Dependencies

- M1.3 — Yahoo NSE Historical Data Provider
- M1.4 — Persist Recommendation History

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.8

### Branch

autonomous/epic-m1-8 (stacked on the still-open `planning/approve-m1-8-m1-11` branch, which carries this EPIC's `APPROVED`/`READY_FOR_EXECUTION` authorization; not yet merged to `main` at the time of this implementation)

### Objective

A single, explicit, versioned, deterministic decision layer (`app/consensus.py`) that gates entry into the positive-recommendation path, using only signals already produced elsewhere in the repository.

### Design Decisions

The EPIC intentionally leaves the exact criteria/thresholds unspecified ("using the capabilities already present in the repository"), so this is a concrete design choice made here, documented for reviewer traceability:

- **Contract:** `CONTRACT_VERSION = "PCC-001"` in `app/consensus.py`. Any future change to a criterion or threshold must bump this constant (never silently redefine `"PCC-001"`), since it is persisted per-recommendation for traceability.
- **Five criteria, each drawing on an existing repository capability, none learned/optimized from historical outcomes (per non-goal):**
  1. `model_probability`: `predicted_probability >= 0.60` — the model's calibrated output already produced by `app/prediction/baseline.py` / stored on `Prediction`.
  2. `model_confidence`: `confidence >= 0.55` — the existing `Prediction.confidence` field.
  3. `positive_trend`: `sma20_distance > 0` — price above its 20-day SMA, from `app/features/technical.py`'s existing feature set.
  4. `sufficient_liquidity`: `volume_ratio_20d >= 0.75` — also from `app/features/technical.py`; guards against recommending on abnormally thin trading days.
  5. `data_quality`: the underlying OHLCV window passed `app/market_data/quality.py`'s deterministic validation (`ValidationReport.is_valid`).
- **Missing data fails its criterion explicitly** (`None` -> FAIL with an "is missing" detail) rather than being silently skipped, defaulted, or crashing — anticipates M1.9's identical concern and keeps `ConsensusInputs` conversion (float features -> `Decimal`) a caller responsibility, kept out of this EPIC's scope.
- **Enforcement point:** a single new function, `record_qualifying_recommendation(session, evaluation, **kwargs)`, is the only path that persists a positive recommendation with a consensus contract behind it; it raises `ConsensusNotQualifiedError` before touching the session if `evaluation.qualifies` is `False`. The existing `record_recommendation` (M1.4) remains the lower-level primitive it wraps, now also requiring `consensus_contract_version` for every recommendation (see below), not only ones routed through the new gate — this is what makes AC "traceable for every resulting recommendation" universal rather than gate-path-only.
- **Persistence:** added `Prediction.consensus_contract_version` (new required `String(32)` column, added to `IMMUTABLE_FIELDS` in `app/recommendations.py` so it can never be altered after issuance, same as every other original-recommendation field). New migration `0008_consensus_contract_version`, chaining off the current head `0007_outcome_actual_return`. Added with a temporary `server_default="UNVERSIONED"` then dropped (same established pattern as `0005_prediction_confidence`), since the table may not always be empty.
- Retrofitted the three pre-existing test fixtures that call `record_recommendation`/construct `Prediction` directly (`tests/test_recommendation_history.py`, `tests/test_outcome_evaluation.py`, `tests/test_recommendation_history_db_integrity.py`) with `consensus_contract_version="PCC-001"`, since the field is now required on every `Prediction` row. No behavior of those pre-existing tests changed otherwise.

### Files Changed

- `app/consensus.py` — new: contract, criteria evaluation, and the gated recording function.
- `app/models.py` — added `Prediction.consensus_contract_version`.
- `app/recommendations.py` — `record_recommendation` now requires `consensus_contract_version`; added to `IMMUTABLE_FIELDS`.
- `migrations/versions/0008_consensus_contract_version.py` — new migration.
- `tests/test_positive_consensus.py` — new: 19 tests.
- `tests/test_recommendation_history.py`, `tests/test_outcome_evaluation.py`, `tests/test_recommendation_history_db_integrity.py` — updated fixtures for the new required field.
- `docs/epics/EPIC-M1.8-positive-consensus-engine.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_positive_consensus.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- Migration validation against a disposable scratch PostgreSQL database (created and dropped for this validation only): full `upgrade head` through `0008` (verified `consensus_contract_version` is `NOT NULL` via `information_schema.columns`), then `downgrade -1` (verified the column is dropped) and `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **56 passed**, 3.06s (37 pre-existing on `main` + 19 new in `test_positive_consensus.py`).
- `pytest -v tests/test_positive_consensus.py`: **19 passed** — covers a fully-qualifying candidate, each of the three numeric thresholds at the exact boundary (inclusive `>=`, all still qualify — the "borderline" AC), each criterion failing individually with the correct criterion name reported, missing data for every field failing explicitly, multiple simultaneous failures all reported independently, determinism/repeatability on identical input, a qualifying candidate successfully recorded with its contract version traced on the persisted row, and a non-qualifying candidate rejected by `record_qualifying_recommendation` before touching the database.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration `0008` upgrade: applied cleanly on top of the full chain through `0007`; column confirmed `NOT NULL`. Downgrade: column confirmed dropped. Re-upgrade: clean.
- Caught and fixed one bug during validation: the initial migration filename/revision id (`0008_predictions_consensus_contract_version`, 44 chars) exceeded Alembic's default `alembic_version.version_num` column width (`VARCHAR(32)`), which only surfaces once a migration actually runs against a real database (`StringDataRightTruncation`) — SQLite-backed unit tests don't enforce that column's length and would not have caught it. Renamed to `0008_consensus_contract_version` (31 chars) and re-validated.

### Acceptance Criteria

- [x] Positive consensus is represented by one explicit versioned contract.
- [x] Every required criterion has a deterministic pass/fail rule.
- [x] Evaluation output explains each criterion result.
- [x] A stock cannot become a positive recommendation unless the contract qualifies it.
- [x] The contract version is traceable for every resulting recommendation.
- [x] Tests cover positive, borderline, and failing candidates.
- [x] No subjective LLM decision is required for final qualification.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including catching and fixing a real Postgres-only bug (the revision-id length) that unit tests alone would have missed. The specific criteria/thresholds chosen are a design decision within the EPIC's deliberately open scope, documented above for reviewer scrutiny — a different threshold philosophy is a legitimate review finding, not a defect in the mechanism itself. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
