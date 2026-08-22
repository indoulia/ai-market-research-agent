# EPIC-118 — Positive Opportunity Selection & Ranking Optimization

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Select and rank the strongest positive opportunities from the discovered and analyzed candidate universe using trust, expected opportunity, risk and evidence quality.

## Scope
- Rank only candidates that pass the positive-only gate.
- Combine expected return, probability, trust, reward/risk, evidence quality and stability.
- Control concentration and duplicate opportunities.
- Prefer higher-quality opportunities rather than maximizing recommendation count.
- Support horizon-specific ranking.
- Preserve ranking snapshots for later usefulness measurement.

## Acceptance Criteria
- Ranking is deterministic and explainable.
- Only positive-gated candidates can enter the recommendation feed.
- Ranking favors evidence-backed opportunities.
- Low-trust/high-risk candidates cannot outrank stronger candidates without explicit evidence.
- Historical ranking decisions are reconstructable.

## Dependencies
Previous: EPIC-079, EPIC-080, EPIC-082, EPIC-089.
Next: EPIC-119, EPIC-099.

## Execution Rule
The ranking layer must not manufacture positive recommendations. It may only rank candidates that already satisfy the positive-only qualification policy.

## Completion Report

**Status:** DONE — merged to main via PR #139 (`e12191e`).

**Implementation:**
- `app/opportunity_ranking.py` (`rank_positive_opportunities`, `get_ranking_history`): a new, versioned (`OPPORTUNITY_RANKING_VERSION = "OPR-001"`), read-only ranking layer over predictions whose *latest* EPIC-082 `PositiveRecommendationGateDecision` is `VERDICT_GATE_PASS`. Never writes to `Prediction` or any upstream table.
- Composite score: fixed weighted average of expected return (`Prediction.target_return`, normalized against a 20% cap), calibrated probability (`Prediction.predicted_probability`), EPIC-080 trust (`PredictionTrustScore.overall_trust_score`), EPIC-078 evidence quality (1.0 when `STATE_SUFFICIENT`), plus EPIC-042 reward/risk (`RecommendationPublication.reward_risk_ratio`) and EPIC-083 stability (`PredictionStabilityAssessment.stability_verdict`) when available — weights renormalize over whichever of the two optional signals are present, so a candidate is never penalized for a signal nobody has computed yet.
- Concentration/duplicate control: only the highest-composite-score prediction per stock survives (`REASON_DUPLICATE_STOCK_LOWER_SCORE` on the rest), then at most `MAX_INCLUDED_PER_SECTOR = 3` survive per `Stock.sector` (`REASON_SECTOR_CONCENTRATION_LIMIT` on overflow), before final `rank_position` is assigned 1..N by descending composite score (symbol tie-break).
- New immutable table `positive_opportunity_rankings` (migration `0072_opportunity_ranking.py`, model `PositiveOpportunityRanking`) persists one row per considered prediction per `evaluated_at` batch — included and excluded alike, with every raw component — so every ranking decision is reconstructable (AC). A batch is idempotent and immutable per `evaluated_at` (a `before_update` listener rejects any field mutation after creation, matching the established gate/decision-table pattern).
- `horizon_days` filter supports horizon-specific ranking (scope item).
- Defensive exclusion reasons (`REASON_NOT_GATE_PASSED`, `REASON_MISSING_TRUST_SCORE`, `REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT`) cover inputs that shouldn't occur given the gate's own guarantees, without ever silently dropping a candidate from the snapshot.

**Tests:** `tests/test_opportunity_ranking.py` (12 tests) — gate-pass requirement, composite score computation with/without optional signals, correct rank ordering, duplicate-stock and sector-concentration exclusion, horizon filter, idempotency by `evaluated_at`, immutability, and ranking history retrieval.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_opportunity_ranking.py -q` → `12 passed`
- `python -m pytest -q` (full suite) → `892 passed`
- `python -m alembic heads` → single head `0072_opportunity_rank (head)`, chain resolves cleanly from `0001_initial`

**Not wired into any live selection/recommendation feed** — consistent with this platform's established propose/gate split (EPIC-060/EPIC-078/EPIC-080/EPIC-084/EPIC-085/EPIC-082 are all likewise available-but-not-wired); wiring ranking into the actual feed remains a future EPIC's job, same posture EPIC-082 itself documented for EPIC-087.
