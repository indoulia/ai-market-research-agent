# EPIC-M1.75 — Short-Horizon Probability & Outcome Distribution

**Status:** READY_FOR_APPROVAL
**Execution Status:** BLOCKED_PENDING_APPROVAL
**Priority:** P0

## Objective
Improve short-term investment decisions by estimating probability and outcome distributions for the supported 1–7 trading-day horizons instead of relying primarily on a single score/confidence value.

## Scope
- Model horizon-specific probability of positive return.
- Estimate probability of reaching target and stop loss where sufficient historical evidence exists.
- Preserve expected return, downside and reward/risk distributions.
- Calibrate probabilities using the existing M1.23/M1.29/M1.49/M1.50 framework.
- Segment performance by horizon, regime and relevant discovery/market segments when sample sizes permit.
- Preserve raw and calibrated values separately.
- Explicitly report insufficient evidence.
- Validate candidates out-of-sample before production use.

## Acceptance Criteria
- 1, 2, 3, 5 and 7 trading-day horizons can be evaluated independently where data permits.
- Probability outputs are calibrated and accompanied by confidence quality.
- Target/SL probabilities reconcile with stored target/SL methodology.
- No future information enters training or evaluation.
- Insufficient evidence prevents false precision.

## Dependency Chain
**Previous:** M1.74 Evidence Completeness & Point-in-Time Data Quality + M1.47 Target & Stop-Loss Engine + M1.49/M1.50 Confidence Calibration.
**Next:** M1.76 Generic Stock Analysis.

## Execution Rule
Do not replace the existing score with probabilities until out-of-sample evidence demonstrates that the new representation adds predictive value.
