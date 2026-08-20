# EPIC-M1.41 — Market-Regime-Aware Scoring

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_STARTED
**Priority:** P1

## Objective
Make scoring sensitive to measurable market conditions when historical evidence proves that prediction behavior changes across regimes.

## Scope
- Define deterministic market regimes.
- Attach regime at recommendation time.
- Measure score/outcome performance by regime.
- Evaluate regime-specific score adjustments.
- Preserve a regime-neutral baseline for comparison.
- Avoid regime classification using future information.

## Acceptance Criteria
- [ ] Every eligible recommendation has a point-in-time regime classification.
- [ ] Regime definitions are versioned.
- [ ] Regime-specific performance is measurable.
- [ ] Regime-aware scoring is compared against the baseline out-of-sample.
- [ ] No regime adjustment is enabled without evidence.
- [ ] Historical recommendations retain their original regime and score.

## Dependencies
**Previous:** M1.26, M1.40
**Next:** M1.42

## Completion Report
Claude must document regime definitions, leakage controls, comparative results, and whether regime-aware scoring was enabled or rejected.