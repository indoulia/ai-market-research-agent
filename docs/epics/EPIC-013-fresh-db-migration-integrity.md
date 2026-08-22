# EPIC-013 — Fresh Database Migration Integrity

**Parent EPIC:** EPIC-004  
**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1

## Context

The EPIC-004 completion report identified a pre-existing failure in `migrations/versions/0003_market_price_dedupe.py`: a relation/index name conflicts with the unique constraint created by `0001_initial`. This prevents a clean `alembic upgrade head` on a fresh database.

EPIC-004 has already merged via PR #10. This remediation is independent of PR #10 and MUST be implemented as a new branch/PR against current `main`.

## Objective

Make a completely fresh PostgreSQL database migrate successfully to the current Alembic head without manually stamping past a broken migration.

## Scope

1. Inspect the migration chain and identify the exact `0003` conflict.
2. Apply the smallest safe migration-history correction.
3. Preserve the intended `market_prices` uniqueness behavior.
4. Validate upgrade from an empty database to head.
5. Validate downgrade/upgrade behavior where appropriate.
6. Add migration validation to automated tests/CI if practical and bounded.

## Non-goals

- General database redesign.
- Changing recommendation behavior.
- Rewriting unrelated migrations.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Fresh PostgreSQL database can run `alembic upgrade head` without manual stamping/skipping.
- [ ] Intended `market_prices` uniqueness behavior remains intact.
- [ ] Migration history remains coherent.
- [ ] Relevant migration validation is automated where practical.
- [ ] Existing application tests remain green.
- [ ] Completion Report is populated in this EPIC before PR review.

## Dependencies

- EPIC-012 should be completed first to preserve one-EPIC-at-a-time execution.

## Execution Rules

Do not execute while `Execution Status: BLOCKED`. After SUB-01 merges successfully, ChatGPT will authorize this EPIC by changing its execution status to `READY_FOR_EXECUTION`.

**Authorization note:** SUB-01 merged (squash-merge commit `54cc029`, confirmed on `main`). This EPIC was then directly authorized for immediate execution by the human product owner in-session, ahead of the usual separate ChatGPT approval commit. Execution Status above was flipped to `READY_FOR_EXECUTION` as part of this authorization.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-013

### Parent EPIC

EPIC-004

### Branch

autonomous/epic-m1-4-sub-02

### Objective

Make a completely fresh PostgreSQL database migrate to the current Alembic head via a real `alembic upgrade head`, with no manual stamping past the broken `0003_market_price_dedupe` migration.

### Root Cause

`migrations/versions/0001_initial.py` creates `market_prices` with a table-level `UniqueConstraint("stock_id", "timestamp", name="uq_market_prices_stock_timestamp")`. PostgreSQL backs a named unique constraint with an identically-named index automatically. `migrations/versions/0003_market_price_dedupe.py`'s original body then called `op.create_index("uq_market_prices_stock_timestamp", "market_prices", ["stock_id", "timestamp"], unique=True)` — attempting to create a second index under that exact same name. On a genuinely fresh database this always fails with `relation "uq_market_prices_stock_timestamp" already exists`; no environment has ever successfully applied this migration's original body. Every prior validation (EPIC-004, EPIC-012) worked around the failure with `alembic stamp 0003_market_price_dedupe` instead of actually running it.

### Implemented

- `migrations/versions/0003_market_price_dedupe.py`: changed `upgrade()`/`downgrade()` to documented no-ops. The uniqueness this migration intended (`one candle per stock per day`) is already fully enforced by `0001_initial`'s constraint, so no schema change is needed — this is the smallest safe correction. Added an in-file docstring explaining why, so a future reader doesn't mistake the no-op for an oversight.
- `tests/test_recommendation_history_db_integrity.py`: removed the `command.stamp(cfg, "0003_market_price_dedupe")` workaround from the scratch-DB fixture; it now runs a plain `command.upgrade(cfg, "head")`, since that now succeeds unaided.
- `tests/test_fresh_database_migration.py` (new): three tests against a live, disposable scratch PostgreSQL database (created and dropped per test, following the SUB-01 pattern; skips gracefully via `pytest.skip` when Postgres isn't reachable, e.g. in this repo's CI):
  1. A truly fresh database reaches `head` (`0007_outcome_actual_return`) via `alembic upgrade head` alone — no stamping.
  2. The intended `market_prices` uniqueness behavior is still enforced post-fix: inserting a second row with the same `(stock_id, timestamp)` raises `IntegrityError`.
  3. A full `downgrade("base")` → `upgrade("head")` round trip completes cleanly, exercising every revision boundary including the fixed no-op `0003`.
- Automated migration validation now lives directly in the test suite (`pytest`), satisfying "add migration validation to automated tests/CI if practical and bounded" without a new CI Postgres service, matching the existing SUB-01 precedent rather than introducing new CI infrastructure out of scope for this EPIC.

### Files Changed

- `migrations/versions/0003_market_price_dedupe.py` — fixed: no-op with root-cause documentation.
- `tests/test_recommendation_history_db_integrity.py` — removed the now-unnecessary stamp workaround.
- `tests/test_fresh_database_migration.py` — new: 3 tests proving fresh-DB migration integrity.
- `docs/epics/EPIC-013-fresh-db-migration-integrity.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_fresh_database_migration.py tests/test_recommendation_history_db_integrity.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`

### Test Results

- `pytest -q`: **40 passed**, 4.05s (37 pre-existing + 3 new in `test_fresh_database_migration.py`).
- Targeted verbose run of the fresh-DB and DB-integrity suites: **6 passed**, 2.98s — confirmed none were silently skipped (this machine's local PostgreSQL is reachable, so the `pytest.skip` fallback was not taken).
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Also found and dropped one leftover scratch database (`market_agent_sub01_90f21b1d`) from a prior session's SUB-01 test run that hadn't been cleaned up — unrelated to this EPIC's changes but flagged here since it was noticed during validation.

### Acceptance Criteria

- [x] Fresh PostgreSQL database can run `alembic upgrade head` without manual stamping/skipping.
- [x] Intended `market_prices` uniqueness behavior remains intact.
- [x] Migration history remains coherent.
- [x] Relevant migration validation is automated where practical (test-suite-based, not CI-Postgres-based).
- [x] Existing application tests remain green.
- [x] Completion Report is populated in this EPIC before PR review.

### Claude Assessment

I believe this implementation satisfies all acceptance criteria with real, verified evidence — a live PostgreSQL instance actually ran `alembic upgrade head` on a brand-new database with no stamping, actually rejected a duplicate `(stock_id, timestamp)` insert, and actually round-tripped a full downgrade/upgrade. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

### Finding Origin

Discovered during EPIC-004 implementation validation and recorded in PR #10's completion report. PR #10 has since merged.

### Review State

Authorized for immediate execution by the human product owner; implemented in this branch. Awaiting reviewer sign-off before merge.
