# EPIC-M1.60 — Recommendation Allocation Guidance

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Provide optional risk-aware allocation guidance based on user constraints without executing trades.

## Scope
- Define user allocation/risk limits.
- Calculate a suggested allocation range from risk and confidence.
- Respect portfolio and concentration constraints.
- Explain why an allocation is constrained.
- Keep allocation separate from recommendation quality.

## Acceptance Criteria
- Guidance is deterministic and capped by user limits.
- No automatic order execution exists.
- Missing risk information prevents unsafe guidance.
- Tests cover concentration and limit boundaries.

## Dependencies
Previous: M1.59.
Next: M1.61.

## Completion Report
Update this EPIC with final implementation evidence before merge.
