# EPIC-M1.38 — Objective Recommendation Outcome Measurement

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_STARTED
**Priority:** P1

## Objective
Determine recommendation success or failure using predefined, immutable outcome rules rather than subjective interpretation.

## Scope
- Define success/failure/neutral/insufficient-data outcomes.
- Calculate realized return at the selected horizon.
- Apply target and loss thresholds consistently.
- Handle price gaps and missing observations explicitly.
- Freeze final outcome after sufficient evidence exists.
- Preserve outcome calculation version.

## Acceptance Criteria
- [ ] Every completed recommendation receives one deterministic outcome state.
- [ ] Outcome rules are versioned.
- [ ] Success/failure cannot be changed without a new versioned evaluation.
- [ ] Missing data never becomes an assumed success/failure.
- [ ] Outcome calculation is reproducible from stored observations.
- [ ] Tests cover boundary conditions.

## Dependencies
**Previous:** M1.36, M1.37
**Next:** M1.39

## Completion Report
Claude must document outcome definitions, formulas, edge cases, tests, and reproducibility evidence.