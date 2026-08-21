# EPIC-M1.140 — Learning & Self-Improvement

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P1

## Objective
Expose MRA's controlled learning process so users can understand what the system learned, what experiments ran and why production behavior changed, without exposing unsafe internal controls.

## UI Scope
- Learning summary.
- Recent learning signals.
- Failure patterns discovered.
- Candidate experiments.
- Champion/challenger status.
- Promotions/rejections.
- Trust impact over time.
- Evidence links and concise explanations.
- Read-only by default.

## API Contract
`GET /api/v1/learning/summary`
`GET /api/v1/learning/history`
`GET /api/v1/learning/experiments`
`GET /api/v1/learning/models`
`GET /api/v1/learning/models/{modelId}`

Responses include:
`id`, `type`, `createdAt`, `status`, `evidenceCount`, `methodologyVersion`, `impact`, `modelVersion`, `decisionReason`.

## Acceptance Criteria
- UI never directly modifies production models.
- Every displayed learning claim links to evidence.
- Promotion/rejection states reconcile with M1.123.
- Historical learning decisions remain immutable.
- User can understand improvement without seeing implementation internals.
