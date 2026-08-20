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

## Dependency Chain

### Previous / Required
- **M1.6 — Positive Recommendation Performance Report** — provides the historical performance calculations.
- **M1.15 — Recommendation Lifecycle & Outcome Scheduler** — provides completed lifecycle/outcome data.

### Next / Unlocks
- **Future self-learning/calibration EPICs** — may use the trust report as evidence, but must be separately defined and approved.

### Chain Position

`M1.8 + M1.9 + M1.10 + M1.12 → M1.13 → M1.14 → M1.15 → M1.16`

M1.11 (Calibration Feedback Loop) may consume the same outcome/performance evidence and should be coordinated with M1.16 rather than treated as an implicit dependency.

### Execution Rule

Do not treat a recommendation as trustworthy merely because the report exists. Every statistic must expose sample size and preserve failures/unevaluable cases. Do not proceed to future self-learning work based on insufficient evidence.

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
