# EPIC-107 — Stock-Specific Behavior Learning

**Status:** DONE
**Execution Status:** COMPLETED
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
EPIC-084, EPIC-104, EPIC-105.

## Completion Report

**Status:** DONE — merged to main via PR #173 (`26471d6`).

**Implementation:**
- `app/stock_behavior_learning.py`: a new, versioned (`STOCK_BEHAVIOR_VERSION = "SBL-001"`) module.
- **Track stock-level prediction outcomes by horizon and regime / hierarchical fallback for insufficient samples:** `assess_stock_behavior` walks `STOCK_HORIZON_REGIME -> STOCK_HORIZON -> STOCK_ONLY -> GLOBAL_HORIZON_REGIME -> GLOBAL`, the same fallback pattern EPIC-104 already established for calibration, stopping at the first level reaching `MIN_SAMPLE_SIZE_FOR_COMPARISON`. `GLOBAL_HORIZON_REGIME` is a pure read of EPIC-084's already-computed `HorizonRegimeTrust` — never recomputed.
- **Learn recurring response characteristics and reliability:** `observed_success_rate` at the resolved level, `verdict` `MEASURED`/`INSUFFICIENT_SAMPLE`, with the full `fallback_chain` persisted for auditability.
- **Keep personal preferences separate from global stock behavior:** holds structurally — this module has no import from `app.user_preferences`, `app.feedback_learning_signals`, or `app.recommendation_feedback` at all.
- **Feed stock-specific evidence into Trust Score and ranking:** propose-only — no write path to `Prediction`, `PredictionTrustScore`, or any ranking table; wiring remains a future revision's job, the same posture EPIC-101-M1.106 established.
- New immutable table `stock_behavior_assessments` (migration `0082_stock_behavior_learning.py`), idempotent by `(stock_id, model_version, horizon_days, regime, evaluated_at)`.

**Tests:** `tests/test_stock_behavior_learning.py` (6 tests) — resolves to the most specific level with sufficient sample; falls back past a sparse regime to stock+horizon; falls back to EPIC-084's global horizon+regime trust; falls all the way back to global when nothing is sufficient; a `None` regime correctly skips both regime-specific fallback levels; idempotency.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_stock_behavior_learning.py -q` → `6 passed`
- `python -m pytest -q` (full suite) → `1024 passed`
- `python -m alembic heads` → single head `0082_stock_behavior (head)`, chain resolves cleanly
