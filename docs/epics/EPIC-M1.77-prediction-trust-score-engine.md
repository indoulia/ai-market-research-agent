# EPIC-M1.77 — Prediction Trust Score Engine

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Create a dedicated, evidence-backed Prediction Trust Score that measures how trustworthy a prediction is, separately from prediction score and calibrated probability.

## Scope
- Combine calibration, historical accuracy, recent performance, sample size, horizon reliability, regime reliability, evidence quality, model stability and drift signals.
- Produce an overall trust score and trust quality.
- Preserve the component scores and reasons behind every trust value.
- Prevent trust increases without measured evidence.
- Support daily recalculation as new outcomes become available.
- Preserve historical trust values immutably.

## Acceptance Criteria
- Trust is distinct from score and confidence.
- Every trust value is explainable and versioned.
- Trust can rise or fall based on evidence.
- Insufficient evidence reduces trust or produces an explicit insufficient-data state.
- Historical trust values are never overwritten.

## Dependency Chain
**Previous:** M1.23, M1.25, M1.50, M1.54, M1.67.
**Next:** M1.78, M1.79, M1.80, M1.84.

## Execution Rule
Trust must be earned from out-of-sample evidence. It must never be increased merely because a model was retrained or a prediction was revised.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.77

### Branch

autonomous/epic-m1-77, branched cleanly from `main` (the declared dependencies -- M1.23, M1.25, M1.50, M1.54, M1.67 -- are already merged).

### Objective

Create a dedicated, evidence-backed Prediction Trust Score that measures how trustworthy a prediction is, separately from prediction score and calibrated probability.

### Design

Every component in `app/prediction_trust_score.py` is a read-only lookup into a signal an earlier EPIC already computed -- this module never recomputes calibration, regime performance, model regression, or evidence quality itself, only combines already-produced evidence (Execution Rule: trust must be earned from out-of-sample evidence; there is no code path here that reads anything about retraining/revision recency at all, so trust can never rise "merely because a model was retrained or a prediction was revised").

### One Real Signal, Three Named Dimensions

Scope names "recent performance," "model stability," and "drift signals" as distinct dimensions, but this platform currently has only one real, independently-computed signal for all three: M1.67's `ModelRegressionCheck` (a model's own real-world performance holding steady vs. regressing over time *is* this platform's current notion of stability/drift). Rather than inventing two more numbers from the same source to look more thorough, `recent_performance_component` alone represents all three -- an honest, forward-compatible choice matching M1.35's own prior posture toward data types with no independent signal yet.

### Sample Size Gates Quality, Not The Average

"Sample size" is not folded into the weighted average -- it gates `trust_quality` independently via `available_component_count`. A perfect 1.0 average built from only 2 or 3 of the 6 possible components is capped at `QUALITY_MEDIUM`/`QUALITY_LOW`, never `QUALITY_HIGH` (`test_few_components_available_caps_trust_quality` proves this directly with a hand-verified case).

### Hard Override For Evidence Leakage

If the prediction's own latest M1.74 `EvidenceQualityDecision` is `STATE_LEAKAGE_DETECTED`, the entire trust score is forced to `QUALITY_INSUFFICIENT_DATA` regardless of how good every other component looks -- a real safety violation is never averaged away (`test_evidence_leakage_forces_insufficient_data`).

### Explainable, Versioned, And Reproducible

Every score persists all six component values (or `None` where unavailable), `available_component_count`, and explicit `reasons` -- fully explainable per-prediction. Append-only and idempotent per `(prediction_id, computed_at)`; a later `computed_at` naturally reflects whatever new evidence dependencies have since produced, without this module triggering their computation (scope: "support daily recalculation as new outcomes become available"; `test_recalculation_reflects_new_evidence`).

### Distinct From Score And Confidence

This module never reads or writes `Prediction.opportunity_score`/`confidence` (`test_never_writes_to_prediction`) -- `PredictionTrustScore` is an entirely new, additive table.

### Files Changed

- `app/prediction_trust_score.py` — new: `compute_prediction_trust_score`, `get_trust_score_history`, component helpers, constants.
- `app/models.py` — new `PredictionTrustScore` model.
- `migrations/versions/0057_prediction_trust_score.py` — new migration.
- `tests/test_prediction_trust_score.py` — new: 8 tests.
- `docs/epics/EPIC-M1.77-prediction-trust-score-engine.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_prediction_trust_score.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0057_prediction_trust_score`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0056` through `0057` (verified `prediction_trust_scores` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **673 passed, 0 failed**.
- `test_prediction_trust_score.py`: **8 passed** — zero available components is `INSUFFICIENT_DATA`; evidence leakage forces `INSUFFICIENT_DATA` even with other strong signals present; too few available components caps quality despite a perfect average; all six components available with hand-verified exact values yields `QUALITY_HIGH`; recalculation with newly-available evidence produces a different, non-`INSUFFICIENT_DATA` result; identical `(prediction_id, computed_at)` calls are idempotent; scores are immutable after creation; the engine never writes to `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Trust is distinct from score and confidence (no read/write of `Prediction.opportunity_score`/`confidence`; proven by test).
- [x] Every trust value is explainable and versioned (six persisted components + `reasons` + `trust_score_version`).
- [x] Trust can rise or fall based on evidence (deterministic recomputation from currently-available signals; proven by test).
- [x] Insufficient evidence reduces trust or produces an explicit insufficient-data state (`QUALITY_INSUFFICIENT_DATA`, component-count cap).
- [x] Historical trust values are never overwritten (append-only, immutable, idempotent per `(prediction_id, computed_at)`).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a hand-verified exact composite score across all six real components. This EPIC composes M1.23/M1.25/M1.41/M1.50/M1.67/M1.74/M1.75 without modifying or duplicating any of them, honestly collapses three scope-named dimensions into the one real signal this platform currently has for them, and never reads anything that could let trust rise without genuine out-of-sample evidence. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
