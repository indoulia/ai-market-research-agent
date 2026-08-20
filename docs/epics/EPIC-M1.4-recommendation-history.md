# EPIC-M1.4 — Persist Recommendation History

**Status:** APPROVED
**Priority:** P1
**Owner:** Engineering Orchestrator

## Objective

Persist every positive recommendation exactly as issued so its original prediction can be evaluated later and never retrospectively changed.

## Dependencies

- M1.3 — Yahoo NSE Historical Data Provider

## Scope

1. Add a persistent recommendation-history record linked to the stock and prediction/model version.
2. Store recommendation ID, symbol, generated timestamp, entry price, horizon (1/3/5/7 trading days), expected return, probability of positive return, confidence, and model/version metadata.
3. Preserve the original recommendation as immutable historical evidence.
4. Add query support for recommendation history.
5. Add focused persistence and immutability tests using local fixtures/database test infrastructure already present in the repository.
6. Keep the design ready for a later outcome record without implementing outcome evaluation in this EPIC.

## Acceptance Criteria

- [ ] Every positive recommendation receives a unique persistent ID.
- [ ] Original recommendation fields are persisted completely.
- [ ] Historical recommendation records cannot be silently overwritten after creation.
- [ ] Recommendation history can be queried by symbol and time range.
- [ ] Tests verify persistence and immutability.
- [ ] No UI/dashboard work is required.
- [ ] No outcome-success calculation is included; that belongs to M1.5.

## Non-goals

- Recommendation generation/model changes.
- Outcome evaluation.
- Performance reporting.
- Watchlist workflow.
- UI/dashboard work.
