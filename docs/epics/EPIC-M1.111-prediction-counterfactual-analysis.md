# EPIC-M1.111 — Prediction Counterfactual & Selection-Bias Analysis

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Measure what would have happened to qualified and suppressed candidates so MRA can distinguish true selection skill from merely avoiding difficult cases.

## Scope
- Preserve point-in-time candidate universe and selection decisions.
- Evaluate published versus suppressed candidates using identical outcome definitions.
- Measure opportunity cost and avoided losses.
- Compare ranking and gating alternatives.
- Feed counterfactual evidence into discovery/ranking evaluation without changing historical decisions.

## Dependencies
M1.97, M1.99, M1.100, M1.110.

## Completion Report

**Status:** VALIDATING (implemented, tests passing, PR open)

**Implementation:**
- `app/counterfactual_analysis.py`: a new, versioned (`COUNTERFACTUAL_ANALYSIS_VERSION = "CFA-001"`) module.
- **Evaluate published versus suppressed candidates using identical outcome definitions:** `backfill_counterfactual_outcomes` calls M1.5's own `evaluate_recommendation` completely unmodified for every M1.13-qualified prediction in a scan that has no outcome yet, whether it was ever selected/published or not — that function only needs `entry_price`/`target_return`/`stop_return`/`horizon_days` and subsequent `MarketPrice` rows, and never checks selection status.
- A candidate that never reached `OUTCOME_QUALIFIED` at all has no target/stop to evaluate against in the first place — that half of "qualified and suppressed candidates" is honestly out of reach without fabricating a synthetic target/stop this platform never actually proposed, named in the module docstring rather than invented.
- **Measure opportunity cost and avoided losses:** `compare_published_vs_suppressed` sums realized gains on suppressed-but-successful candidates (`opportunity_cost_total`) and realized losses on suppressed-but-failed candidates (`avoided_loss_total`), verified directly by `test_compare_computes_opportunity_cost_and_avoided_loss`.
- **Compare ranking and gating alternatives:** already covered by M1.99's `RankingEffectivenessReport`, not duplicated here.
- **Preserve point-in-time candidate universe and selection decisions / feed counterfactual evidence into discovery/ranking evaluation without changing historical decisions:** no write path to `RecommendationGeneration`, `RecommendationSelection`, or `PositiveRecommendationGateDecision` — only new `PredictionOutcome` rows via M1.5's own immutable, idempotent writer, and a new, always-fresh `PublishedVsSuppressedReport` (migration `0087_counterfactual_analysis.py`).

**Migration numbering note:** this branch first numbered its migration `0086`, chained onto `0085_lifecycle_capacity`. By the time it was ready to merge, a concurrent EPIC-M1.141 session's migration had independently collided at the same `0085` parent and then resolved itself to `0086_api_pref_profile`. Rather than merge as a second competing head, this branch rebased onto the post-fix `origin/main` and renumbered its own migration to `0087_counterfactual` chained onto `0086_api_pref_profile` — no schema change, coordinated live with the other session.

**Tests:** `tests/test_counterfactual_analysis.py` (7 tests) — backfill evaluates an unselected qualified prediction via the real M1.5 evaluator, correctly skips when market data is insufficient or already evaluated, insufficient-sample reporting, opportunity-cost/avoided-loss computation, a weak verdict when suppressed candidates actually outperformed, and report-history accumulation.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_counterfactual_analysis.py -q` → `7 passed`
- `python -m pytest -q` (full suite) → `1084 passed`
- `python -m alembic heads` → single head `0087_counterfactual (head)`, chain resolves cleanly
