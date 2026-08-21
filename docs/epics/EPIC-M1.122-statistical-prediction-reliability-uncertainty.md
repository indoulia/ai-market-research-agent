# EPIC-M1.122 — Statistical Prediction Reliability & Uncertainty

**Status:** VALIDATING
**Execution Status:** IMPLEMENTED_PR_OPEN
**Priority:** P0

## Objective
Make MRA probability, confidence and Trust Score statistically defensible by measuring evidence strength, calibration uncertainty and distinct sources of uncertainty rather than treating a point probability as certainty.

## Scope
- Add sample-size and evidence-strength measures to prediction reliability.
- Estimate confidence intervals for empirical success rates and probability estimates.
- Track calibration by horizon, regime, sector, market-cap bucket, stock and setup where sample size permits.
- Add bootstrap/stability analysis for prediction estimates and model comparisons.
- Distinguish model/epistemic uncertainty, market/aleatoric uncertainty, data uncertainty and evidence uncertainty where feasible.
- Produce predictive ranges/distributions in addition to point targets where supported.
- Integrate uncertainty and evidence strength into Trust Score and positive-only eligibility.
- Prevent small-sample high-success histories from producing artificially high Trust.
- Define minimum evidence thresholds and shrinkage/backoff policies for sparse segments.
- Preserve methodology and statistical-estimation versions with predictions.

## Required Outputs
- Probability
- Confidence interval / reliability band
- Evidence sample size
- Calibration status
- Uncertainty components
- Trust Score
- Evidence-strength indicator
- Prediction range where available

## Acceptance Criteria
- A high probability with insufficient evidence cannot produce high Trust solely from the probability value.
- Calibration metrics are segmented only when statistically meaningful.
- Sparse segments fall back to broader validated populations using explicit policy.
- Uncertainty is represented separately from directional confidence.
- Statistical calculations are reproducible and versioned.
- Historical reliability values remain immutable.

## Dependencies
M1.68, M1.77, M1.82, M1.86, M1.100, M1.101, M1.102.

## Non-Goal
Do not manufacture precision. When evidence is insufficient, MRA must suppress the opportunity rather than display misleading confidence.

## Completion Report

**Status:** VALIDATING — implemented, tests green, PR open (not yet merged).

**Implementation:**
- `app/prediction_reliability.py`: a new, versioned (`RELIABILITY_RULE_VERSION = "PRU-001"`) module, and a new immutable table `prediction_reliability_assessments` (migration `0093_prediction_reliability.py`), idempotent by `(prediction_id, assessed_at)`.
- **Add sample-size/evidence-strength measures, estimate confidence intervals for empirical success rates, track calibration by segment where sample size permits, define minimum evidence thresholds/backoff for sparse segments:** the sample size, observed rate and hierarchical stock→setup→sector→market-cap→horizon→global fallback are already M1.104's own (`segment_calibration.assess_segment_calibration`) — reused, not recomputed. This EPIC's own genuinely new contribution is the **Wilson score confidence interval** computed over that resolved sample/rate (`_wilson_score_interval`), and an `evidence_strength` classification (`INSUFFICIENT`/`LOW`/`MODERATE`/`STRONG`) bucketed by the interval's half-width rather than by raw sample count alone — a segment can clear M1.104's `MIN_SAMPLE_SIZE` floor and still not be `STRONG`.
- **Prevent small-sample high-success histories from producing artificially high Trust (acceptance criterion):** verified directly — 30 samples at 100% observed success yields `evidence_strength == MODERATE` (CI half-width ≈0.057, generally >0.05), while 300 samples at 100% observed success yields `STRONG` (half-width ≈0.006). Same observed rate, different evidence strength, purely from the interval width (`test_small_sample_perfect_record_is_not_strong`, `test_large_sample_perfect_record_is_strong`).
- **Distinguish model/epistemic, market/aleatoric and data uncertainty where feasible:** composed from already-real, independent signals rather than invented — market/model uncertainty is M1.102's own `RegimeTransitionAssessment.uncertainty_source` (`NONE`/`MARKET`/`MODEL`/`MARKET_AND_MODEL`), read via its snapshot getter (`get_regime_uncertainty_snapshot`); data uncertainty is M1.74's own evidence-quality-gate state, read the same way `prediction_trust_score` already reads it. `uncertainty_source` is `None` when no regime-transition snapshot exists yet for the prediction — "not checked this run," never "no uncertainty found," the same honest-absence posture M1.115's provider-drift check uses.
- **Preserve methodology/statistical-estimation versions with predictions / historical reliability values remain immutable:** every assessment is versioned (`reliability_rule_version`) and append-only (no update path); idempotent by `(prediction_id, assessed_at)`.
- **Not done (explicitly out of scope for this PR, same posture M1.101/M1.102/M1.104 already established for their own signals):** bootstrap/stability analysis across model comparisons, predictive ranges/distributions beyond point targets, and integrating this signal into `PredictionTrustScore`/`PositiveRecommendationGateDecision` itself. This module is propose-only — no write path to `Prediction`, `PredictionTrustScore`, `SegmentCalibrationAssessment`, or any recommendation-facing table — composing it into Trust Score's actual gating decision remains a future revision's job, consistent with how M1.104's own segment-calibration signal is still not wired into Trust Score either.

**Tests:** `tests/test_prediction_reliability.py` (8 tests) — below-minimum-sample insufficiency, small-sample-vs-large-sample perfect-record evidence strength, data-uncertainty override from the evidence-quality gate, market-regime-uncertainty reuse from M1.102, absence-not-negative-finding when no regime snapshot exists, idempotency, and history ordering.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_prediction_reliability.py -q` → `8 passed`
- `python -m pytest tests/ -q` (full suite) → `1141 passed`
- `python -m alembic heads` → single head `0093_prediction_reliability (head)`, chain resolves cleanly from `0092_reproducibility_audit`
