# EPIC-M1.110 — Prediction Lifecycle & Recommendation Capacity Control

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Manage predictions through a complete immutable lifecycle and limit the user feed to a controlled set of the strongest positive opportunities.

## Scope
- Define CREATED, ACTIVE, REVISED, EXPIRED, TARGET_HIT, SL_HIT, INVALIDATED and EVALUATED states.
- Preserve all state transitions and reasons.
- Prevent duplicate active recommendations for the same opportunity/horizon.
- Define configurable recommendation capacity limits.
- Rank before publication.
- Archive completed predictions without deleting learning history.
- Keep suppressed/negative candidates internal for learning.

## Dependencies
M1.55, M1.78, M1.87, M1.99, M1.105.

## Completion Report

**Status:** VALIDATING (implemented, tests passing, PR open)

**Implementation:**
- `app/prediction_lifecycle_capacity.py`: a new, versioned (`LIFECYCLE_CAPACITY_VERSION = "PLC-001"`) module.
- **Define CREATED/ACTIVE/REVISED/EXPIRED/TARGET_HIT/SL_HIT/INVALIDATED/EVALUATED states:** `classify_prediction_lifecycle_state` is a pure, read-only classifier over already-immutable evidence — M1.5's `PredictionOutcome`, M1.55's `RecommendationRevision` history, M1.62's `RecommendationRevalidationOutcome`, and M1.15's own `RecommendationLifecycle` row — in a fixed priority order (closed outcome > revalidation verdict > revision > open lifecycle tracking > `CREATED`). This is the same "derived-classification-never-delete" pattern this platform already uses for retention/archiving/delisting.
- **Preserve all state transitions and reasons:** `snapshot_prediction_lifecycle` persists an immutable row per `(prediction_id, evaluated_at)` recording `previous_state` from the most recent prior snapshot, so a reader can reconstruct every transition without any row ever being mutated.
- **Prevent duplicate active recommendations for the same opportunity/horizon:** `apply_capacity_control` excludes any candidate for a `(stock_id, horizon_days)` pair that already has another prediction currently classified `ACTIVE`.
- **Define configurable recommendation capacity limits / rank before publication:** reads M1.87/M1.99's own already-persisted `PositiveOpportunityRanking` (`included=True`, ordered by `rank_position`) for the scan — never re-ranks — and cuts off at a caller-supplied `capacity_limit` (default `DEFAULT_CAPACITY_LIMIT = 10`).
- **Archive completed predictions without deleting learning history / keep suppressed/negative candidates internal for learning:** holds structurally — no write path to `Prediction`, `RecommendationSelection`, or any recommendation-facing table; an excluded or non-`ACTIVE` prediction is never deleted, only classified.
- New immutable tables `prediction_lifecycle_snapshots` and `capacity_control_decisions` (migration `0085_prediction_lifecycle_capacity.py`), both idempotent by `(prediction_id, evaluated_at)`.

**Tests:** `tests/test_prediction_lifecycle_capacity.py` (13 tests) — all eight lifecycle states individually verified, a real state transition captured with correct `previous_state`, snapshot idempotency, capacity control selecting the top-ranked within a limit, duplicate-active-opportunity exclusion, and capacity-decision idempotency.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_prediction_lifecycle_capacity.py -q` → `13 passed`
- `python -m pytest -q` (full suite) → `1063 passed`
- `python -m alembic heads` → single head `0085_lifecycle_capacity (head)`, chain resolves cleanly
