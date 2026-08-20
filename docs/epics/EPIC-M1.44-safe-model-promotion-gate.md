# EPIC-M1.44 — Safe Model Promotion Gate

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Allow a candidate model to replace the current model only when predefined evidence and safety gates are satisfied.

## Scope
- Define promotion thresholds.
- Require candidate-vs-current comparison evidence.
- Require minimum sample sizes.
- Require no unacceptable regression in critical horizons/segments.
- Require reproducible evaluation artifacts.
- Version active model selection.
- Provide explicit rejection reasons.
- Support rollback to the previous approved model.

## Acceptance Criteria
- [ ] Promotion is impossible without a completed comparison.
- [ ] Minimum evidence thresholds are enforced.
- [ ] Critical regression checks are enforced.
- [ ] Every promotion/rejection is auditable.
- [ ] Active model version is unambiguous.
- [ ] Previous model remains recoverable for rollback.
- [ ] Promotion does not modify historical recommendation results.

## Dependencies
**Previous:** M1.43
**Next:** M1.45

## Completion Report
Claude must document promotion gates, rejection cases, audit evidence, active-version handling, and rollback validation.