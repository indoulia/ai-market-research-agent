# EPIC-M1.66 — Recommendation Decision Trace

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Make every recommendation reproducible from its exact inputs, evidence, rules, model, score, target, SL, and confidence versions.

## Scope
- Capture input feature snapshot.
- Capture evidence sources and timestamps.
- Capture scoring and confidence versions.
- Capture target/SL methodology.
- Capture qualification and rejection reasons.
- Provide a deterministic decision trace.

## Acceptance Criteria
- A historical recommendation can be reconstructed without current data.
- Every material decision has an explicit reason.
- Trace data is immutable.
- Trace output is suitable for debugging and user explanation.

## Dependencies
Previous: M1.65.
Next: M1.67.

## Completion Report
Update this EPIC with final implementation evidence before merge.
