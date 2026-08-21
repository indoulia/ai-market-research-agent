# EPIC-M1.130 — Prediction Abstention Quality & Opportunity Suppression Learning

**Status:** VALIDATING
**Execution Status:** IMPLEMENTED_PR_OPEN
**Priority:** P1

## Objective
Measure whether MRA's positive-only suppression decisions are themselves correct, preventing the system from becoming either recklessly permissive or excessively conservative.

## Scope
- Preserve qualified-but-suppressed candidates and reasons.
- Define abstention outcomes for suppressed opportunities.
- Measure missed-opportunity rate, false-positive avoidance and suppression utility.
- Segment abstention quality by horizon, regime, sector, stock/setup and trust level.
- Learn thresholds that balance opportunity capture with recommendation quality.
- Feed validated abstention evidence into ranking and Trust policy.
- Keep user-facing output positive-only.

## Acceptance Criteria
- Every suppression has a reason and policy version.
- Suppressed candidates can be evaluated retrospectively without becoming user recommendations.
- MRA can quantify both harmful publication and harmful suppression.
- Threshold changes require controlled validation.
- Historical suppression decisions remain immutable.

## Dependencies
M1.87, M1.99, M1.100, M1.110.

## Non-Goal
Do not introduce negative/cautious recommendations to the user-facing feed.

## Completion Report

**Status:** VALIDATING — implemented, tests green, PR open (not yet merged).

**Implementation:**
- `app/abstention_quality.py`: a new, versioned (`ABSTENTION_QUALITY_VERSION = "AQR-001"`) module, and a new immutable report table `segment_abstention_quality_reports` (migration `0095_abstention_quality.py`, chained after a `0094_merge_0093_heads` alembic merge migration — this branch and EPIC-M1.116's both chained onto `0092_reproducibility_audit` and landed on main as sibling heads within the same window, the same collision `0089_merge_0088_heads` already documented).
- **Preserve qualified-but-suppressed candidates and reasons / define abstention outcomes for suppressed opportunities:** already M1.13's (`RecommendationGeneration`), M1.81's (`PositiveRecommendationGateDecision`) and M1.111's (`evaluate_recommendation` via `backfill_counterfactual_outcomes`) own jobs — reused, not duplicated.
- **Measure missed-opportunity rate, false-positive avoidance and suppression utility:** M1.111's `compare_published_vs_suppressed` already computes this as one platform-wide aggregate (`opportunity_cost_total`, `avoided_loss_total`). This EPIC's own genuinely new contribution is **segmenting** that same comparison — `evaluate_segment_abstention_quality` groups the identical qualified/evaluated rows by sector, market-cap bucket, horizon and market regime (M1.104's own segment vocabulary plus M1.26's `classify_market_regime`, both reused unchanged) and reports each group's published/suppressed sample counts, success rates, `opportunity_cost_total`, `avoided_loss_total` — and, new, `published_loss_total` (the realized loss on *published* failures, i.e. the harmful-publication side of the AC's "quantify both harmful publication and harmful suppression"), each independently gated by M1.85/M1.99's own `MIN_SAMPLE_SIZE_FOR_COMPARISON`/`WEAKNESS_MARGIN` (verified: a 20-vs-20 sector group with a 25pp published-success advantage reports `OK` with the exact delta; a 5-vs-5 group reports `INSUFFICIENT_SAMPLE` with no delta at all).
- **Segment abstention quality by horizon, regime, sector ... and trust level:** sector/market-cap/horizon/regime/global are covered. **Stock/setup-level and trust-level segmentation are honestly out of scope for this PR** — named here rather than fabricated, the same restraint M1.109's own module already exercised for data it didn't yet have reliable coverage for.
- **Learn thresholds ... / feed validated abstention evidence into ranking and Trust policy:** explicitly deferred, same posture M1.101/M1.102/M1.104/M1.122's own signals already established. Propose-only — no write path to `RecommendationGeneration`, `RecommendationSelection`, `PositiveRecommendationGateDecision`, or any ranking/Trust table.
- **Historical suppression decisions remain immutable:** every report is append-only (no update path), always computed fresh (same posture as M1.85/M1.99/M1.102's own reports).

**Tests:** `tests/test_abstention_quality.py` (8 tests) — sector-level OK verdict with correct success-rate delta, below-threshold insufficiency, global-segment aggregation across sectors, opportunity-cost/avoided-loss totals, published-loss-total (harmful-publication) computation, regime-segment population, window filtering, and report-history accumulation.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_abstention_quality.py -q` → `8 passed`
- `python -m pytest tests/ -q` (full suite) → `1155 passed`
- `python -m alembic heads` → single head `0095_abstention_quality (head)`, chain resolves cleanly through the `0094_merge_0093_heads` merge point
