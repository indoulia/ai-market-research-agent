# EPIC-M1.99 — Cross-Sectional Opportunity Ranking

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Select the strongest positive opportunities by comparing candidates against one another using calibrated probability, trust, expected return, risk, evidence quality and stability.

## Scope
- Rank qualified positive candidates across the current universe.
- Support horizon-specific ranking.
- Combine probability, expected return, risk, reward/risk, trust and evidence quality.
- Penalize instability, concentration and weak evidence.
- Preserve ranking snapshots and selection reasons.
- Measure ranking effectiveness against alternatives and benchmarks.

## Acceptance Criteria
- Ranking is deterministic and explainable.
- Only positive-gated candidates enter the recommendation feed.
- Ranking favors evidence-backed, high-trust opportunities.
- Historical ranking decisions are reconstructable.
- Ranking performance can be measured independently from model accuracy.

## Dependencies
Previous: M1.87, M1.98.
Next: M1.100.

## Completion Report

**Status:** VALIDATING (implemented, tests passing, PR open)

**Implementation:**
- `app/cross_sectional_ranking.py` (`rank_scan_candidates`, `measure_ranking_effectiveness`, `get_effectiveness_report_history`): a new, versioned (`EFFECTIVENESS_RULE_VERSION = "CSR-001"`) module.
- **Rank qualified positive candidates across the current universe / support horizon-specific ranking / combine probability, expected return, risk, reward/risk, trust and evidence quality / penalize instability, concentration and weak evidence / preserve ranking snapshots:** `rank_scan_candidates` resolves one scan's own M1.9-qualified candidates into `prediction_id`s and hands them unchanged to M1.87's already-merged `rank_positive_opportunities` — every one of these scope items is satisfied by composition with M1.87, never a second implementation, avoiding the vocabulary/logic-drift trap two similarly-named EPICs have hit before in this backlog.
- **Measure ranking effectiveness against alternatives and benchmarks (this EPIC's own, genuinely new contribution):** `measure_ranking_effectiveness` compares the realized, already-resolved success rate of M1.87's composite-ranked top-K opportunities (`PositiveOpportunityRanking.included`/`rank_position`) against M1.14's own, already-production `RecommendationSelection` opportunity-score-only top-K, over the same `PredictionOutcome` evidence within a caller-supplied `EvaluationWindow` (M1.25). Neither ranking method is re-derived; this module only compares two already-computed, already-persisted artifacts' downstream outcomes.
- Below `MIN_SAMPLE_SIZE_FOR_COMPARISON` on either side the report is honestly `INSUFFICIENT_SAMPLE`; otherwise `COMPOSITE_BETTER`/`ALTERNATIVE_BETTER`/`NO_SIGNIFICANT_DIFFERENCE` by the same `WEAKNESS_MARGIN` this platform uses everywhere else. New table `ranking_effectiveness_reports` (migration `0074_ranking_effectiveness.py`) follows the same append-only "report," not "per-entity decision," pattern M1.85's `FactorAssociationReport` already established — no idempotency check, no unique constraint, each call is an independent fresh measurement.
- No write path to `Prediction`, `ScanCandidate`, `RecommendationSelection`, or `PositiveOpportunityRanking` — this module cannot affect either ranking method, only measure them (AC: "only positive-gated candidates enter the recommendation feed" continues to hold unchanged).

**Tests:** `tests/test_cross_sectional_ranking.py` (6 tests) — cross-sectional ranking scopes correctly to one scan's own qualified candidates (excluding another scan's), insufficient-sample handling, `COMPOSITE_BETTER`/`ALTERNATIVE_BETTER`/`NO_SIGNIFICANT_DIFFERENCE` verdicts, and `top_k`/`rank_position` filtering.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_cross_sectional_ranking.py -q` → `6 passed`
- `python -m pytest -q` (full suite) → `915 passed`
- `python -m alembic heads` → single head `0074_ranking_effectiveness (head)`, chain resolves cleanly
