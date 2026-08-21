# EPIC-M1.141 — User Feedback & Preferences

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Allow users to control recommendation preferences and provide structured feedback that becomes an auditable learning signal without directly changing production models.

## UI Scope
- Default horizon preference with short-term default (1–7 trading days).
- Market/sector/size preferences.
- Recommendation display preferences.
- Simple useful/not-useful feedback.
- Structured feedback reasons.
- Optional free-text note.
- Feedback history.
- Clear statement that feedback enters controlled learning, not immediate model mutation.

## API Contract
`GET /api/v1/preferences`
`PUT /api/v1/preferences`
`POST /api/v1/recommendations/{recommendationId}/feedback`
`GET /api/v1/feedback/history`

Preference model:
`defaultHorizon`, `markets[]`, `sectors[]`, `industries[]`, `marketCaps[]`, `minTrust`, `notificationPreferences`.

Feedback model:
`feedbackId`, `recommendationId`, `predictionVersionId`, `rating`, `reasonCode`, `note`, `createdAt`.

## Acceptance Criteria
- User preferences affect selection/presentation, not global prediction truth.
- Feedback is immutable after submission.
- Duplicate accidental submissions are handled idempotently.
- Feedback always references the exact prediction version.
- Unsafe model controls are not exposed to ordinary users.
