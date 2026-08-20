# EPIC-M1.15 — Recommendation Lifecycle & Outcome Scheduler

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
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

## Dependency Chain

### Previous / Required
- **M1.5 — Evaluate Recommendation Outcomes** — provides the objective outcome-evaluation contract.
- **M1.10 — Positive Horizon Selection** — provides the intended trading-day horizon.
- **M1.13 — Positive Recommendation Generator** — provides issued recommendations to track.
- **M1.14 — Recommendation Selection & Daily Limit** — provides the selected recommendation set.

### Next / Unlocks
- **M1.16 — Recommendation Trust Report** — consumes the completed lifecycle/outcome history.

### Chain Position

`M1.8 + M1.9 + M1.10 + M1.12 → M1.13 → M1.14 → M1.15 → M1.16`

M1.17 remains a discovery branch from M1.8/M1.13 and does not block this lifecycle chain.

### Execution Rule

Do not execute M1.16 until M1.15 is implemented, reviewed, and merged. Do not change issued recommendations to make lifecycle evaluation easier.

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
