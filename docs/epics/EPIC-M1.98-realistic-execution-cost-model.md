# EPIC-M1.98 — Realistic Execution & Cost Model

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Measure prediction usefulness using economically realistic entry/exit assumptions rather than idealized prices.

## Scope
- Model spread, slippage, liquidity and transaction costs where data supports them.
- Handle gaps, circuit limits and unavailable execution prices.
- Define realistic entry and exit timestamps.
- Preserve gross and net outcome metrics separately.
- Apply realistic assumptions consistently in backtests and outcome evaluation.
- Keep recommendation output advisory; do not execute trades.
- Add sensitivity analysis for execution assumptions.

## Acceptance Criteria
- Backtest outcomes can be evaluated on gross and realistic net basis.
- Illiquid or unexecutable scenarios are explicitly identified.
- Execution assumptions are versioned.
- Historical outcomes remain reproducible.
- Trust/usefulness metrics can consume realistic outcomes.

## Dependencies
Previous: M1.95, M1.96, M1.97.
Next: M1.99.
