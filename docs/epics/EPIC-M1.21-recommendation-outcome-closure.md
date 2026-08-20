# EPIC-M1.21 — Recommendation Outcome Closure

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Approved By:** —  
**Priority:** P1

## Objective
Ensure every eligible issued recommendation reaches an explicit terminal outcome state so historical learning is based on complete, auditable evidence.

## Scope
1. Identify recommendations whose selected horizon is due for closure.
2. Apply objective outcome evaluation using trading-day logic and available market data.
3. Distinguish successful, unsuccessful, and unevaluable outcomes.
4. Record closure timestamp and evaluation metadata.
5. Keep the original recommendation immutable.
6. Make closure idempotent and recoverable.
7. Add tests for all supported horizons and unavailable-data cases.

## Non-goals
- Changing recommendations after issuance.
- Subjective outcome labels.
- Model retraining.
- Trading execution.

## Acceptance Criteria
- [ ] Eligible recommendations reach a terminal outcome exactly once.
- [ ] Outcomes use the intended 1/3/5/7-day horizon.
- [ ] Failures and unevaluable cases remain distinguishable.
- [ ] Original recommendation data is unchanged.
- [ ] Re-running closure does not duplicate outcomes.
- [ ] Tests cover normal and edge cases.

## Dependency Chain
### Previous / Required
- **M1.20 — Watchlist Decision History**
- **M1.15 — Recommendation Lifecycle & Outcome Scheduler**

### Next / Unlocks
- **M1.22 — Recommendation Score Analysis**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Do not fabricate an outcome when required market data is unavailable. Preserve an explicit unevaluable state.

## Completion Report
Update with implementation evidence, tests, PR/merge information, and final status before marking implemented.
