# EPIC-M1.26 — Market Regime Detection

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1

## Objective
Classify the market environment at recommendation time so performance can be measured by regime and future scoring can use regime-aware evidence.

## Scope
- Define deterministic market-regime categories.
- Calculate regime from information available at `as_of_timestamp` only.
- Persist regime and regime version with recommendation context.
- Support historical replay without future-data leakage.
- Add deterministic tests for each regime and boundary.

## Non-goals
- Changing recommendation scores.
- Automatic model promotion.
- Trading decisions.

## Acceptance Criteria
- Every recommendation can be associated with a regime when sufficient data exists.
- Regime classification is reproducible for the same inputs.
- No future data is used.
- Regime version is traceable.
- Historical replay produces the same regime for the same historical timestamp.

## Dependency Chain
**Previous:** M1.15, M1.21, M1.24  
**Next:** M1.27, M1.29

## Completion Report
`docs/epics/EPIC-M1.26-market-regime-detection.md`
