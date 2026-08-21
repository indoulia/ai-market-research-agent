# EPIC-M1.128 — Market Microstructure & Liquidity Intelligence

**Status:** DONE
**Execution Status:** COMPLETE
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

## Implementation

**Status:** DONE — merged to main via PR #249 (`68606eb`).

`app/microstructure_liquidity.py` reuses `discovery_segmentation.classify_liquidity_bucket` (the same `volume_ratio_20d` thresholds M1.34/M1.98 already use) and adds the microstructure evidence they didn't capture:

- `compute_average_daily_turnover` — the one liquidity-depth proxy this platform's OHLCV data can honestly support (no real bid-ask spread/order-book depth is ingested anywhere, same honest gap M1.98's own docstring names; nothing here fabricates one).
- `compute_gap_observation` — overnight gap percent/bucket plus `probable_circuit_band_event`, a documented proxy (single-day move ≥10%) for having hit *some* NSE circuit band, not a confirmed exchange freeze (no per-stock band schedule is ingested).
- `assess_liquidity_regime` — compares the current vs. previous `ScanCandidate`-derived liquidity bucket for a stock to flag a regime change.
- `record_microstructure_snapshot` — an immutable, point-in-time snapshot (`MicrostructureSnapshot`) linked to a `Prediction`; every value is derived only from data at or before `recorded_at`.
- `get_microstructure_snapshot` — the read path a future revision of M1.98's execution-cost model could consume (not wired in, same propose-only posture as every other gate module here).
- `compute_liquidity_segment_performance` — segments already-evaluated outcomes by liquidity bucket, gap bucket and circuit-event flag; a superset of M1.27's `DiscoverySegment`-based liquidity dimension.

11 new tests in `tests/test_microstructure_liquidity.py`; migration `0104_microstructure_liquidity` adds the table.
