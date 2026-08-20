# EPIC-M1.6 — Positive Recommendation Performance Report

**Status:** APPROVED
**Priority:** P1

## Objective

Measure the historical performance of positive recommendations using only objectively evaluated outcomes.

## Dependencies

- M1.5 — Evaluate Recommendation Outcomes

## Scope

1. Calculate overall positive-recommendation success rate.
2. Calculate success by 1/3/5/7-day horizon.
3. Report predicted versus actual return.
4. Report average winning and losing return.
5. Report performance by probability/confidence bucket.
6. Always expose the sample size with percentages.
7. Keep failed recommendations visible; do not cherry-pick successes.

## Acceptance Criteria

- [ ] Overall success rate is calculated from evaluated recommendations only.
- [ ] Horizon-specific success rates are available.
- [ ] Predicted versus actual return statistics are available.
- [ ] Probability/confidence bucket performance is available.
- [ ] Every percentage includes its underlying sample count.
- [ ] Unevaluable recommendations are excluded from success-rate denominators and reported separately.
- [ ] Tests verify calculations against known fixtures.

## Non-goals

- Model retraining.
- Recommendation generation changes.
- Watchlist workflow.
- UI/dashboard work.
