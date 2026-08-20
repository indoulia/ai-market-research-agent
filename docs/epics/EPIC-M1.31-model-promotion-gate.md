# EPIC-M1.31 — Model Promotion Gate

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1

## Objective
Define a hard evidence gate that allows a candidate model to become the production model only when it demonstrably improves on the current model.

## Scope
- Define promotion criteria and minimum sample sizes.
- Require out-of-sample improvement across agreed core metrics.
- Require no unacceptable regression in any critical horizon.
- Record model version, evidence, decision, and approver.
- Make promotion atomic and reversible.
- Retain the previous production model for comparison/rollback.

## Non-goals
- Autonomous trading.
- Promotion based only on training performance.
- Deleting previous model versions.

## Acceptance Criteria
- No candidate becomes production without passing every mandatory gate.
- Promotion decision is reproducible from stored evidence.
- Previous production version remains recoverable.
- Failed candidates are retained as rejected versions with reasons.
- Promotion history is immutable.

## Dependency Chain
**Previous:** M1.25, M1.30  
**Next:** M1.32

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.31

### Branch

autonomous/epic-m1-31, branched cleanly from `main` (both declared dependencies -- M1.25 and M1.30 -- are already merged).

### Objective

A hard, deterministic evidence gate deciding whether a candidate model may become production, consuming M1.30's disjoint-window comparison report as its sole evidence, with every decision -- promoted or rejected -- retained immutably forever.

### Design Decisions

- **New table `model_promotions`** (migration `0022`, chains off M1.26's `0021`): an append-only, immutable decision log. Deliberately **not** a separate "current model" pointer plus a separate history table: the log itself *is* both. `get_current_production_model_version` reads the most recent `PROMOTED` row; rollback is simply reading the prior `PROMOTED` row. This is what makes "make promotion atomic and reversible" and "retain the previous production model" true by construction rather than by a second subsystem's consistency being maintained correctly -- one immutable insert per decision is the only state-changing operation that ever happens.
- **The gate has three mandatory checks, evaluated in order, any one of which rejects:**
  1. M1.30's own `VERDICT_INSUFFICIENT_EVIDENCE` → `REASON_INSUFFICIENT_EVIDENCE` (scope item 1: minimum sample sizes, inherited from M1.30's `MIN_SAMPLE_SIZE_FOR_COMPARISON` gating rather than redefined).
  2. M1.30's own `VERDICT_REGRESSED` → `REASON_REGRESSED` (scope item 2: "require out-of-sample improvement across agreed core metrics" -- M1.30's overall success-rate-based verdict *is* that check; this EPIC's gate doesn't recompute it, it consumes it).
  3. **New in this EPIC:** `_critical_horizon_regressions` -- a candidate could pass the overall verdict while quietly regressing one specific horizon it wasn't dominant in; this scans every horizon present in both baseline and candidate (skipping any horizon either side already flagged `INSUFFICIENT_SAMPLE` in M1.30's own `insufficient_sample_dimensions`) and rejects with `REASON_CRITICAL_HORIZON_REGRESSION` if any horizon's success rate falls by `REGRESSION_MARGIN` (reused from M1.30, not redefined) or more.
  4. Only if all three pass: `DECISION_PROMOTED`, `REASON_VALIDATED`.
- **"Promotion decision is reproducible from stored evidence" (AC)** holds because `evaluate_promotion` is a pure function of its `comparison` argument -- no randomness, no hidden state; the same M1.30 report always yields the same decision.
- **Immutability guard** (`ModelPromotionImmutableError`, `before_update`) on every field, matching this platform's standing convention for historical-fact rows -- "promotion history is immutable" (AC) and "failed candidates are retained as rejected versions with reasons" (AC) both hold at the database boundary, not only by application discipline.
- **No autonomous trading and no promotion based on in-sample performance alone** (non-goals) hold structurally: this module has no trading code path at all, and its only evidence input is M1.30's strictly out-of-sample comparison -- there is no code path that could feed it in-sample/training metrics instead.

### Files Changed

- `app/model_promotion.py` — new: `evaluate_promotion`, `get_current_production_model_version`, `get_promotion_history`, decision/reason constants, `ModelPromotionImmutableError`.
- `app/models.py` — new `ModelPromotion` model.
- `migrations/versions/0022_model_promotions.py` — new migration.
- `tests/test_model_promotion.py` — new: 8 tests.
- `docs/epics/EPIC-M1.31-model-promotion-gate.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_model_promotion.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0022_model_promotions`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0021` through `0022` (verified `model_promotions` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **286 passed, 0 failed** (278 pre-existing from `main` + 8 new).
- `pytest -v tests/test_model_promotion.py`: **8 passed** — a `VALIDATED` comparison is `PROMOTED`; a `REGRESSED` one and an `INSUFFICIENT_EVIDENCE` one are each `REJECTED` with the matching reason; a comparison that is `VALIDATED` overall but has one horizon collapsing from 80% to 20% success is correctly `REJECTED` with `CRITICAL_HORIZON_REGRESSION` despite the passing top-level verdict; the identical horizon regression is correctly *ignored* (and promotion proceeds) when either side already flagged that horizon `INSUFFICIENT_SAMPLE`; a direct mutation attempt after creation raises `ModelPromotionImmutableError`; the "current production model" correctly tracks only the latest *promoted* version even after a later rejected candidate is evaluated; and the full promotion history preserves every decision, including rejected ones, queryable by candidate version.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] No candidate becomes production without passing every mandatory gate (three checks, any one rejects).
- [x] Promotion decision is reproducible from stored evidence (pure function of the M1.30 comparison).
- [x] Previous production version remains recoverable (the prior `PROMOTED` row, never deleted).
- [x] Failed candidates are retained as rejected versions with reasons (`DECISION_REJECTED` rows with a specific `decision_reason`, never deleted).
- [x] Promotion history is immutable (`before_update` guard, proven by test).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip. The additional critical-horizon-regression check is this EPIC's own genuinely new contribution beyond simply consuming M1.30's top-level verdict, and is directly tested in both directions (blocking when it should, correctly ignored when sample size doesn't support the comparison). Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
