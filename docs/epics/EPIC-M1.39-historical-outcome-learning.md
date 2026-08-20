# EPIC-M1.39 — Historical Outcome Learning

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_STARTED
**Priority:** P1

## Objective
Turn completed recommendation history into a clean learning dataset that explains which conditions correlate with successful outcomes.

## Scope
- Build point-in-time-safe learning records.
- Join recommendation features to finalized outcomes.
- Preserve model, score, probability, horizon, market regime, sector, size, and discovery source.
- Prevent future-data leakage.
- Segment historical performance by relevant dimensions.
- Version dataset construction rules.

## Acceptance Criteria
- [ ] Every included record has a known information cutoff.
- [ ] No post-recommendation information enters features.
- [ ] Outcomes are linked deterministically.
- [ ] Dataset construction is reproducible.
- [ ] Dataset versions are immutable.
- [ ] Excluded/incomplete records have explicit reasons.

## Dependencies
**Previous:** M1.38, M1.17
**Next:** M1.40

## Completion Report
Claude must document feature cutoff rules, leakage controls, dataset schema, validation, and sample dataset evidence.