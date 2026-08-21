# EPIC-M1.141 — Feedback, Preferences & Learning Boundary API

**Track:** API
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Expose user preferences and manual feedback without allowing individual user behavior to corrupt global prediction truth. Feedback becomes an auditable learning signal, not an immediate model mutation.

## Contracts
`GET /api/v1/preferences`

Response: `defaultHorizon,markets,sectors,industries,marketCapBuckets,watchlist,notificationPreferences,displayPreferences`.

`PUT /api/v1/preferences`

Request uses the same fields with server-side validation and versioning.

`POST /api/v1/recommendations/{id}/feedback`

Request: `{ "type": "useful|not_useful|target_realistic|target_too_high|target_too_low|reason", "comment": "optional", "predictionVersion": "..." }`

Response: `{ "feedbackId": "...", "accepted": true, "recordedAt": "...", "learningImpact": "queued|informational" }`

## Rules
- Feedback is immutable after submission; corrections create a new record.
- Feedback must reference a prediction version.
- User preference changes affect selection/presentation policy, not historical prediction truth.
- Feedback never directly updates a production model.
- Learning impact is queued for the controlled learning pipeline.

## Acceptance Criteria
- API validates allowed feedback types.
- Duplicate submissions are idempotent where client request ID is reused.
- Feedback is auditable and versioned.
- User-specific preferences are isolated from global model training unless explicitly aggregated through governed learning.
- Contract tests cover invalid, stale-version and duplicate feedback.

## Parallelization
API implementation. UI M1.142 consumes this exact contract.

## Dependencies
M1.132, M1.88, M1.130, M1.110.
