# EPIC-M1.102 — Regime Transition & Uncertainty Intelligence

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Detect unstable market-regime transitions and separate inherent market uncertainty from insufficient model knowledge so Trust Score and positive recommendation eligibility respond appropriately.

## Scope
- Detect transitions between market regimes.
- Measure transition confidence and instability.
- Distinguish market uncertainty from data/model uncertainty where feasible.
- Incorporate uncertainty into Trust Score and positive-only gating.
- Preserve regime and uncertainty snapshots with predictions.
- Evaluate transition-period prediction performance separately.

## Acceptance Criteria
- Stable and transitional regimes are distinguishable.
- Transition periods can reduce trust when evidence supports it.
- Uncertainty sources are separately represented.
- Historical transition behavior is measurable.
- No automatic recommendation downgrade to a negative/cautious user-facing state; low-trust candidates are suppressed instead.

## Dependencies
Previous: M1.79, M1.101.
Next: M1.103.

## Completion Report

**Status:** DONE — merged to main via PR #154 (`70d2fa6`).

**Implementation:**
- `app/regime_transition_intelligence.py`: a new, versioned (`REGIME_TRANSITION_VERSION = "RTI-001"`) module. Never reclassifies a regime itself — reads M1.26's already-computed `MarketRegime` only.
- **Detect transitions between market regimes / measure transition confidence and instability:** `detect_regime_transition` compares a scan's regime label against the immediately preceding scan (same `universe_version`, ordered by `scan_date`); `distance_to_boundary` (reusing M1.26's own `BULLISH_BREADTH_THRESHOLD`/`BEARISH_BREADTH_THRESHOLD` constants, never redefining them) measures how close the breadth ratio sits to either threshold — within a fixed `UNSTABLE_BOUNDARY_MARGIN = 0.05` is `NEAR_BOUNDARY`.
- **Distinguish market uncertainty from data/model uncertainty where feasible:** composes two independent, already-real signals rather than inventing a third — MARKET uncertainty is this module's own boundary-proximity-plus-transition measure; MODEL uncertainty reuses M1.101's `trust_reduction_recommended` feature/coverage drift signals for the same model version (a new public `MONITORED_FEATURES` constant was added to `feature_drift_monitor.py` so this module can iterate the monitored-feature vocabulary without reaching into that module's private column mapping — a pure additive export, no existing behavior changed). `uncertainty_source` is an honest `NONE`/`MARKET`/`MODEL`/`MARKET_AND_MODEL` enumeration.
- **Incorporate uncertainty into Trust Score and positive-only gating:** `trust_reduction_recommended` is set only when the MARKET signal itself is active (an unstable transition) — a propose-only flag with no write path to `PredictionTrustScore`/`TrustControlDecision`/any recommendation table, the same posture M1.80/M1.83/M1.101 already established before `trust_control.py` composed them.
- **Preserve regime and uncertainty snapshots with predictions:** `snapshot_prediction_regime_uncertainty` links a prediction to its scan's transition assessment via a new thin immutable index table (`prediction_regime_uncertainty_snapshots`), the same pattern M1.78's `DailyPredictionSnapshot` already established; returns `None` rather than fabricating a link when no assessment exists yet for that scan.
- **Evaluate transition-period prediction performance separately:** `evaluate_transition_period_performance` compares realized success rates between transition-flagged and stable scans within a window, `INSUFFICIENT_SAMPLE` below `MIN_SAMPLE_SIZE_FOR_COMPARISON` on either side — same always-fresh "report" pattern as M1.85/M1.99.
- **No automatic recommendation downgrade to a negative/cautious state (AC):** holds structurally — this module has no write path to `Prediction`, `PositiveRecommendationGateDecision`, or any recommendation-facing table at all; every output is a new, independent table (migration `0077_regime_transition_intelligence.py`).

**Tests:** `tests/test_regime_transition_intelligence.py` (14 tests) — no-transition/transition-detected cases, missing-regime error, boundary instability near/far from threshold, all four `uncertainty_source` combinations, idempotency, per-prediction snapshot linking (including the no-assessment-yet case), and transition-period performance insufficient-sample/measured cases.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_regime_transition_intelligence.py -q` → `14 passed`
- `python -m pytest -q` (full suite) → `964 passed`
- `python -m alembic heads` → single head `0077_regime_transition (head)`, chain resolves cleanly
