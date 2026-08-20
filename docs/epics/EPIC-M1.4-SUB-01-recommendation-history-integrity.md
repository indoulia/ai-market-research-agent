# EPIC-M1.4-SUB-01 — Recommendation History Integrity

**Parent EPIC:** EPIC-M1.4  
**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P0

## Context

EPIC-M1.4 was implemented in PR #10 and was merged to `main` before ChatGPT's strict review. The implementation protects immutable recommendation fields through a SQLAlchemy `before_update` listener, but the review identified that this is an ORM-level guard rather than a persistence/database integrity boundary.

PR #10 is already merged. Therefore this remediation MUST NOT attempt to update PR #10. It must be implemented as a new branch and PR against the current `main`.

## Target

- Original implementation PR: **#10**
- Original branch: `autonomous/epic-m1-4`
- Remediation target: **current `main`**
- New implementation branch: Claude should create an `autonomous/epic-m1-4-sub-01` branch (or repository-equivalent naming).
- New PR: required.

## Objective

Strengthen recommendation-history integrity so the original recommendation fields cannot be silently modified through supported persistence paths beyond the specific ORM event listener.

## Scope

1. Define exactly which recommendation fields are immutable after issuance.
2. Enforce immutability at the persistence/database boundary appropriate to the repository's PostgreSQL architecture.
3. Keep outcome/status fields mutable for M1.5.
4. Add tests demonstrating that supported persistence paths cannot alter immutable recommendation fields.
5. Preserve the existing M1.4 API and data model unless a minimal change is required.
6. Update this EPIC's Completion Report on the implementation PR.

## Non-goals

- Rewriting M1.4.
- Creating a duplicate recommendation table.
- Implementing M1.5 outcome evaluation.
- Changing recommendation-generation logic.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Immutable recommendation fields are explicitly documented.
- [ ] Integrity is enforced at the persistence/database boundary, not solely by the existing ORM event listener.
- [ ] M1.5 can still update outcome/status fields without changing the original recommendation.
- [ ] Tests demonstrate the integrity protection through the supported persistence path.
- [ ] Existing M1.4 behavior remains compatible.
- [ ] New PR is based on current `main` and passes all required validation.
- [ ] Completion Report is populated in this EPIC before PR review.

## Execution Rules

- Work from current `origin/main`.
- Do not modify the already-merged PR #10 branch.
- Create a new remediation branch and PR.
- Do not merge until ChatGPT strict review passes.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.4-SUB-01

### Parent EPIC

EPIC-M1.4

### Pull Request

To be recorded once opened; Claude does not merge PRs (see the corrected top-level contract).

### Branch

autonomous/epic-m1-4-sub-01

### Implementation Commit

Recorded once committed on this branch.

### Objective

Enforce recommendation-field immutability at the PostgreSQL database boundary (a trigger), not solely through the existing SQLAlchemy `before_update` ORM listener, while keeping `status` mutable for M1.5.

### Implemented

- Added migration `0006_predictions_trigger` creating a PL/pgSQL trigger function `predictions_enforce_immutability()` and a `BEFORE UPDATE` trigger `predictions_immutability_trigger` on the `predictions` table. The trigger compares `OLD`/`NEW` for every field in the same immutable-field list already defined in `app/recommendations.py.IMMUTABLE_FIELDS` (`stock_id`, `created_at`, `as_of_timestamp`, `entry_price`, `horizon_days`, `target_return`, `stop_return`, `predicted_probability`, `confidence`, `model_version`, `feature_version`) and raises a PostgreSQL exception if any changed, regardless of how the `UPDATE` was issued — raw SQL, `Session.execute(text(...))`, or an ORM bulk `Query.update()`, all of which bypass the per-instance `before_update` mapper event that was the sole guard before this EPIC.
- `status` is deliberately excluded from the trigger's comparison, exactly as it already was in the ORM listener, so M1.5's `OPEN -> EVALUATED` transition keeps working unchanged.
- Kept the existing `app/recommendations.py` ORM-level listener as-is (not removed) — it still gives a fast, friendly Python-level error (`RecommendationImmutableError`) for the common ORM-mediated update path, with the new trigger now providing the actual persistence-boundary guarantee for every path, per the review finding ("supplement", not necessarily replace).
- Added `tests/test_recommendation_history_db_integrity.py` (3 tests) that exercise the trigger specifically through paths the ORM listener cannot see: a raw `text("UPDATE predictions SET entry_price = ...")`, and an ORM bulk `session.query(Prediction).filter(...).update({...})`, both of which the trigger correctly rejects; plus a raw SQL `status` update, which still succeeds. These tests require a live PostgreSQL connection (the trigger is Postgres-specific PL/pgSQL) and skip gracefully via `pytest.skip` when one isn't reachable — e.g., in this repo's CI, which does not provision a Postgres service. They were run and verified passing against this development machine's local PostgreSQL instance (via a disposable scratch database created and dropped per test session).
- Minor unrelated-but-adjacent fix: added `path_separator = os` to `alembic.ini` to silence a `DeprecationWarning` that only surfaces when invoking Alembic's `Config`/`command` API directly from Python (as the new test does) rather than via its CLI.

