# EPIC-M1.62 — Recommendation Revalidation Engine

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Automatically determine whether an active recommendation remains valid after material market, news, event, or model changes.

## Scope
- Detect material changes in recommendation inputs.
- Revalidate active recommendations.
- Produce UNCHANGED, UPDATED, WITHDRAWN, or EXPIRED outcomes.
- Preserve every prior recommendation version.
- Record the exact revalidation reason and evidence timestamp.

## Acceptance Criteria
- Revalidation is deterministic and idempotent.
- Material invalidation cannot leave a stale recommendation active.
- Historical versions remain immutable.
- Tests cover target/SL proximity, horizon expiry, data changes, and model changes.

## Dependencies
Previous: M1.61.
Next: M1.63.

## Completion Report
Update this EPIC with final implementation evidence before merge.
