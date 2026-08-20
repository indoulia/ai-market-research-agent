# EPIC-M1.58 — Position Risk Assessment

Status: READY_FOR_APPROVAL
Execution Status: NOT_READY

## Objective
Quantify recommendation-level downside, reward/risk, and volatility-adjusted risk so users can understand risk before acting.

## Scope
- Calculate risk from reference price to stop loss.
- Calculate reward from reference price to target.
- Calculate reward/risk ratio.
- Validate target, stop loss, upside, and horizon consistency.
- Preserve calculation/version metadata.
- Do not provide portfolio allocation advice in this EPIC.

## Acceptance Criteria
- Risk calculations are deterministic and auditable.
- Invalid target/SL combinations are rejected.
- Published recommendations expose risk metrics.
- Historical recommendations retain their original risk snapshot.
- Tests cover boundaries and invalid inputs.

## Dependencies
Previous: M1.47.
Next: M1.59.

## Completion Report
Update this EPIC with final implementation evidence before merge.
