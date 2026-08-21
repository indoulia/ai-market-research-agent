# EPIC-M1.79 — Horizon & Regime-Specific Trust

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Measure prediction trust separately by forecast horizon and market regime so MRA can publish stronger opportunities only where its historical evidence supports them.

## Scope
- Maintain trust by 1/2/3/5/7 trading-day horizon.
- Maintain trust by supported market regime.
- Combine horizon and regime evidence when sample sizes permit.
- Preserve sample size and uncertainty.
- Feed trust into positive-only recommendation gating.
- Recalculate as new outcomes arrive without rewriting historical trust.

## Acceptance Criteria
- Trust can differ by horizon and regime.
- Insufficient samples are explicit.
- Historical values remain immutable.
- Low-trust combinations can suppress recommendations.
- Tests cover horizon/regime boundaries and sparse data.

## Dependency Chain
**Previous:** M1.77, M1.78, M1.26.
**Next:** M1.80, M1.81, M1.84.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.79

### Branch

autonomous/epic-m1-79, branched cleanly from `main` (the declared dependencies -- M1.77, M1.78, M1.26 -- are already merged).

### Objective

Measure prediction trust separately by forecast horizon and market regime so this platform can publish stronger opportunities only where its historical evidence supports them.

### Design

A genuinely different lens than M1.77's `PredictionTrustScore`, not a duplicate: M1.77 blends horizon reliability (M1.75) and regime reliability (M1.41) into ONE composite number per prediction; `app/horizon_regime_trust.py` keeps them -- and their combination -- as separate, independently queryable segments (AC: "trust can differ by horizon and regime"). `segment_type` (`HORIZON`/`REGIME`/`COMBINED`) is inferred from which of `horizon_days`/`regime` the caller supplies; `COMBINED` requires both and is gated by exactly the same minimum-sample floor as the other two, never computed from a smaller slice just because it looks more specific.

### Sample Size And Uncertainty Preserved

Every segment persists its own `sample_count` and a standard binomial standard error (`sqrt(p*(1-p)/n)`) alongside `success_rate` -- a real, simple, well-known uncertainty measure, not a fabricated confidence claim. Below `MIN_SAMPLE_SIZE_FOR_COMPARISON`, the verdict is explicitly `VERDICT_INSUFFICIENT_SAMPLE` and both fields stay `None` (AC: "insufficient samples are explicit"; "sparse segments are marked insufficient rather than overfit").

### An Honest Constraint Discovered While Testing

This platform only ever generates a real `Prediction` for a positive (upward-trending) candidate (M1.9/M1.13's "positive-only" qualification), so a `BEARISH_*` regime segment can never have real evaluated evidence here -- the same honest, forward-compatible constraint already established for M1.10's never-populated horizon day 2 and M1.46's MEDIUM/LONG bands. `test_a_different_regime_is_isolated` instead proves cross-segment isolation using two regimes that genuinely can both occur for positive candidates (differing volatility bands).

### Feeds A Future Gate, Enforces Nothing Itself

`is_low_trust` is exposed for a future gate (M1.81, not yet built) to consume -- this module has no write path to `Prediction`/`ScanCandidate`/any selection table, matching this platform's established propose/gate split (M1.65, M1.74, M1.77).

### Immutable And Reproducible

Append-only, immutable after creation, and deterministic given the same underlying evaluated-prediction history (AC: "historical values remain immutable"; "historical segment trust remains reconstructable").

### Files Changed

- `app/horizon_regime_trust.py` — new: `compute_horizon_regime_trust`, `get_trust_history`, `get_latest_trust`, constants.
- `app/models.py` — new `HorizonRegimeTrust` model.
- `migrations/versions/0059_horizon_regime_trust.py` — new migration.
- `tests/test_horizon_regime_trust.py` — new: 10 tests.
- `docs/epics/EPIC-M1.79-horizon-regime-specific-trust.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_horizon_regime_trust.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0059_horizon_regime_trust`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0058` through `0059` (verified `horizon_regime_trusts` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **692 passed, 0 failed**.
- `test_horizon_regime_trust.py`: **10 passed** — missing both dimensions raises; horizon-only, regime-only, and combined segments each correctly gate on sample size and compute hand-verified success rate/standard error/low-trust flag; two different, both-achievable regimes are correctly isolated from each other; history and "latest" lookups behave correctly; trust rows are immutable; the module never writes to `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Trust can differ by horizon and regime (`HorizonRegimeTrust` per segment; proven by test).
- [x] Insufficient samples are explicit (`VERDICT_INSUFFICIENT_SAMPLE`).
- [x] Historical values remain immutable (`before_update` guard; proven by test).
- [x] Low-trust combinations can suppress recommendations (`is_low_trust` exposed for a future gate to consume).
- [x] Tests cover horizon/regime boundaries and sparse data.

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a hand-verified exact statistical result for a sufficient-sample segment. This EPIC composes M1.26's regime classification and the same evaluated-prediction history M1.77 reads, without duplicating M1.77's own blended composite, and never enforces suppression itself -- only makes the signal available for a future gate. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
