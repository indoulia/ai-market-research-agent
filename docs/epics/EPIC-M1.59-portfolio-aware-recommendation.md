# EPIC-M1.59 — Portfolio-Aware Recommendation

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Make recommendations aware of existing user holdings and active recommendations without changing the underlying opportunity score.

## Scope
- Represent current holdings and active recommendation exposure.
- Detect sector and correlated-stock concentration.
- Identify duplicate or highly correlated opportunities.
- Explain portfolio-level conflicts.
- Keep recommendation quality separate from allocation decisions.

## Acceptance Criteria
- Portfolio exposure is computed deterministically.
- Concentration/conflict warnings are reproducible.
- Recommendations remain individually auditable.
- No automatic trading or allocation is performed.

## Dependencies
Previous: M1.58.
Next: M1.60.

## Completion Report
Update this EPIC with final implementation evidence before merge.
