# EPIC-M1.128 — Market Microstructure & Liquidity Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Improve short-horizon recommendation quality by incorporating liquidity, tradability, spread, volume, price-band and gap behavior into opportunity quality and realistic outcome evaluation.

## Scope
- Track liquidity and turnover metrics.
- Track spread where available.
- Measure unusual volume and liquidity regime changes.
- Detect price-band/circuit constraints.
- Measure gap frequency and gap magnitude.
- Incorporate tradability into recommendation utility and execution realism.
- Preserve microstructure snapshots used by predictions.
- Segment prediction performance by liquidity bucket.

## Acceptance Criteria
- Illiquid candidates can be identified before recommendation.
- Microstructure conditions can affect opportunity utility without changing raw model probability.
- Historical microstructure features are point-in-time safe.
- Execution-cost estimates can consume microstructure evidence.
- Prediction performance can be compared across liquidity segments.

## Dependencies
M1.98, M1.99, M1.96, M1.121.
