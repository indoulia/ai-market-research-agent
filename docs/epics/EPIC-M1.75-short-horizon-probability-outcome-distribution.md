# EPIC-M1.75 — Short-Horizon Probability & Outcome Distribution

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Extend short-term recommendation outputs from a single score/confidence value into calibrated, horizon-specific outcome probabilities and risk distributions for 1, 2, 3, 5 and 7 trading days.

## Scope
- Produce horizon-specific probability of positive return.
- Estimate probability of reaching target within the selected horizon.
- Estimate probability of reaching stop loss within the selected horizon.
- Estimate expected return and downside distribution where evidence supports it.
- Preserve score, confidence and confidence quality as separate concepts.
- Calibrate outputs against completed historical outcomes.
- Respect M1.74 evidence-quality state.
- Preserve model/version metadata and point-in-time inputs.
- Add deterministic calibration and boundary tests.

## Non-goals
- Automatic trading or position execution.
- Replacing existing score/confidence without validation.
- Presenting unsupported probabilities when samples are insufficient.
- Medium/long-term modeling beyond interfaces required for future horizons.

## Acceptance Criteria
- 1/2/3/5/7-day outputs are independently measurable.
- Probability values are calibrated against historical outcomes.
- Target-hit and stop-loss probabilities are distinguishable.
- Insufficient evidence/sample states are explicit.
- Outputs are reproducible and auditable.
- Existing recommendation contracts remain authoritative.

## Dependency Chain
**Previous:** M1.74 Evidence Completeness & Point-in-Time Data Quality + M1.23 Recommendation Confidence Analysis + M1.47 Target & Stop-Loss Engine.
**Next:** M1.76 Generic Stock Analysis.

## Execution Rule
Never present a probability as calibrated when evidence or sample size is insufficient. Existing score and confidence must remain backward compatible.
