# EPIC-M1.30 — Candidate Model Evaluation

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_STARTED  
**Priority:** P1

## Objective
Evaluate a candidate scoring/prediction model against the current production model using strictly time-separated historical data.

## Scope
- Define reproducible temporal train/evaluation windows.
- Run candidate and current models on identical unseen evaluation periods.
- Compare success rate, return, calibration, and horizon performance.
- Segment results by regime, sector, market-cap, and discovery source.
- Produce a deterministic comparison report.

## Non-goals
- Production model replacement.
- Live trading.
- Training on future evaluation data.

## Acceptance Criteria
- Evaluation data is strictly out-of-sample.
- Candidate and baseline use identical evaluation inputs.
- Metrics are directly comparable.
- Statistical/sample limitations are disclosed.
- Evaluation produces a versioned, auditable result.

## Dependency Chain
**Previous:** M1.24, M1.25, M1.27, M1.28, M1.29  
**Next:** M1.31

## Completion Report
`docs/epics/EPIC-M1.30-candidate-model-evaluation.md`
