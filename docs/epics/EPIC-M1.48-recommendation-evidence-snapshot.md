# EPIC-M1.48 — Recommendation Evidence Snapshot

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.35, M1.47

## Objective
Capture the evidence that justified a recommendation so users and future learning can see what the system knew when the decision was made.

## Scope
- Fundamental evidence.
- News evidence.
- Event evidence.
- Market and sector evidence.
- Technical/volume evidence.
- Source, timestamp, freshness, and evidence status.
- Recommendation-time immutable snapshot.

## Acceptance Criteria
- Every recommendation records all required evidence categories or an explicit unavailable state.
- Every evidence item has source/reference metadata and timestamp where available.
- Stale evidence is clearly identified.
- Historical snapshots cannot be silently overwritten.
- UI/API can retrieve the complete recommendation evidence snapshot.
- Tests cover missing, stale, and fresh evidence.

## Dependency Chain
M1.35 → M1.48 → M1.49/M1.54+

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->
