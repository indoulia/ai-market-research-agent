# EPIC-M1.54 — Evidence Freshness & Revalidation

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.35, M1.48

## Objective
Ensure recommendation evidence remains fresh enough for the selected horizon and automatically identify recommendations that require revalidation.

## Scope
- Freshness rules by evidence category.
- Horizon-aware freshness thresholds.
- Detect stale, missing, conflicting, and changed information.
- Trigger revalidation when material evidence changes.
- Record revalidation reason and result.

## Acceptance Criteria
- Each evidence category has an explicit freshness policy.
- Freshness is evaluated relative to recommendation horizon.
- Material changes trigger revalidation.
- Stale evidence is visible to users and downstream scoring.
- Revalidation never silently mutates the original snapshot.
- Tests cover fresh, stale, changed, and unavailable evidence.

## Dependency Chain
M1.35/M1.48 → M1.54 → M1.55

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->
