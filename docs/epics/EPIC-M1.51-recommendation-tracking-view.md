# EPIC-M1.51 — Recommendation Tracking View

**Status:** READY_FOR_APPROVAL  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.36, M1.47, M1.48

## Objective
Give users a clear longitudinal view of every active and completed recommendation from publication through outcome.

## Scope
- Entry/reference price.
- Target and stop loss.
- Horizon and elapsed time.
- Current price and return.
- Target/SL progress.
- Confidence and score at publication.
- Evidence snapshot.
- Outcome status and history.

## Acceptance Criteria
- Active recommendations can be tracked over time.
- Historical recommendations remain viewable after completion.
- Original recommendation values are visible beside current state.
- Tracking updates do not rewrite the original recommendation snapshot.
- Users can inspect outcome history by stock, recommendation, horizon, and date.
- Tests cover active, completed, and missing-data states.

## Dependency Chain
M1.36/M1.47/M1.48 → M1.51 → M1.55+

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->
