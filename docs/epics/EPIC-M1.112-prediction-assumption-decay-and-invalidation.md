# EPIC-M1.112 — Prediction Assumption Decay & Invalidation

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Automatically detect when the assumptions behind an active prediction have materially decayed or broken and remove it from the user feed without exposing negative/cautious recommendations.

## Scope
- Track assumptions supporting each prediction.
- Define assumption freshness/decay rules.
- Detect material contradiction or thesis break.
- Trigger revalidation or invalidation.
- Preserve original and revised prediction history.
- Feed invalidation outcomes into learning.

## Dependencies
M1.65, M1.105, M1.106, M1.110.
