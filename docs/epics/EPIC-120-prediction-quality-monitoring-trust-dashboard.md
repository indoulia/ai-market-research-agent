# EPIC-120 — Prediction Quality Monitoring & Trust Dashboard

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Make the evolution of prediction quality, trust and learning visible over time so users can understand whether MRA is actually becoming more reliable.

## Scope
- Show trust score history.
- Show accuracy, calibration and usefulness trends.
- Show target/SL/horizon performance.
- Show performance by horizon and regime.
- Show positive recommendation count versus successful recommendation count.
- Show suppressed-candidate statistics without presenting negative recommendations as user recommendations.
- Show model versions, promotions, regressions and learning events.
- Show data/evidence quality trends.
- Provide drill-down from aggregate trust to individual prediction history.

## Acceptance Criteria
- Users can see whether trust is increasing or decreasing over time.
- Historical prediction states are reconstructable.
- Model changes and their measured impact are visible.
- Metrics distinguish current performance from historical performance.
- Dashboard never hides negative evidence needed to understand trust.
- User-facing recommendation feed remains positive-only.

## Dependencies
Previous: EPIC-080, EPIC-081, EPIC-085, EPIC-086, EPIC-087, EPIC-119.
Next: EPIC-117 validation gate.

## Completion Report

**Status:** DONE — merged to main via PR #143 (`9bd6961`).

**Implementation:**
- `app/trust_dashboard.py` (`build_trust_dashboard`, `get_prediction_trust_drilldown`): a new, versioned (`DASHBOARD_VERSION = "TDB-001"`) read-only composition module, following the same no-persistence pattern EPIC-019's `compute_trust_report` already established. It introduces no new measurement and no new table -- every field is assembled from an already-existing, already-immutable history accessor:
  - `trust_score_trend` — every `PredictionTrustScore` for the model version's predictions, chronological (EPIC-080).
  - `benchmark_history` / `calibration_drift_history` — `get_benchmark_report_history` (EPIC-086) / `get_drift_history` (EPIC-085), covering accuracy, target/stop-hit rate, horizon and calibration trend scope items.
  - `usefulness_by_horizon` — `get_usefulness_report_history` per horizon (EPIC-089).
  - `regime_trust` — `get_trust_history` for the `COMBINED` segment across every horizon/regime (EPIC-084), covering "performance by horizon and regime."
  - `promotion_history` / `regression_history` / `learning_hypothesis_history` — EPIC-026/EPIC-062/EPIC-119's own histories, covering "model versions, promotions, regressions and learning events."
  - `positive_recommendation_count` / `successful_recommendation_count` / `suppressed_candidate_count` / `suppression_reason_counts` — derived from each prediction's *latest* EPIC-082 gate decision and EPIC-005 outcome; suppression is reported only via the fixed EPIC-082 reason vocabulary, never alongside a candidate's identity as a "recommendation" (AC: "never presents negative recommendations as user recommendations").
  - `evidence_quality_state_counts` — each prediction's latest EPIC-078 evidence-quality state, covering the data/evidence quality trend scope item.
- `get_prediction_trust_drilldown` composes every per-prediction history (trust score, gate decisions, EPIC-087 trust control, evidence quality, EPIC-083 stability, EPIC-088 attribution, EPIC-089 usefulness, EPIC-005 outcome) for one `prediction_id`, satisfying "drill-down from aggregate trust to individual prediction history."
- No write path to `Prediction`, `ScanCandidate`, or any recommendation-facing table — this module cannot affect the live positive-only feed, matching the AC "user-facing recommendation feed remains positive-only."

**Tests:** `tests/test_trust_dashboard.py` (7 tests) — empty dashboard for an unknown model version, positive/successful/suppressed counting (including that only the *latest* gate/evidence-quality decision per prediction counts), chronological trust-score trend across predictions, and promotion/regression/regime-trust/drilldown composition.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_trust_dashboard.py -q` → `7 passed`
- `python -m pytest -q` (full suite) → `909 passed`
- No migration needed (no new table; purely a read-only composition module).
