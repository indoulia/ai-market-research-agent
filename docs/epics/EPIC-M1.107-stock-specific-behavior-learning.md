# EPIC-M1.107 — Stock-Specific Behavior Learning

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Learn prediction reliability and recurring behavior at the individual security level without allowing sparse stock history to create false confidence.

## Scope
- Track stock-level prediction outcomes by horizon and regime.
- Learn recurring response characteristics and reliability.
- Use hierarchical/global fallback for insufficient samples.
- Feed stock-specific evidence into Trust Score and ranking.
- Keep personal preferences separate from global stock behavior.

## Dependencies
M1.79, M1.104, M1.105.
