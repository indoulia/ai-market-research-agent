# EPIC-M1.4-SUB-03 — Model Timestamp Portability

**Parent EPIC:** EPIC-M1.4  
**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P2

## Context

The M1.4 completion report identified literal `server_default="now()"` values in several SQLAlchemy models. This is dialect-fragile and prevents clean SQLite fixture use for affected models.

M1.4 has already merged via PR #10. This remediation is independent of PR #10 and MUST be implemented as a new branch/PR against current `main`.

## Objective

Make model timestamp defaults dialect-portable without changing PostgreSQL behavior or broadening the work into unrelated model refactoring.

## Scope

1. Identify affected model timestamp defaults.
2. Replace literal/dialect-fragile defaults with the repository's appropriate SQLAlchemy expression.
3. Preserve migration/schema semantics.
4. Add focused tests for affected model timestamp behavior under the repository's supported test dialects.
5. Keep the change minimal and isolated.

## Non-goals

- General model refactoring.
- Recommendation logic changes.
- Database migration redesign beyond what is strictly required.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Affected model timestamp defaults are dialect-portable.
- [ ] PostgreSQL behavior remains correct.
- [ ] SQLite fixture behavior works without special workarounds.
- [ ] Tests cover affected models.
- [ ] No unrelated model behavior changes.
- [ ] Completion Report is populated in this EPIC before PR review.

## Dependencies

- EPIC-M1.4-SUB-01 should be completed first to preserve one-EPIC-at-a-time execution.
- EPIC-M1.4-SUB-02 should be completed before this EPIC unless ChatGPT explicitly changes the ordering.

## Execution Rules

Do not execute while `Execution Status: BLOCKED`. ChatGPT will authorize execution after the prerequisite remediation work is complete.

**Authorization note:** SUB-01 merged (squash-merge commit `54cc029`) and SUB-02 was implemented and opened as a PR in this same session (branch `autonomous/epic-m1-4-sub-02`, not yet merged at the time this EPIC was implemented). This EPIC was directly authorized for immediate execution by the human product owner in-session, ahead of the usual separate ChatGPT approval commit. Execution Status above was flipped to `READY_FOR_EXECUTION` as part of this authorization. This EPIC's changes do not depend on SUB-02's changes at the code level (no shared files, no migrations added by either) and do not conflict with it — both can merge in either order.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.4-SUB-03

### Parent EPIC

EPIC-M1.4

### Branch

autonomous/epic-m1-4-sub-03

### Objective

Make model timestamp defaults dialect-portable so a genuinely fresh SQLite fixture (`Base.metadata.create_all`) can rely on `created_at`/`updated_at` server defaults, without changing PostgreSQL behavior.

### Root Cause

`app/models.py` declared `server_default="now()"` (a plain Python string) on five columns across four models (`Stock.created_at`, `Stock.updated_at`, `DatasetValidationRun.created_at`, `Prediction.created_at`, `ModelVersion.created_at`). A plain string passed to `server_default` is stored as a literal SQL default clause verbatim rather than compiled per-dialect. Reproduced directly: on SQLite this stores the literal text `"now()"` as the column's value on insert, which then fails with `ValueError("Invalid isoformat string: 'now()'")` when SQLAlchemy's `DateTime` type tries to parse it back as a Python `datetime`. On PostgreSQL, `now()` happens to also be a valid function call, which is why this was never noticed there — but this string was never actually driving PostgreSQL DDL in the first place: the real Postgres schema comes from the Alembic migrations (`migrations/versions/0001_initial.py`, `0005_prediction_confidence.py`), which already correctly use `sa.func.now()`. `app/models.py`'s `server_default` is only exercised when tests build tables directly via `Base.metadata.create_all()` against SQLite.

### Implemented

- `app/models.py`: replaced all five `server_default="now()"` occurrences with `server_default=func.now()` (added `func` to the existing `sqlalchemy` import). `func.now()` compiles to `CURRENT_TIMESTAMP` on SQLite and `now()` on PostgreSQL, matching what the migrations already do.
- `tests/test_model_timestamp_portability.py` (new, 10 tests):
  - Parametrized over all four affected models: compiles each model's `CREATE TABLE` DDL under the SQLite dialect and asserts `CURRENT_TIMESTAMP` appears (and the literal string `now()` does not); and under the PostgreSQL dialect, asserts `now()` appears — proving the per-dialect compilation directly at the DDL level for every affected column, independent of any unrelated model quirks.
  - Two end-to-end tests using `Stock` and `Prediction` (via `Base.metadata.create_all` on an in-memory SQLite engine): insert a row without specifying `created_at`/`updated_at` and confirm a real Python `datetime` comes back, reproducing exactly the "clean SQLite fixture use" scenario this EPIC targets.
- Deliberately did not attempt an end-to-end insert test for `DatasetValidationRun`/`ModelVersion`: both use a plain `BigInteger` primary key, which does not get SQLite's rowid-alias autoincrement behavior (the same pre-existing, unrelated quirk already documented in `Prediction`'s own model comment for exactly this reason). No existing test in the suite exercises ORM inserts against those two models, so this is not a regression and fixing it is out of this EPIC's scope (non-goal: "General model refactoring"). The DDL-level compile tests still fully cover their timestamp-default portability.

### Files Changed

- `app/models.py` — `server_default="now()"` → `server_default=func.now()` on 5 columns; added `func` import.
- `tests/test_model_timestamp_portability.py` — new: 10 tests covering DDL compilation (all 4 models) and end-to-end SQLite inserts (`Stock`, `Prediction`).
- `docs/epics/EPIC-M1.4-SUB-03-model-timestamp-portability.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_model_timestamp_portability.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- Manual reproduction before the fix (ad hoc script): confirmed `ValueError("Invalid isoformat string: 'now()'")` on a bare `Stock` insert against SQLite; confirmed the same insert succeeds and returns a real `datetime` after the fix.

### Test Results

- `pytest -q`: **47 passed**, 3.52s (37 pre-existing on `main` + 10 new in `test_model_timestamp_portability.py`; this branch does not include SUB-02's 3 fresh-database-migration tests since that is a separate, still-unmerged branch).
- `pytest -v tests/test_model_timestamp_portability.py`: **10 passed** — all pass, none skipped.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).

### Acceptance Criteria

- [x] Affected model timestamp defaults are dialect-portable.
- [x] PostgreSQL behavior remains correct (migrations already used `sa.func.now()`; unaffected by this change).
- [x] SQLite fixture behavior works without special workarounds.
- [x] Tests cover affected models.
- [x] No unrelated model behavior changes.
- [x] Completion Report is populated in this EPIC before PR review.

### Claude Assessment

I believe this implementation satisfies all acceptance criteria with real, verified evidence: reproduced the original failure, applied the minimal fix, and proved both the SQLite and PostgreSQL compiled DDL are correct for every affected column. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

### Finding Origin

Discovered during EPIC-M1.4 implementation validation and recorded in PR #10's completion report. PR #10 has since merged.

### Review State

Authorized for immediate execution by the human product owner; implemented in this branch. Awaiting reviewer sign-off before merge.
