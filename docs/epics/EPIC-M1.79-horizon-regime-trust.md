# EPIC-M1.79 — Horizon & Regime Specific Trust

> **Note (2026-08-21 QA/integration audit):** This file duplicates
> `EPIC-M1.79-horizon-regime-specific-trust.md`, which is `DONE` with a
> real, verified implementation (`app/horizon_regime_trust.py`). No EPIC
> numbered ≥110 references this file or depends on it as unfinished work.
> Left in place, not deleted/renamed — a human should decide whether to
> formally retire it.

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_READY
**Priority:** P0

## Objective
Make Prediction Trust specific to the conditions in which a prediction is being made, especially 1/2/3/5/7-day horizons and the active market regime.

## Scope
- Maintain trust by horizon.
- Maintain trust by market regime.
- Maintain trust by sector/market-cap where evidence is sufficient.
- Maintain trust by prediction setup/discovery source where sample sizes support it.
- Prevent aggregate historical success from hiding weak segments.
- Select or reduce trust for a recommendation using the relevant segment evidence.
- Preserve segment history over time.

## Acceptance Criteria
- A prediction can show different trust for different horizons.
- Regime-specific reliability is visible.
- Sparse segments are marked insufficient rather than overfit.
- Segment trust updates only from measured outcomes.
- Historical segment trust remains reconstructable.

## Dependency Chain
**Previous:** M1.77, M1.26, M1.27, M1.78.
**Next:** M1.80, M1.84.

## Execution Rule
Never infer high trust for a segment solely from aggregate model performance.
