# EPIC-M1.7 — Watchlist Positive-Sensus Evaluation

**Status:** APPROVED
**Priority:** P1

## Objective

Allow a user-provided stock to be thoroughly evaluated against the positive-recommendation criteria without forcing a recommendation.

## Dependencies

- M1.3 — Yahoo NSE Historical Data Provider
- M1.5 — Evaluate Recommendation Outcomes

## Scope

1. Accept a configured stock as a watchlist candidate.
2. Run the same positive-opportunity evaluation used for discovered candidates.
3. Promote the stock to a positive recommendation only when all required criteria are satisfied.
4. Otherwise place it in backlog with the explicit reason: `NOT MATCHING POSITIVE CONSENSUS`.
5. Record which required criteria failed.
6. Allow later re-evaluation when new market data is available.

## Acceptance Criteria

- [ ] A user-provided stock can be evaluated independently of market-wide discovery.
- [ ] The same objective positive criteria are applied.
- [ ] A qualifying stock becomes a positive recommendation candidate.
- [ ] A non-qualifying stock enters backlog rather than receiving a negative recommendation.
- [ ] Backlog records explain the failed criteria.
- [ ] Re-evaluation does not overwrite prior evaluations.
- [ ] Tests cover qualifying and non-qualifying watchlist stocks.

## Non-goals

- Sell/negative recommendations.
- Portfolio management.
- Autonomous trading.
- UI/dashboard work.
