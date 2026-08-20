# EPIC-M1.52 — Structured User Feedback

**Status:** READY_FOR_APPROVAL  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.51

## Objective
Allow users to provide structured feedback on recommendation quality without treating opinion as objective outcome truth.

## Scope
- Feedback on target, SL, confidence, market context, news/events, fundamentals, and overall recommendation.
- Pre-outcome and post-outcome feedback.
- Structured reason codes plus optional comment.
- Feedback timestamp and recommendation/model version.
- Immutable feedback records.

## Acceptance Criteria
- User can submit structured feedback for a recommendation.
- Feedback is linked to the exact recommendation version.
- Feedback cannot overwrite objective outcomes.
- Multiple feedback events are retained.
- Feedback can be queried for later analysis.
- Tests cover validation, persistence, duplicates, and historical immutability.

## Dependency Chain
M1.51 → M1.52 → M1.53

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->
