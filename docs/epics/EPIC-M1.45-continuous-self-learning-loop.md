# EPIC-M1.45 — Continuous Self-Learning Loop

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Connect discovery, recommendation outcomes, learning, evaluation, and safe model promotion into a controlled continuous improvement loop.

## Scope
- Schedule learning-data refresh.
- Detect when sufficient new outcomes are available.
- Rebuild/version the learning dataset.
- Evaluate candidate scoring/model changes.
- Invoke the M1.44 promotion gate.
- Promote only approved candidates.
- Keep the current model when evidence is insufficient.
- Trigger renewed discovery using the active model.
- Preserve a complete lineage from recommendation to model version.

## Acceptance Criteria
- [ ] The loop runs without manual intervention once enabled.
- [ ] No model changes occur without the promotion gate.
- [ ] Insufficient evidence causes no change.
- [ ] Every learning cycle has a unique version and audit record.
- [ ] Active model changes are traceable to comparison evidence.
- [ ] Historical recommendations remain immutable.
- [ ] Failed learning cycles do not stop ordinary recommendation tracking.
- [ ] The system can resume safely after interruption.

## Non-goals
- Autonomous trading.
- Guaranteed improvement.
- Deleting poor historical recommendations.
- Using future information for past predictions.

## Dependencies
**Previous:** M1.44, M1.45 prerequisites M1.33–M1.44
**Next:** Future M2 learning capabilities

## Completion Report
Claude must document the complete loop, scheduling/trigger rules, failure recovery, model lineage, promotion evidence, and end-to-end validation.
