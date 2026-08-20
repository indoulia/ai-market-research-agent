# EPIC-M1.5 — Evaluate Recommendation Outcomes

**Status:** APPROVED
**Priority:** P1

## Objective

Automatically determine whether each completed positive recommendation succeeded using its predefined horizon and objective market-price outcome rule.

## Dependencies

- M1.4 — Persist Recommendation History

## Scope

1. Evaluate completed 1/3/5/7 trading-day recommendations.
2. Capture the objective evaluation price and actual return.
3. Classify each recommendation deterministically as SUCCESS, FAILURE, or UNEVALUABLE.
4. Record predicted versus actual return and prediction error.
5. Ensure the original recommendation remains unchanged.
6. Add focused tests for horizon calculation, market outcomes, and boundary cases.

## Acceptance Criteria

- [ ] Completed recommendations are evaluated at the correct trading-day horizon.
- [ ] Actual return is calculated deterministically.
- [ ] SUCCESS/FAILURE/UNEVALUABLE classification follows a documented rule.
- [ ] Predicted versus actual return is stored.
- [ ] Original recommendation data is immutable.
- [ ] Tests cover all supported horizons and edge cases.

## Non-goals

- Performance dashboards.
- Model retraining.
- Watchlist workflow.
- UI/dashboard work.
