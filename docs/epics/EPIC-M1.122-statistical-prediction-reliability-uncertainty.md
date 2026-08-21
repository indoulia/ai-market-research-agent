# EPIC-M1.122 — Statistical Prediction Reliability & Uncertainty

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
