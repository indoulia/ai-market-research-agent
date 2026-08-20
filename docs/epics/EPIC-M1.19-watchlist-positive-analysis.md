# EPIC-M1.19 — Watchlist Positive Analysis

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
**Priority:** P1

## Objective
Evaluate active watchlist stocks through the existing quantitative prediction, consensus, scoring, and horizon pipeline without creating a recommendation merely because a stock is watched.

## Scope
1. Evaluate active watchlist symbols using point-in-time market/model data.
2. Reuse the existing positive-consensus contract.
3. Reuse the existing opportunity score.
4. Reuse supported 1/3/5/7-day horizon selection.
5. Record qualification and non-qualification reasons.
6. Persist analysis timestamp and relevant model/data versions.
7. Make repeated analysis idempotent for the same watchlist evaluation context.

## Non-goals
- Issuing a recommendation solely from watchlist membership.
- Changing consensus, scoring, or horizon rules.
- Trading automation.
- Outcome learning.

## Acceptance Criteria
- [ ] Watchlist candidates use the same quantitative path as normal candidates.
- [ ] Watchlist membership cannot bypass qualification.
- [ ] Qualification and rejection reasons are traceable.
- [ ] Point-in-time data/model versions are retained.
- [ ] Duplicate evaluations are prevented.
- [ ] Tests cover positive, rejected, stale-data, and duplicate cases.

## Dependency Chain
### Previous / Required
- **M1.18 — Watchlist Intake**
- **M1.8 — Positive Consensus Engine**
- **M1.9 — Positive Opportunity Scoring**
- **M1.10 — Positive Horizon Selection**
- **M1.13 — Positive Recommendation Generator**

### Next / Unlocks
- **M1.20 — Watchlist Decision History**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Do not create a recommendation from watchlist membership alone. All positive qualification must pass the existing deterministic contracts.

## Completion Report
Update with implementation evidence, tests, PR/merge information, and final status before marking implemented.