### Files Changed

- `migrations/versions/0006_predictions_trigger.py` — new: the immutability-enforcing trigger and function.
- `tests/test_recommendation_history_db_integrity.py` — new: 3 tests proving DB-boundary enforcement across non-ORM persistence paths.
- `alembic.ini` — added `path_separator = os` (removes a deprecation warning; no behavior change).
- `docs/epics/EPIC-M1.4-SUB-01-recommendation-history-integrity.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- Migration validation against a disposable scratch Postgres database (`market_agent_sub01_check`, created and dropped for this validation only): `0001_initial` → `0002_upstox_instrument_key` for real, `alembic stamp 0003_market_price_dedupe` (still the pre-existing broken migration from EPIC-M1.4/SUB-02, worked around the same documented way), then `alembic upgrade head` (runs `0004`, `0005`, and the new `0006` for real). Verified the trigger and function exist via `information_schema.triggers`/`pg_proc`, then `alembic downgrade -1` and re-verified both were dropped.

### Test Results

- `pytest -q`: **23 passed** on this branch (20 present here from `main` post-M1.4 + 3 new in `tests/test_recommendation_history_db_integrity.py`; this branch does not include M1.5's tests since PR #14/M1.5 is a separate, still-unmerged branch), 2.27–2.41s across runs.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration `0006` upgrade: applied cleanly; `predictions_immutability_trigger` (UPDATE) and `predictions_enforce_immutability()` both present.
- Migration `0006` downgrade: applied cleanly; both removed.
- The 3 new integration tests were confirmed to actually exercise the trigger (not silently skipped) — this machine's local PostgreSQL instance is reachable, so the `pytest.skip` fallback path was not taken during this validation run.

### Acceptance Criteria

- AC-1 "Immutable recommendation fields are explicitly documented": PASS. Evidence: the exact field list is defined once in `app/recommendations.py.IMMUTABLE_FIELDS` and the trigger migration reuses the identical list (with a comment cross-referencing it), so there is a single documented source of truth, not two independently-maintained lists.
- AC-2 "Integrity is enforced at the persistence/database boundary, not solely by the existing ORM event listener": PASS. Evidence: `test_bulk_orm_update_rejects_immutable_field_change` and `test_raw_sql_update_rejects_immutable_field_change` both use persistence paths that bypass the ORM's `before_update` mapper event entirely, and both are rejected by the new PostgreSQL trigger.
- AC-3 "M1.5 can still update outcome/status fields without changing the original recommendation": PASS. Evidence: `test_raw_sql_update_still_allows_status_change` updates `status` via raw SQL against the live trigger and succeeds; M1.5's existing `evaluate_recommendation` (which sets `prediction.status = "EVALUATED"` via the ORM) is unaffected since `status` was never in the trigger's guarded column list.
- AC-4 "Tests demonstrate the integrity protection through the supported persistence path": PASS. Evidence: the 3 new tests, run against a real PostgreSQL instance (not mocked), all passing.
- AC-5 "Existing M1.4 behavior remains compatible": PASS. Evidence: all 20 pre-existing tests on this branch (unchanged from post-M1.4 `main`) still pass; the ORM-level `RecommendationImmutableError` listener was not modified or removed.
- AC-6 "New PR is based on current `main` and passes all required validation": PASS (with a caveat — see Unexpected Findings below about migration-numbering collision risk with PR #14, which is about merge ordering, not this branch's own validity against current `main`). Evidence: branch forked from `origin/main` at commit `35ecade` (the current `main` tip at the time of writing, after PR #11 merged); `pytest`/`compileall`/`git diff --check` all pass.
- AC-7 "Completion Report is populated in this EPIC before PR review": PASS — this report.

### Validation

Ran the real local test suite and independently validated the new migration applies and reverses cleanly against a disposable scratch PostgreSQL database, consistent with the standard set in EPIC-M1.4/M1.5. Additionally verified — by actually connecting to a live PostgreSQL instance rather than mocking it — that the trigger genuinely rejects non-ORM persistence paths, which is the entire point of this remediation EPIC.

### Known Limitations

- The new database-integrity tests only run when a live PostgreSQL connection is reachable; they skip (not fail) in environments without one, including this repo's current CI (`.github/workflows/test.yml`), which sets a `DATABASE_URL` but provisions no Postgres service. This means CI cannot currently prove the trigger works — only this local run can, and it did. EPIC-M1.4-SUB-02's scope ("Add migration validation to automated tests/CI if practical and bounded") would be the natural place to add a Postgres service to CI so tests like these run there too.
- As in prior EPICs, the shared local dev database (`market_agent`) was not touched; only disposable scratch databases were used for all validation in this EPIC.

### Unexpected Findings

- **Migration-numbering collision with PR #14 (EPIC-M1.5), not fixed here**: this branch forks from `main` immediately after EPIC-M1.4 merged (commit `35ecade`), before EPIC-M1.5 (PR #14) exists in `main`. The current migration head on `main` is `0005_prediction_confidence`. This EPIC's new migration is `0006_predictions_trigger`, chaining from `0005`. PR #14 also already defines its own `0006_outcome_actual_return`, chaining from the same `0005` head. Whichever of these two PRs merges **second** will have a migration-history conflict (two different revisions both claiming `down_revision=0005_prediction_confidence`) and will need to renumber its migration to `0007` with an updated `down_revision` pointing at whichever `0006` merged first, then re-run migration validation. This is flagged here rather than resolved, since resolving it depends on merge order, which is now outside Claude's control (Claude does not merge PRs per the corrected contract). Recommend: merge one of PR #14 / this PR first, then have the other's author (or a small follow-up commit) renumber before merging.
- Confirmed again that `alembic.Config`/`command.upgrade` invoked directly from Python (rather than via the Alembic CLI) needs `path_separator = os` in `alembic.ini` to avoid a deprecation warning on `prepend_sys_path` parsing — fixed as a minor, directly-related adjacent change since this EPIC's tests are the first in the repo to invoke Alembic that way.

### Architectural Observations

- The immutable-field list now genuinely has one source of truth (`app/recommendations.py.IMMUTABLE_FIELDS`), with the migration's `_IMMUTABLE_COLUMNS` tuple manually kept in sync via an explicit code comment cross-reference — there is no automated enforcement that the two stay identical if either is edited independently in the future. If EPIC-M1.4-SUB-03 (model timestamp portability) or any future EPIC touches these fields again, keep both lists in sync by hand, or consider (as a future improvement, not implemented here) generating the trigger's column list from the Python constant at migration-authoring time.
- This same "ORM listener + DB trigger" pattern could reasonably be applied to `PredictionOutcome`'s immutability guarantee (added in M1.5, currently ORM-listener-only) if the same database-boundary concern applies there — not addressed in this EPIC since its scope is explicitly recommendation history (M1.4), not outcome evaluation (M1.5), which is an independent, still-unmerged PR.

### Recommended Follow-up

- Resolve the migration-numbering collision with PR #14 once merge order is known (see Unexpected Findings).
- Consider extending the same database-boundary immutability pattern to `PredictionOutcome` (M1.5) in a future EPIC, if that boundary-strength concern applies there too.
- Consider adding a Postgres service to CI (`.github/workflows/test.yml`) so tests like this EPIC's `test_recommendation_history_db_integrity.py` and the migration chain itself can be validated in CI instead of only locally — natural fit for EPIC-M1.4-SUB-02's scope.
- Suggestions only; not implemented as part of this EPIC.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence (including actually exercising a live PostgreSQL trigger, not just asserting on mocks). The migration-numbering collision with PR #14 is a real, disclosed risk that whoever merges second must resolve — I flagged it rather than guessing at merge order. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

### Review 1 — REJECTED / REMEDIATION REQUIRED

Reviewer: ChatGPT  
Original PR: #10  
Original PR status: MERGED before strict review

Finding:

The implementation's immutability guarantee is enforced through a SQLAlchemy `before_update` listener. That is insufficient as the sole integrity boundary for a historical trust/evidence record.

Required remediation:

Move or supplement the guarantee at the persistence/database boundary while preserving mutable outcome/status fields.

**Resolution path:** New PR required because PR #10 has already merged.
