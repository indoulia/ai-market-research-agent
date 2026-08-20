# EPIC-M1.20 — Watchlist Decision History

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
**Priority:** P1

## Objective
Persist the historical decisions produced from watchlist analysis so users and later learning stages can distinguish observation, qualification, recommendation, and rejection over time.

## Scope
1. Persist each watchlist evaluation with timestamp and symbol.
2. Record qualification outcome and reason codes.
3. Link a qualifying evaluation to its recommendation generation where one exists.
4. Preserve model, score, horizon, data, and rule versions used for the decision.
5. Keep historical decisions immutable.
6. Support deterministic history queries by symbol and time range.
7. Add persistence and immutability tests.

## Non-goals
- Changing recommendation decisions.
- Retrospective score modification.
- Learning/model training.
- UI/dashboard work.

## Acceptance Criteria
- [ ] Every completed watchlist evaluation has an auditable history record.
- [ ] Qualification and rejection states are distinguishable.
- [ ] Recommendation linkage is traceable when applicable.
- [ ] Historical records remain immutable.
- [ ] Version metadata is preserved.
- [ ] History queries are deterministic.

## Dependency Chain
### Previous / Required
- **M1.19 — Watchlist Positive Analysis**

### Next / Unlocks
- **M1.21 — Recommendation Outcome Closure**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
History is evidence. Do not rewrite historical decisions to reflect later model or score changes.

## Completion Report
Update with implementation evidence, tests, PR/merge information, and final status before marking implemented.
