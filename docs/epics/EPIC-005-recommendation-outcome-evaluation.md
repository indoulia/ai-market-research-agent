# EPIC-005 — Evaluate Recommendation Outcomes

**Status:** DONE
**Priority:** P1

## Objective

Automatically determine whether each completed positive recommendation succeeded using its predefined horizon and objective market-price outcome rule.

## Dependencies

- EPIC-004 — Persist Recommendation History

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

## Completion Report

### Status
IMPLEMENTED

### EPIC
EPIC-005

### Parent EPIC
None.

### Pull Request
PR #14

### Branch
autonomous/epic-m1-5

### Implementation Commit
8f29e02

### Objective
Deterministically evaluate completed recommendations at their predefined 1/3/5/7 trading-day horizon and classify outcomes without modifying the original recommendation.

### Implemented
- Extended `PredictionOutcome` with `actual_return` and `prediction_error`.
- Added deterministic horizon evaluation with SUCCESS/FAILURE/UNEVALUABLE classification.
- Preserved original recommendation fields; only status transitions to EVALUATED.
- Added 14 focused outcome tests covering horizons and edge cases.
- Renumbered the migration to `0007_outcome_actual_return` so it follows the merged EPIC-012 migration `0006_predictions_trigger`.

### Files Changed
- `app/models.py`
- `app/outcomes.py`
- `migrations/versions/0007_outcome_actual_return.py`
- `tests/test_outcome_evaluation.py`
- `docs/M1-STATUS.md`
- This EPIC report

### Tests Executed
- `pytest -q` — previously 34 passed on the implementation branch before migration renumbering.
- `python -m compileall -q app scripts tests migrations` — previously passed.
- `git diff --check` — previously passed.
- Migration upgrade/downgrade was previously validated; the migration was subsequently renumbered from 0006 to 0007 with `down_revision=0006_predictions_trigger` to follow merged main.

### Validation
The implementation logic and tests were reviewed. The migration-numbering collision with EPIC-012 has been corrected to a linear Alembic chain.

### Known Limitations
- No batch/scheduled evaluator is included; this EPIC implements the per-recommendation evaluation primitive.
- The pre-existing broken `0003_market_price_dedupe` migration remains outside this EPIC's scope.

### Unexpected Findings
- Alembic migration revisions must remain within the repository's 32-character version column constraint.
- EPIC-012 merged `0006_predictions_trigger`, so this EPIC's migration must be `0007` and depend on that revision.

### Recommended Follow-up
- EPIC-006 — positive-recommendation performance reporting.
- A future batch evaluator may call this primitive for all eligible OPEN recommendations.

### Claude Assessment
Implementation is complete against the EPIC acceptance criteria, subject to final strict review.

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
