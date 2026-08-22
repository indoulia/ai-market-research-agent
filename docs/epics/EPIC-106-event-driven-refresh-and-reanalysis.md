# EPIC-106 — Event-Driven Refresh & Reanalysis

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Trigger timely data refresh and prediction re-analysis when material external events occur rather than waiting only for scheduled polling.

## Scope
- Define event triggers for earnings, corporate announcements, major news, price/volume shocks and market-regime changes.
- Route triggers through provider abstractions.
- Apply deduplication and materiality thresholds.
- Revalidate affected predictions.
- Preserve trigger, source and resulting revision history.
- Prevent refresh storms and duplicate recalculations.

## Dependencies
EPIC-077, EPIC-090, EPIC-105.

## Completion Report

**Status:** DONE — merged to main via PR #170 (`d8a384f`).

**Implementation:**
- `app/event_driven_refresh.py`: a new, versioned (`EVENT_TRIGGER_VERSION = "EDR-001"`) module.
- **Define event triggers for earnings, corporate announcements, major news, price/volume shocks and market-regime changes:** `_detect_new_triggers` scans four already-real, provider-populated sources — `NewsEventRecord` (EPIC-077, `MATERIALITY_HIGH` only), `CorporateAction` (EPIC-096, any action), `ScanCandidate` (EPIC-015, a fixed `SHOCK_VOLUME_RATIO_THRESHOLD`/`SHOCK_ATR_PERCENT_THRESHOLD` distinct from and stricter than EPIC-021's own regime-classification threshold), and `RegimeTransitionAssessment` (EPIC-102, `transition_detected` for a scan this stock's own qualified candidacy is linked to).
- **Route triggers through provider abstractions:** every source table is itself populated exclusively through this platform's provider adapters (EPIC-090/EPIC-091) — this module never calls a provider directly.
- **Apply deduplication and materiality thresholds:** a real DB unique constraint on `(event_type, source_table, source_id)` means the exact same underlying record can never create a second trigger; only `HIGH` materiality news qualifies.
- **Revalidate affected predictions:** every still-open prediction on the triggering stock is passed to EPIC-105's `evaluate_prediction_freshness` (reused unchanged).
- **Prevent refresh storms and duplicate recalculations:** before revalidating, each prediction's own freshness history is checked for a decision already made within a fixed `REFRESH_COOLDOWN` (1 hour) of `as_of` — a burst of several qualifying events in that window still produces at most one fresh re-analysis per prediction, proven directly by `test_cooldown_prevents_duplicate_revalidation`.
- **Preserve trigger, source and resulting revision history:** new immutable-after-processing table `event_trigger_records` (migration `0081_event_driven_refresh.py`) records the source table/id, detection time, and every resulting `PredictionFreshnessDecision` id.

**Tests:** `tests/test_event_driven_refresh.py` (7 tests) — major-news trigger and revalidation, low-materiality news correctly not triggering, dedup of the same news record, corporate-action trigger, price/volume-shock trigger, regime-change trigger, and cooldown suppression of a second revalidation burst.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_event_driven_refresh.py -q` → `7 passed`
- `python -m pytest -q` (full suite) → `1018 passed`
- `python -m alembic heads` → single head `0081_event_trigger (head)`, chain resolves cleanly
