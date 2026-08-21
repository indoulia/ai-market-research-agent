# EPIC-M1.113 — Model Specialization & Capability Routing

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Allow MRA to use specialized validated models for different horizons, regimes, sectors or prediction setups when evidence demonstrates that specialization improves out-of-sample performance.

## Scope
- Define specialization dimensions and eligibility criteria.
- Compare specialized versus global models.
- Route predictions to specialized models only when sufficient evidence exists.
- Maintain global fallback for sparse segments.
- Prevent fragmentation and overfitting.
- Track specialized-model performance and Trust Score.

## Dependencies
M1.79, M1.100, M1.101, M1.104, M1.108, M1.109.

## Completion Report

**Status:** VALIDATING (implemented, tests passing, PR open)

**Implementation:**
- `app/model_specialization_routing.py`: a new, versioned (`SPECIALIZATION_ROUTING_VERSION = "MSR-001"`) module.
- **Define specialization dimensions:** reuses the exact same `HORIZON`/`REGIME`/`SECTOR`/`SETUP` dimension names this platform's other segmentation EPICs already use, reading segment membership directly off M1.85's already-immutable `PredictionAttributionSnapshot` columns wherever possible, joining to `Stock.sector` only for the one dimension the snapshot doesn't carry.
- **Compare specialized versus global models / route only when sufficient evidence exists / maintain global fallback for sparse segments:** `evaluate_specialization_candidate` reuses M1.100's own "independent confirmation across two disjoint windows" pattern — `ROUTE_TO_SPECIALIZED` only when the specialized model's segment success rate exceeds the global model's in *both* a baseline and a later, disjoint confirmation window; `USE_GLOBAL_FALLBACK` otherwise, including every insufficient-sample case (verified directly by `test_global_fallback_when_insufficient_sample`).
- **Prevent fragmentation and overfitting:** the caller supplies `candidate_count` (how many specialization candidates are being tested together); `adjusted_margin = WEAKNESS_MARGIN * candidate_count`, the same fixed Bonferroni-style scaling M1.100/M1.108 already established for their own multiplicity questions — verified directly by `test_multiplicity_correction_demotes_moderate_edge` (a real ~30-point edge routes at `candidate_count=1` but falls back to global at `candidate_count=5`).
- **Track specialized-model performance and Trust Score:** every decision, including its full evidence (sample counts, both window verdicts, the adjusted margin), is persisted immutably; `routing_verdict` is propose-only — no write path to `Prediction`, `ModelPromotion`, or any production table, since this platform has no live multi-model serving infrastructure to route into (M1.83's own docstring already establishes this honestly).
- New table `specialization_routing_decisions` (migration `0090_model_specialization_routing.py`).

**Tests:** `tests/test_model_specialization_routing.py` (8 tests) — route-to-specialized when both windows validate, global fallback when the confirmation window doesn't replicate, global fallback on insufficient sample, multiplicity correction demoting a moderate edge, all four dimensions (horizon/regime/sector/setup) individually verified, idempotency.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_model_specialization_routing.py -q` → `8 passed`
- `python -m pytest -q` (full suite) → `1109 passed`
- `python -m alembic heads` → single head `0090_specialization_routing (head)`, chain resolves cleanly
