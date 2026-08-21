# EPIC-M1.77 — Prediction Trust Score Engine

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_READY
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
