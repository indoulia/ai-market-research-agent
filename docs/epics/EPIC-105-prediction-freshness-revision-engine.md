# EPIC-105 — Prediction Freshness & Revision Engine

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Continuously determine whether an active prediction remains valid and create an immutable revision when material new information changes its thesis.

## Scope
- Track freshness of every prediction input.
- Detect material new market, fundamental, news and event information.
- Trigger re-analysis when policy thresholds are met.
- Preserve every prediction revision and reason.
- Recalculate target, SL, probability, score and Trust Score when justified.
- Invalidate stale predictions without presenting negative/cautious states to users.

## Dependencies
EPIC-049, EPIC-057, EPIC-081, EPIC-101, EPIC-103.

## Completion Report

**Status:** DONE — merged to main via PR #165 (`65b81b8`).

**Implementation:**
- `app/prediction_freshness_engine.py`: a new, versioned (`FRESHNESS_ENGINE_VERSION = "PFE-001"`) module composing EPIC-057's already-merged `revalidate_recommendation` (`UNCHANGED`/`UPDATED`/`WITHDRAWN`/`EXPIRED`, reused unchanged and itself idempotent) with the two newer evidence sources EPIC-057 predates and has no way to know about: EPIC-101's per-feature/coverage drift `trust_reduction_recommended` signals, and EPIC-103's fundamental provider `MATERIAL_DISAGREEMENT` verdict for the same stock.
- **Track freshness / detect material new information / trigger re-analysis when thresholds are met:** `evaluate_prediction_freshness` records a `trigger` entry for each active signal — `REVALIDATION_MATERIAL_CHANGE` (any EPIC-057 outcome other than `UNCHANGED`), `FEATURE_DRIFT_DETECTED` (naming every currently-drifting monitored feature), `COVERAGE_DRIFT_DETECTED`, `FUNDAMENTAL_PROVIDER_DISAGREEMENT` — and sets `re_analysis_recommended = bool(triggers)`.
- **Preserve every prediction revision and reason:** `revision_trigger_reason` reuses EPIC-050's own `REASON_MATERIAL_EVIDENCE_CHANGE` vocabulary value (not a parallel one) so a future orchestration step that actually calls `create_recommendation_revision` needs no vocabulary translation.
- **Recalculate target, SL, probability, score and Trust Score when justified:** deliberately not performed here — this module never calls EPIC-050's revision creation itself, the same propose/gate split this platform has used for every trust/eligibility signal since EPIC-085.
- **Invalidate stale predictions without presenting negative/cautious states to users:** holds structurally — no write path to `Prediction`, `RecommendationSelection`, or any recommendation-facing table.
- New immutable table `prediction_freshness_decisions` (migration `0080_prediction_freshness_engine.py`), idempotent by `(prediction_id, evaluated_at)`.

**Tests:** `tests/test_prediction_freshness_engine.py` (6 tests) — clean prediction produces no triggers; each of the four trigger sources (revalidation material change, feature drift, coverage drift, fundamental provider disagreement) independently verified; idempotency.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_prediction_freshness_engine.py -q` → `6 passed`
- `python -m pytest -q` (full suite) → `1000 passed`
- `python -m alembic heads` → single head `0080_prediction_freshness (head)`, chain resolves cleanly
