# EPIC-M1.110 — Prediction Lifecycle & Recommendation Capacity Control

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Manage predictions through a complete immutable lifecycle and limit the user feed to a controlled set of the strongest positive opportunities.

## Scope
- Define CREATED, ACTIVE, REVISED, EXPIRED, TARGET_HIT, SL_HIT, INVALIDATED and EVALUATED states.
- Preserve all state transitions and reasons.
- Prevent duplicate active recommendations for the same opportunity/horizon.
- Define configurable recommendation capacity limits.
- Rank before publication.
- Archive completed predictions without deleting learning history.
- Keep suppressed/negative candidates internal for learning.

## Dependencies
M1.55, M1.78, M1.87, M1.99, M1.105.
