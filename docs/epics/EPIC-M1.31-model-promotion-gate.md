# EPIC-M1.31 — Model Promotion Gate

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_STARTED  
**Priority:** P1

## Objective
Define a hard evidence gate that allows a candidate model to become the production model only when it demonstrably improves on the current model.

## Scope
- Define promotion criteria and minimum sample sizes.
- Require out-of-sample improvement across agreed core metrics.
- Require no unacceptable regression in any critical horizon.
- Record model version, evidence, decision, and approver.
- Make promotion atomic and reversible.
- Retain the previous production model for comparison/rollback.

## Non-goals
- Autonomous trading.
- Promotion based only on training performance.
- Deleting previous model versions.

## Acceptance Criteria
- No candidate becomes production without passing every mandatory gate.
- Promotion decision is reproducible from stored evidence.
- Previous production version remains recoverable.
- Failed candidates are retained as rejected versions with reasons.
- Promotion history is immutable.

## Dependency Chain
**Previous:** M1.25, M1.30  
**Next:** M1.32

## Completion Report
`docs/epics/EPIC-M1.31-model-promotion-gate.md`
