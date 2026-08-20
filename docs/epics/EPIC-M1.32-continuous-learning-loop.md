# EPIC-M1.32 — Continuous Learning Loop

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1

## Objective
Connect discovery, recommendation outcomes, learning, evaluation, calibration, and controlled model promotion into a repeatable continuous-learning cycle.

## Scope
- Trigger learning/evaluation after sufficient new outcomes accumulate.
- Refresh discovery effectiveness metrics.
- Refresh score calibration candidates.
- Evaluate candidate models against the production baseline.
- Invoke the M1.31 promotion gate.
- Keep production model/version stable when evidence is insufficient.
- Record every learning cycle, decision, and resulting version.
- Make the cycle resumable and idempotent.

## Non-goals
- Autonomous trading.
- Unbounded self-modification.
- Rewriting historical recommendations.
- Promoting a model without the M1.31 evidence gate.

## Acceptance Criteria
- The learning cycle can run repeatedly without duplicate effects.
- Insufficient new data results in no promotion and an explicit reason.
- Every promoted model has traceable evaluation evidence.
- Failed candidates remain available for analysis.
- Historical recommendations remain immutable.
- The system can report what changed between learning cycles.

## Dependency Chain
**Previous:** M1.28, M1.29, M1.30, M1.31  
**Next:** Future discovery/scoring improvements based on measured evidence.

## Completion Report
`docs/epics/EPIC-M1.32-continuous-learning-loop.md`
