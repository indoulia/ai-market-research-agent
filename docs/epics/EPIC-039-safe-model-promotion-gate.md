# EPIC-039 — Safe Model Promotion Gate

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Allow a candidate model to replace the current model only when predefined evidence and safety gates are satisfied.

## Scope
- Define promotion thresholds.
- Require candidate-vs-current comparison evidence.
- Require minimum sample sizes.
- Require no unacceptable regression in critical horizons/segments.
- Require reproducible evaluation artifacts.
- Version active model selection.
- Provide explicit rejection reasons.
- Support rollback to the previous approved model.

## Acceptance Criteria
- [ ] Promotion is impossible without a completed comparison.
- [ ] Minimum evidence thresholds are enforced.
- [ ] Critical regression checks are enforced.
- [ ] Every promotion/rejection is auditable.
- [ ] Active model version is unambiguous.
- [ ] Previous model remains recoverable for rollback.
- [ ] Promotion does not modify historical recommendation results.

## Dependencies
**Previous:** EPIC-038
**Next:** EPIC-040

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-039

### Branch

autonomous/epic-m1-44, branched cleanly from `main` (the declared dependency -- EPIC-038 -- is already merged).

### Objective

A hard, deterministic evidence gate deciding whether a candidate model may become the active model, consuming EPIC-038's same-period comparison report as its sole evidence -- the natural generalization of EPIC-026 (which gated EPIC-025's same-model/two-period comparison) to EPIC-038's two-model/same-period one.

### Promotion Gates

Three mandatory checks, evaluated in order, any one of which rejects:
1. EPIC-038's own `VERDICT_INSUFFICIENT_EVIDENCE` → `REASON_INSUFFICIENT_EVIDENCE` (scope: "require minimum sample sizes", inherited from EPIC-038's/EPIC-019's `MIN_SAMPLE_SIZE_FOR_COMPARISON`, not redefined).
2. EPIC-038's own `VERDICT_REGRESSED` → `REASON_REGRESSED` (scope: "require candidate-vs-current comparison evidence" -- EPIC-038's overall calibration verdict *is* that check; this gate consumes it, never recomputes it).
3. **New in this EPIC, generalizing EPIC-026's single horizon-only check to all five of EPIC-038's segment dimensions**: `_critical_segment_regressions` scans every segment bucket present in both models' evaluations across horizon, sector, market-cap bucket, discovery source, and regime (skipping any bucket either side already flagged `INSUFFICIENT_SAMPLE`) and rejects with `REASON_CRITICAL_SEGMENT_REGRESSION` if any bucket's calibration error worsens by `REGRESSION_MARGIN` (reused from EPIC-025/EPIC-038, not redefined) or more -- a candidate could pass the overall verdict while quietly regressing one specific segment it wasn't dominant in.
4. Only if all three pass: `DECISION_PROMOTED`, `REASON_VALIDATED`.

### Rejection Cases

Every rejection records a specific, named reason (`INSUFFICIENT_EVIDENCE`/`REGRESSED`/`CRITICAL_SEGMENT_REGRESSION`) and, for the segment-regression case, the exact `(dimension, key)` bucket that triggered it (scope: "provide explicit rejection reasons"). Rejected decisions are never deleted -- they are retained forever alongside promoted ones in the same immutable log.

### Audit Evidence

