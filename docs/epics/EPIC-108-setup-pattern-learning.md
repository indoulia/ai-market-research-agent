# EPIC-108 — Setup & Signal-Combination Learning

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Discover which combinations of market, technical, fundamental, news, event and regime signals consistently produce useful positive outcomes.

## Scope
- Define reproducible setup signatures.
- Track outcomes by setup, horizon and regime.
- Discover recurring successful and failed combinations.
- Control feature/combination explosion and multiple testing.
- Feed validated setup evidence into experiments, ranking and Trust Score.

## Dependencies
EPIC-088, EPIC-089, EPIC-100, EPIC-104.

## Completion Report

**Status:** DONE — merged to main via PR #179 (`73a32e5`).

**Implementation:**
- `app/setup_combination_learning.py`: a new, versioned (`SETUP_COMBINATION_VERSION = "SCL-001"`) module.
- **Define reproducible setup signatures / track outcomes by setup, horizon and regime:** `setup_signature = f"{sma20_distance_bucket}_{volume_ratio_bucket}"` is a deterministic function of EPIC-088's already-bucketed, already-immutable `PredictionAttributionSnapshot` columns, joined with `horizon_days` and `regime` — no new bucketing logic introduced. This is the genuinely new contribution vs. EPIC-088, which only ever looks at one dimension at a time.
- **Discover recurring successful and failed combinations:** reuses EPIC-088's exact `ASSOCIATION_SUCCESS`/`ASSOCIATION_FAILURE`/`ASSOCIATION_NONE`/`ASSOCIATION_INSUFFICIENT_SAMPLE` vocabulary rather than inventing a parallel one.
- **Control feature/combination explosion and multiple testing:** `multiplicity_trial_count` counts the number of distinct combinations that clear the sample floor in this run, and `adjusted_margin = WEAKNESS_MARGIN * multiplicity_trial_count` (the same fixed Bonferroni-style scaling idea EPIC-100 introduced for experiment arms, applied here to combinations — a genuinely different multiplicity question, so EPIC-100's own function is not called, only its underlying constant/pattern). Verified directly by `test_multiplicity_correction_requires_larger_delta_with_more_qualifying_combinations`: two combinations with a real ~18-23% edge over baseline are correctly demoted to `NO_CONSISTENT_ASSOCIATION` once three combinations are being tested at once (adjusted margin 30%).
- **Feed validated setup evidence into experiments, ranking and Trust Score:** propose-only — no write path to any experiment, ranking, or Trust Score table.
- New table `setup_combination_reports` (migration `0083_setup_combination_learning.py`), following EPIC-088/EPIC-099/EPIC-102's own "always compute a fresh, independent report" posture (no idempotency check needed for a report table).

**Tests:** `tests/test_setup_combination_learning.py` (5 tests) — insufficient overall sample; success/failure associations; a sparse combination correctly marked `INSUFFICIENT_SAMPLE` within an otherwise-measured report; multiplicity correction demoting moderate-edge combinations; history accumulation across multiple computation runs.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_setup_combination_learning.py -q` → `5 passed`
- `python -m pytest -q` (full suite) → `1041 passed`
- `python -m alembic heads` → single head `0083_setup_combination (head)`, chain resolves cleanly
