# EPIC-088 — Prediction Attribution

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P1

## Objective
Determine which evidence, features, market conditions and model signals contributed to successful and failed positive predictions, so MRA can learn what actually drives reliable outcomes.

## Scope
- Attribute prediction decisions to material input factors.
- Preserve point-in-time attribution snapshots.
- Compare attribution patterns for successful vs failed predictions.
- Measure attribution by horizon and market regime.
- Identify consistently useful and consistently misleading factors.
- Feed attribution evidence into controlled experiments and learning.
- Never claim causal impact when only predictive association is established.

## Acceptance Criteria
- Every eligible prediction has explainable attribution evidence.
- Attribution is reproducible from historical inputs.
- Successful and failed predictions can be compared.
- Attribution can be segmented by horizon and regime.
- Historical attribution is immutable.
- Learning consumes attribution as evidence, not as assumed causality.

## Dependencies
Previous: EPIC-043, EPIC-061, EPIC-080, EPIC-081.
Next: EPIC-089.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-088

### Branch

autonomous/epic-m1-85, branched cleanly from `main` (the declared dependencies -- EPIC-043, EPIC-061, EPIC-080, EPIC-081 -- are already merged).

### Objective

Determine which evidence, features, market conditions and model signals contributed to successful and failed positive predictions, so this platform can learn what actually drives reliable outcomes -- without ever claiming causal impact when only predictive association is established.

### Design

`capture_attribution_snapshot` composes rather than duplicates: feature/evidence values are read from EPIC-061's already-immutable `RecommendationDecisionTrace` (never re-derived), the outcome from EPIC-005's `PredictionOutcome`, and the regime via EPIC-021's `classify_market_regime` (reused unchanged). This module's only genuinely new contribution is bucketing two continuous features (`sma20_distance`, `volume_ratio_20d`) into fixed, documented, versioned bands, and `compute_factor_association_report`, which measures each factor value's success-rate *association* -- deliberately never reasoned about or named as causation anywhere in this module. Every verdict is association-flavored (`CONSISTENTLY_ASSOCIATED_WITH_SUCCESS`/`_FAILURE`, `NO_CONSISTENT_ASSOCIATION`), never "causes," "drives," or "explains."

### Honest About What's Not Captured

Snapshots are only captured for genuinely eligible predictions -- ones with both a real evaluated outcome and an already-captured EPIC-061 decision trace; `capture_attribution_snapshot` returns `None` rather than fabricating a snapshot for anything else (`test_snapshot_requires_outcome_and_trace`).

### Reproducible, Segmented, Never Overfit

`compute_factor_association_report` is a deterministic aggregate over already-immutable snapshots; below `MIN_SAMPLE_SIZE_FOR_COMPARISON`, both the whole report and every individual factor value are explicitly `INSUFFICIENT_SAMPLE`, never an unsafe conclusion from sparse data (`test_association_report_insufficient_sample`). `test_association_report_measures_real_association` proves a real, hand-verified association (a `STRONG` `sma20_distance` bucket 100% associated with success, a `WEAK` bucket 100% associated with failure) across horizon, regime, feature-bucket, and evidence-availability dimensions simultaneously (AC: "attribution can be segmented by horizon and regime").

### Feeds Learning As Evidence, Not Assumed Causality

Every association is a number plus a non-causal label, ready for a future controlled-experiment EPIC (EPIC-063/EPIC-064's framework) to consume as a *hypothesis* to test -- this module has no write path to `Prediction`, `ScanCandidate`, or any scoring table itself (`test_never_writes_to_predictions_or_traces`).

### Files Changed

- `app/prediction_attribution.py` — new: `capture_attribution_snapshot`, `get_attribution_snapshot`, `compute_factor_association_report`, `get_association_report_history`, constants.
- `app/models.py` — new `PredictionAttributionSnapshot` and `FactorAssociationReport` models.
- `migrations/versions/0065_attribution_snapshot.py` — new migration.
- `tests/test_prediction_attribution.py` — new: 6 tests.
- `docs/epics/EPIC-088-prediction-attribution.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_prediction_attribution.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0065_attribution_snapshot`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0064` through `0065` (verified both new tables created), `downgrade -1` (verified both dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **742 passed, 0 failed**.
- `test_prediction_attribution.py`: **6 passed** — a prediction without an evaluated outcome or captured trace yields no snapshot; a real snapshot correctly buckets features, captures real evidence availability and regime, and records the real outcome; snapshots are idempotent per prediction; the association report is explicitly insufficient-sample below the floor; a real, hand-verified association (100%/0% success rate by bucket) is measured correctly across horizon/regime/feature/evidence dimensions simultaneously; the module never writes to `Prediction` or its decision trace.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every eligible prediction has explainable attribution evidence (`capture_attribution_snapshot`, only for real evaluated+traced predictions).
- [x] Attribution is reproducible from historical inputs (deterministic aggregate over immutable snapshots).
- [x] Successful and failed predictions can be compared (per-factor success-rate association).
- [x] Attribution can be segmented by horizon and regime (`DIMENSION_HORIZON`/`DIMENSION_REGIME`, proven by test).
- [x] Historical attribution is immutable (`before_update` guard on snapshots).
- [x] Learning consumes attribution as evidence, not as assumed causality (association-only verdict vocabulary; no write path to any production table).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a hand-verified exact association measurement. This EPIC composes EPIC-005/EPIC-021/EPIC-061's already-existing data without duplicating any of it, and strictly avoids causal language anywhere in the code or its own verdict vocabulary, consistent with the scope's own explicit constraint. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
