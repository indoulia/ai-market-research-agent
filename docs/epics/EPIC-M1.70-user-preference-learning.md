# EPIC-M1.70 — User Preference Learning

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Learn stable user preferences from repeated behavior while keeping explicit user settings authoritative.

## Scope
- Observe accepted/rejected recommendation patterns.
- Detect stable preference signals.
- Suggest preference changes to the user.
- Never silently alter explicit user settings.
- Separate personal preference learning from global model learning.

## Acceptance Criteria
- User can inspect why a preference suggestion was generated.
- Minimum evidence thresholds are explicit.
- Explicit settings always override inferred preferences.
- Personal learning cannot modify the global production model.

## Dependencies
Previous: M1.69.
Next: M1.71.

## Completion Report
Update this EPIC with final implementation evidence before merge.
