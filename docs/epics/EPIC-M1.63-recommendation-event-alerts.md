# EPIC-M1.63 — Recommendation Event Alerts

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Notify users only when a recommendation or market event requires attention.

## Scope
- Target/SL proximity alerts.
- Recommendation invalidation/revalidation alerts.
- Major news/event alerts.
- Material confidence or market-regime changes.
- New high-confidence opportunity alerts.
- Deduplication and throttling.

## Acceptance Criteria
- Alerts are tied to explicit events.
- Duplicate alerts are suppressed.
- Alert severity is deterministic.
- Users can control alert preferences.
- No recommendation is changed merely because an alert is sent.

## Dependencies
Previous: M1.62.
Next: M1.64.

## Completion Report
Update this EPIC with final implementation evidence before merge.
