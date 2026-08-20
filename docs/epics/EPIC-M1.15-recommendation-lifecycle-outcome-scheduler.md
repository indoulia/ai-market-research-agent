# EPIC-M1.15 — Recommendation Lifecycle & Outcome Scheduler

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P1

## Objective

Automatically track each issued recommendation through its selected 1/3/5/7-day horizon and evaluate its objective outcome without manual intervention.

## Scope

1. Define recommendation lifecycle states from issuance through final evaluation.
2. Schedule/check outcome evaluation for the selected horizon.
3. Persist intermediate evaluation state where needed and a final objective outcome.
4. Ensure each recommendation is evaluated once for its final horizon.
5. Handle weekends, market holidays, missing prices, and unavailable data explicitly.
6. Make processing idempotent and recoverable after interruption.
7. Add tests for each horizon and scheduling edge case.

## Non-goals

- Changing the recommendation after issuance.
- Model retraining.
- Subjective outcome assessment.
- Trading execution.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Every issued recommendation enters a traceable lifecycle.
- [ ] Final evaluation occurs at the intended trading-day horizon.
- [ ] Historical recommendation fields remain immutable.
- [ ] Outcome processing is idempotent.
- [ ] Market holidays/weekends are handled using trading-day logic.
- [ ] Missing data produces an explicit unevaluable state rather than fabricated results.
- [ ] Tests cover 1/3/5/7-day horizons and interruption/retry behavior.

## Dependencies

- M1.5 — Evaluate Recommendation Outcomes
- M1.10 — Positive Horizon Selection
- M1.13 — Positive Recommendation Generator

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
