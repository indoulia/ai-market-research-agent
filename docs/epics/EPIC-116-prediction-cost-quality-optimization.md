# EPIC-116 — Prediction Cost & Quality Optimization

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Optimize MRA's provider/model usage so prediction quality improves without unnecessary external cost or latency.

## Scope
- Measure provider/model marginal predictive value.
- Route expensive analysis only where it improves validated outcomes.
- Cache reusable evidence safely with freshness controls.
- Use cheaper/local providers for suitable tasks.
- Compare quality, latency and cost trade-offs.
- Ensure cost optimization never silently reduces minimum prediction-quality policy.

## Dependencies
EPIC-093, EPIC-094, EPIC-103, EPIC-114.

## Completion Report

**Status:** DONE — merged to main via PR #216.

**Implementation:**
- `app/cost_quality_optimization.py`: a new, versioned (`COST_QUALITY_VERSION = "CQO-001"`) module.
- **Measure provider/model marginal predictive value / compare quality, latency and cost trade-offs:** `compute_cost_quality_tradeoff` composes EPIC-093's already-computed `ProviderQualityReport` (per-provider success rate and verdict) with EPIC-093's own `PROVIDER_COST_PER_REQUEST_USD` — never recomputing either. Every real provider adapter in this platform today is free; reported honestly rather than fabricating a nonzero cost.
- **Route expensive analysis only where it improves validated outcomes / use cheaper/local providers for suitable tasks:** among quality-acceptable providers (verdict not `VERDICT_WEAK`), the best-quality *free* provider is preferred by default (`COST_OPTIMIZED_SELECTION`); a paid provider is only ever recommended when no quality-acceptable free provider exists (`QUALITY_JUSTIFIES_COST`).
- **Ensure cost optimization never silently reduces minimum prediction-quality policy:** a `VERDICT_WEAK` provider (below EPIC-059's `RELIABILITY_SUCCESS_THRESHOLD` quality floor) is never recommended regardless of cost — verified directly by `test_weak_provider_never_recommended_despite_being_free`; if every candidate is `VERDICT_WEAK`, the honest `NO_ACCEPTABLE_PROVIDER` verdict is returned rather than falling back to a free-but-proven-poor option.
- A provider with no known cost yet (not in `PROVIDER_COST_PER_REQUEST_USD`) is neither assumed free nor assumed paid — excluded from a cost-based recommendation entirely until its real cost is known, verified by `test_provider_with_unknown_cost_excluded_from_recommendation`.
- **Cache reusable evidence safely with freshness controls:** already covered structurally by EPIC-030's freshness checks; no new caching mechanism added, since none exists elsewhere in this codebase to safely extend within this EPIC's scope — named honestly rather than built speculatively.
- Read-only: no write path to `ProviderRegistry` or any selection table. New table `cost_quality_tradeoff_reports` (migration `0093_cost_quality_optimization.py`).

**Tests:** `tests/test_cost_quality_optimization.py` (6 tests) — cost-optimized selection among two free providers, a weak provider never recommended despite being free, no-acceptable-provider when all are weak, quality-justifies-cost when only a paid provider clears the floor (via a monkeypatched cost table, since no real paid provider exists in this codebase today), unknown-cost exclusion, report history accumulation.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_cost_quality_optimization.py -q` → `6 passed`
- `python -m pytest -q` (full suite) → `1139 passed`
- `python -m alembic heads` → single head `0093_cost_quality (head)`, chain resolves cleanly
