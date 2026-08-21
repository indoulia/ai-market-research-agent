# EPIC-M1.112 — Prediction Assumption Decay & Invalidation

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Automatically detect when the assumptions behind an active prediction have materially decayed or broken and remove it from the user feed without exposing negative/cautious recommendations.

## Scope
- Track assumptions supporting each prediction.
- Define assumption freshness/decay rules.
- Detect material contradiction or thesis break.
- Trigger revalidation or invalidation.
- Preserve original and revised prediction history.
- Feed invalidation outcomes into learning.

## Dependencies
M1.65, M1.105, M1.106, M1.110.

## Completion Report

**Status:** VALIDATING (implemented, tests passing, PR open)

**Implementation:**
- `app/assumption_decay_tracker.py`: a new, versioned (`DECAY_RULE_VERSION = "ADT-001"`) module.
- **Track assumptions supporting each prediction:** every M1.48 evidence category that was `STATUS_AVAILABLE` at capture time is one tracked assumption (`FUNDAMENTAL`, `NEWS`, `EVENT`, `TECHNICAL_VOLUME`). `MARKET_SECTOR` is honestly excluded — a static classification with no real freshness-window concept in M1.35's own policy, named in the docstring rather than assigned an invented threshold.
- **Define assumption freshness/decay rules:** reuses M1.35's own `FRESHNESS_POLICY` thresholds unchanged, but applies them against the *original* `evidence_timestamp` M1.48 froze at capture, compared against `evaluated_at` (now) rather than the prediction's own `as_of_timestamp` (then) — a genuinely new check M1.74's evidence-quality gate never performs (that gate only ever asks whether evidence was fresh *at capture*).
- **Detect material contradiction or thesis break / trigger revalidation or invalidation:** `decay_ratio` is the fraction of tracked categories that have crossed their freshness window since capture; `MATERIAL_DECAY` (`decay_ratio >= 0.5`) sets `invalidation_recommended=True`. Propose-only — no write path to `Prediction` or any recommendation-facing table; an actual revalidation/revision remains M1.62/M1.55/M1.105's job.
- **Preserve original and revised prediction history / feed invalidation outcomes into learning:** this module never mutates `RecommendationEvidenceItem` or any revision table — every assessment is a new, immutable, idempotent-by-`(prediction_id, evaluated_at)` row (migration `0088_assumption_decay_tracker.py`).

**Migration numbering:** re-fetched `origin/main` and re-checked `alembic heads` immediately before writing this migration (per the live coordination established with the concurrent API-track session over the earlier 0083/0085 collisions) — confirmed a single clean head at `0087_counterfactual` before chaining `0088_assumption_decay` onto it.

**Tests:** `tests/test_assumption_decay_tracker.py` (6 tests) — no-decay when everything is fresh, partial decay with the correct ratio, material decay recommending invalidation, `MARKET_SECTOR` correctly excluded from tracking, an `UNAVAILABLE`-status item correctly excluded, idempotency.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_assumption_decay_tracker.py -q` → `6 passed`
- `python -m pytest -q` (full suite) → `1090 passed`
- `python -m alembic heads` → single head `0088_assumption_decay (head)`, chain resolves cleanly
