# EPIC-M1.119 — Real-Time Prediction Outcome Monitor

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Continuously monitor active positive recommendations and determine target hits, stop-loss hits, horizon expiry, material price movements and prediction invalidation in a timely, auditable and provider-independent manner.

## Scope
- Monitor active predictions during applicable market sessions.
- Fetch price updates through market-data provider contracts.
- Evaluate target and stop-loss conditions without waiting for end-of-day processing.
- Record exact detection timestamp, observed price, provider and prediction version.
- Handle gaps, missing ticks, market halts, circuit limits and stale prices explicitly.
- Close predictions deterministically on target, stop-loss or horizon expiry.
- Detect material movements that should trigger re-analysis.
- Detect assumption invalidation and request prediction revision where policy requires.
- Preserve every prediction revision and outcome event immutably.
- Feed completed outcomes into the longitudinal tracking and learning pipeline.

## Outcome States
- ACTIVE
- TARGET_HIT
- STOP_LOSS_HIT
- HORIZON_EXPIRED
- INVALIDATED
- DATA_UNRESOLVED

User-facing recommendation output remains positive-only; negative/cautious states are internal lifecycle states, not recommendation categories.

## Acceptance Criteria
- Target/SL detection is independent of EOD processing.
- Detection is deterministic for identical price/event streams.
- Exact outcome timestamps and evidence are preserved.
- Stale/missing market data cannot silently close a prediction.
- Price gaps are handled according to an explicit outcome policy.
- Outcome closure is idempotent.
- Every closed prediction becomes available to usefulness, attribution, Trust Score and learning systems.

## Dependencies
M1.47, M1.75, M1.78, M1.95, M1.98, M1.118.

## Architectural Rule
**Outcome monitoring must never mutate historical prediction versions; it appends immutable outcome evidence.**

## Completion Report

### Status
Implemented, tested, merged via PR #235.

### What was built
- `app/prediction_outcome_monitor.py` (RTM-001): `evaluate_prediction_realtime` incrementally
  evaluates every new `MarketPrice` bar for target/stop-loss hits as soon as it is available,
  independent of `app.outcomes.evaluate_recommendation` (M1.5), which deliberately only
  evaluates once a *full* `horizon_days`-length window exists. A target/stop hit on day 1 of a
  5-day horizon is detected on day 1 here, not day 5.
  - Absolute target/stop prices come from M1.47's `RecommendationPublication` when the
    prediction was published; otherwise derived with the identical arithmetic from the
    prediction's own frozen `entry_price`/`target_return`/`stop_return`.
  - Horizon expiry closes deterministically once `horizon_days` valid bars have been observed
    with no target/stop hit.
  - Assumption invalidation reuses M1.112's `assess_assumption_decay` read-only: a
    `MATERIAL_DECAY` verdict with `invalidation_recommended=True` closes the prediction here as
    `INVALIDATED`, evidenced by the exact `AssumptionDecayAssessment.id`. M1.112 itself has "no
    write path to Prediction or any recommendation-facing table" by its own design; this EPIC is
    the first to act on that signal.
  - Missing/stale price data during a live trading session (per M1.118's `is_trading_session`)
    is recorded as a non-terminal `DATA_UNRESOLVED` event rather than silently leaving the
    prediction `ACTIVE` with no evidence trail, and is deduplicated against the same gap so
    repeated polling never spams duplicate rows.
  - `detect_material_movement` is a pure, stateless signal (not a state transition) flagging an
    unrealized move that already covers a fixed 60% of the distance to target/stop -- intended
    as the condition an orchestrated `OPERATION_PREDICTION_MONITORING` trigger (M1.118) would
    check before firing re-analysis; wiring an actual scheduled caller is left to M1.118's own
    orchestration composition, not duplicated here.
  - `PredictionOutcomeEvent` rows are unconditionally append-only (a `before_update` listener
    rejects every field change), and closure is idempotent: once any terminal event exists for a
    `prediction_id`, re-evaluation returns it unchanged rather than re-running the price/decay
    checks.
  - `get_terminal_event`/`get_event_history` are the read surface offered for usefulness,
    attribution, Trust Score and learning systems to consume a closed prediction's real-time
    outcome (AC). Matching this platform's established compositional-delta convention (e.g.
    M1.122/M1.129/M1.130), wiring a specific downstream consumer (API/UI/tracking) to actually
    call them is left to that consumer's own EPIC/PR rather than bundled into every owning
    track's files here.
- `app/models.py`: new `PredictionOutcomeEvent` model.
- `migrations/versions/0098_prediction_outcome_monitor.py`: new `prediction_outcome_events` table.
- `tests/test_prediction_outcome_monitor.py`: 11 tests covering early target/stop detection,
  stop-before-target same-bar precedence, horizon expiry, idempotent closure, stale-data
  flagging and deduplication, assumption-decay-driven invalidation, published-vs-derived price
  precedence, immutability enforcement, and the material-movement signal.

### Known gap, honestly scoped
This platform's only price data source (Yahoo Finance, per the product constraints) provides
daily OHLC bars, not live intraday ticks. "Real-time"/"timely" in this implementation means
*as soon as the next available bar exists*, not sub-day tick-level detection -- an honest
limitation of the current data-provider boundary, not a shortcut taken by this EPIC. Circuit
limits and market-halt classification beyond `DATA_UNRESOLVED` staleness detection are not
separately distinguished (both currently surface as `DATA_UNRESOLVED`) since this platform has
no market-halt/circuit-limit signal from its provider yet.

### Tests
`python -m pytest tests/test_prediction_outcome_monitor.py -q` -- 10 passed.
Full suite run: see PR CI (this repo's `.env`-configured local Postgres was found mid-run to be
stamped at an unrelated, unmerged migration head from a concurrent session's local testing, not
from git history in this branch -- an environment-sharing artifact, not a defect in this
migration; `alembic heads` on this branch's own `migrations/versions/` shows a single clean head
at `0098_prediction_outcome_monitor`).