`evaluate_promotion` is a pure function of its `comparison` argument -- no randomness, no hidden state -- so the same EPIC-038 report always yields the same decision (AC: "every promotion/rejection is auditable"; "promotion decision is reproducible from stored evidence," carried over from EPIC-026's identical framing). Every decision -- promoted or rejected -- is persisted as one immutable `ModelPromotionDecision` row recording `dataset_version`, `candidate_model_name`, `comparison_version`, `calibration_error_delta`, `decision`, `decision_reason`, the regressed segment (if any), `approver`, and `decided_at`.

### Active-Version Handling

`get_active_model(session, dataset_version=...)` returns the most recent `PROMOTED` row for that dataset version, or `None` if nothing has ever been promoted -- never fabricated (AC: "active model version is unambiguous"). Scoping by `dataset_version` (rather than a single global pointer, as EPIC-026 had) reflects that EPIC-038's comparisons are inherently dataset-version-scoped.

### Rollback Validation

Mirrors EPIC-026's exact design: the append-only, immutable `model_promotion_decisions` log itself *is* the rollback mechanism -- every prior `PROMOTED` row remains queryable forever via `get_promotion_history`, never deleted or overwritten (AC: "previous model remains recoverable for rollback"). `test_active_model_tracks_only_the_latest_promotion_for_its_dataset_version` proves a later rejected candidate does not disturb the active pointer, and the full history remains queryable regardless.

### Promotion Does Not Modify Historical Results

This module has no code path that writes to `Prediction`, `PredictionOutcome`, or any other historical-result table -- its only write is the append-only decision log itself. `test_promotion_does_not_modify_historical_prediction_tables` proves the `Prediction` table is untouched by a promotion decision (AC).

### Design Decisions

- **New table `model_promotion_decisions`** (migration `0029`, chains off EPIC-034's `0028`), deliberately separate from EPIC-026's `model_promotions` table rather than extending it: EPIC-026 gates EPIC-025-style same-model/two-period evidence (`success_rate_delta`, `candidate_model_version`/`baseline_model_version`), while this gate consumes structurally different EPIC-038-style same-period/two-model evidence (`calibration_error_delta`, `dataset_version`/`candidate_model_name`). Keeping them separate avoids forcing one schema to represent two different evidence shapes, and leaves EPIC-026's already-merged, already-tested module untouched.
- **Reuses rather than duplicates**: EPIC-038's `VERDICT_INSUFFICIENT_EVIDENCE`/`VERDICT_REGRESSED` (imported, not redefined), EPIC-025's `REGRESSION_MARGIN`, and mirrors EPIC-026's immutability-guard and append-only-log design exactly.
- **Generalizing the critical-regression check to all five dimensions, not just horizon**, is this EPIC's own genuinely new contribution beyond simply consuming EPIC-038's top-level verdict.

### Files Changed

- `app/safe_model_promotion.py` — new: `evaluate_promotion`, `get_active_model`, `get_promotion_history`, decision/reason constants, `ModelPromotionDecisionImmutableError`.
- `app/models.py` — new `ModelPromotionDecision` model.
- `migrations/versions/0029_model_promotion_decisions.py` — new migration.
- `tests/test_safe_model_promotion.py` — new: 9 tests.
- `docs/epics/EPIC-039-safe-model-promotion-gate.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_safe_model_promotion.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0029_model_promotion_decisions`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0028` through `0029` (verified `model_promotion_decisions` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **381 passed, 0 failed** (372 pre-existing from `main` + 9 new).
- `pytest -q tests/test_safe_model_promotion.py -v`: **9 passed** — a `VALIDATED` comparison is `PROMOTED`; a `REGRESSED` one and an `INSUFFICIENT_EVIDENCE` one are each `REJECTED` with the matching reason; a comparison that is `VALIDATED` overall but has one horizon's calibration error blowing up from 0.1 to 0.5 is correctly `REJECTED` with `CRITICAL_SEGMENT_REGRESSION` (recording the exact `horizon`/`1` bucket) despite the passing top-level verdict; the identical segment regression is correctly *ignored* (and promotion proceeds) when either side already flagged that bucket `INSUFFICIENT_SAMPLE`; a direct mutation attempt after creation raises `ModelPromotionDecisionImmutableError`; the active model correctly tracks only the latest *promoted* candidate for its dataset version even after a later rejected candidate is evaluated; the full promotion history preserves every decision, including rejected ones, queryable by candidate name; and no `Prediction` row is ever created or touched by a promotion decision.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Promotion is impossible without a completed comparison (`evaluate_promotion` requires a `CandidateModelComparisonReport`; there is no other entry point).
- [x] Minimum evidence thresholds are enforced (`VERDICT_INSUFFICIENT_EVIDENCE` → `REASON_INSUFFICIENT_EVIDENCE`, inherited from EPIC-019/EPIC-038).
- [x] Critical regression checks are enforced (`_critical_segment_regressions` across all five segment dimensions).
- [x] Every promotion/rejection is auditable (deterministic, immutable, stored `ModelPromotionDecision` row for every decision).
- [x] Active model version is unambiguous (`get_active_model`, most recent `PROMOTED` row per dataset version, never fabricated).
- [x] Previous model remains recoverable for rollback (`get_promotion_history`, immutable append-only log, nothing ever deleted).
- [x] Promotion does not modify historical recommendation results (no write path to any historical table exists in this module; proven by test).

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a segment-regression check proven to fire correctly and to be correctly suppressed under insufficient sample. This EPIC composes EPIC-038's verdict vocabulary and EPIC-025's regression margin while mirroring EPIC-026's append-only, immutable design exactly, generalizing its single-horizon regression check to all five of EPIC-038's segment dimensions. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->