# EPIC-M1.16 — Recommendation Trust Report

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P1

## Objective

Expose the historical truth of recommendation performance so trust is based on evidence rather than claims.

## Scope

1. Report overall success rate with sample count.
2. Report success by 1/3/5/7-day horizon with sample counts.
3. Report predicted versus actual returns.
4. Report average winning and losing returns.
5. Report performance by probability/confidence bucket.
6. Report failures and unevaluable recommendations separately.
7. Identify weak horizons and misleading confidence ranges when sample size supports the comparison.
8. Ensure every statistic is reproducible from persisted recommendation/outcome data.

## Non-goals

- Changing recommendation generation.
- Model retraining.
- Hiding or filtering failures to improve presentation.
- UI/dashboard work beyond the minimum output contract needed for the report.

## Acceptance Criteria

- [ ] Every success percentage includes its sample count.
- [ ] Failures remain visible.
- [ ] Unevaluable recommendations are reported separately.
- [ ] Horizon performance is available for supported horizons.
- [ ] Predicted vs actual return statistics are available.
- [ ] Confidence/probability bucket statistics include sample counts.
- [ ] Insufficient samples are explicitly identified.
- [ ] Tests verify report calculations against known fixtures.

## Dependencies

- M1.6 — Positive Recommendation Performance Report
- M1.15 — Recommendation Lifecycle & Outcome Scheduler

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
