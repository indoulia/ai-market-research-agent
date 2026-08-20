# EPIC-M1.55 — Recommendation Revision & Versioning

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.51, M1.54

## Objective
Allow a live recommendation to be revised when material new information changes the system view while preserving every prior version and its original prediction.

## Scope
- Immutable recommendation versions.
- Revision reason and triggering evidence.
- New target, SL, horizon, score, confidence, and evidence snapshot when revised.
- Version-to-version comparison.
- Clear active version for users.
- Preserve original and previous outcomes/history.

## Acceptance Criteria
- A revision never overwrites a prior recommendation version.
- Every revision has a reason and timestamp.
- Users can see what changed and why.
- Tracking associates outcomes with the correct version.
- Revisions are deterministic and auditable.
- Tests cover multiple revisions and concurrent/duplicate triggers.

## Dependency Chain
M1.51/M1.54 → M1.55 → M1.56

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->
