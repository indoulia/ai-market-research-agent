# EPIC-M1.29 — Adaptive Score Calibration

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1

## Objective
Use completed recommendation outcomes to measure and calibrate score/probability reliability without changing the production scoring model automatically.

## Scope
- Compare predicted probability/score bands with observed success.
- Calculate calibration error by horizon and regime.
- Detect persistent over-confidence or under-confidence.
- Produce a versioned calibration candidate.
- Preserve original recommendation scores unchanged.

## Non-goals
- Automatic production model replacement.
- Backfilling scores on historical recommendations.
- Trading decisions.

## Acceptance Criteria
- Calibration uses only closed outcomes.
- Historical scores remain immutable.
- Calibration results are reproducible and versioned.
- Minimum sample thresholds are enforced.
- Candidate calibration can be compared with current calibration out-of-sample.

## Dependency Chain
**Previous:** M1.22, M1.23, M1.26, M1.27  
**Next:** M1.30, M1.31

## Completion Report
`docs/epics/EPIC-M1.29-adaptive-score-calibration.md`
