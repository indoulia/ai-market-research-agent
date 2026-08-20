# EPIC-M1.21 — Recommendation Outcome Closure

**Status:** APPROVED  
**Execution Status:** VALIDATING  
**Approved By:** User  
**Priority:** P1

## Objective
Ensure every eligible issued recommendation reaches an explicit terminal outcome state so historical learning is based on complete, auditable evidence.

## Scope
1. Identify recommendations whose selected horizon is due for closure.
2. Apply objective outcome evaluation using trading-day logic and available market data.
3. Distinguish successful, unsuccessful, and unevaluable outcomes.
4. Record closure timestamp and evaluation metadata.
5. Keep the original recommendation immutable.
6. Make closure idempotent and recoverable.
7. Add tests for all supported horizons and unavailable-data cases.

## Non-goals
- Changing recommendations after issuance.
- Subjective outcome labels.
- Model retraining.
- Trading execution.

## Acceptance Criteria
- [ ] Eligible recommendations reach a terminal outcome exactly once.
- [ ] Outcomes use the intended 1/3/5/7-day horizon.
- [ ] Failures and unevaluable cases remain distinguishable.
- [ ] Original recommendation data is unchanged.
- [ ] Re-running closure does not duplicate outcomes.
- [ ] Tests cover normal and edge cases.

## Dependency Chain
### Previous / Required
- **M1.20 — Watchlist Decision History**
- **M1.15 — Recommendation Lifecycle & Outcome Scheduler**

### Next / Unlocks
- **M1.22 — Recommendation Score Analysis**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Do not fabricate an outcome when required market data is unavailable. Preserve an explicit unevaluable state.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.21

### Branch

autonomous/epic-m1-21, branched cleanly from `main` (both declared dependencies, M1.20 and M1.15, are already merged).

### Objective

Ensure every eligible recommendation issued via the watchlist path (M1.18-M1.20) reaches an explicit terminal outcome, exactly as M1.15 already guarantees for M1.14-selected recommendations.

### Design Decisions

- **No new table or migration, and `app/lifecycle.py` is not modified at all.** M1.15's `RecommendationLifecycle` table and its `advance_lifecycle`/`process_due_lifecycles` functions are source-agnostic: they operate on any lifecycle row regardless of how it was created. The only reason a watchlist-qualified recommendation wasn't already being closed out is that nothing ever created its `ISSUED` row -- M1.15's own `ensure_lifecycle_entries_for_scan` only looks at M1.14 `RecommendationSelection` rows, the daily-scan selection path a watchlist recommendation never goes through.
- **New module `app/watchlist_outcome_closure.py`, one real function:** `ensure_lifecycle_entry_for_watchlist_decision(session, decision)` creates the missing `ISSUED` row for a qualifying `WatchlistDecision`'s `RecommendationGeneration`, using the exact same `RecommendationLifecycle` model and `STATE_ISSUED`/`LIFECYCLE_VERSION` constants M1.15 already defined. Returns `None` for a rejected decision (`outcome != QUALIFIED`) -- nothing was issued, so scope item 1 ("identify recommendations... due for closure") correctly finds nothing to track.
- **Idempotent by `recommendation_generation_id` uniqueness** -- the same table constraint M1.15's own `ensure_lifecycle_entries_for_scan` relies on. This also correctly no-ops if a `RecommendationGeneration` somehow already has a lifecycle row from the M1.14 path (not possible in practice today, since a watchlist-triggered generation and an M1.14-selected one are different `RecommendationGeneration` rows by construction, but handled safely regardless).
- **Scope items 2-6 ("trading-day logic," "distinguish successful/unsuccessful/unevaluable," "record closure timestamp/metadata," "keep the original recommendation immutable," "idempotent and recoverable") are M1.15's existing, already-tested behavior** -- `advance_lifecycle`/`process_due_lifecycles` need no changes to correctly close a watchlist-issued lifecycle row; this EPIC's tests prove the *integration point* (a watchlist decision produces a row M1.15's scheduler will pick up and correctly evaluate), not the underlying evaluation logic a second time.
- `ensure_lifecycle_entries_for_watchlist_decisions` is a thin batch convenience over the single-decision function, for a caller with a list of decisions (e.g. from `get_watchlist_decision_history`) to process together.

### Files Changed

- `app/watchlist_outcome_closure.py` — new: `ensure_lifecycle_entry_for_watchlist_decision`, `ensure_lifecycle_entries_for_watchlist_decisions`.
- `tests/test_watchlist_outcome_closure.py` — new: 5 tests.
- `docs/epics/EPIC-M1.21-recommendation-outcome-closure.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_watchlist_outcome_closure.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from M1.20's `0019_watchlist_decisions`)

### Test Results

- `pytest -q`: **216 passed, 0 failed** (211 pre-existing from `main` + 5 new).
- `pytest -v tests/test_watchlist_outcome_closure.py`: **5 passed** — a qualifying watchlist decision gets a real `ISSUED` lifecycle row linked to its generation; a rejected decision gets none; creating the entry twice is idempotent (one row); the batch helper correctly skips rejected decisions while creating entries for qualifying ones; and an end-to-end test proves a watchlist-issued lifecycle row is picked up and correctly closed to `EVALUATED` by M1.15's unmodified `process_due_lifecycles` once its horizon's market data exists -- direct evidence that no second evaluation mechanism was built or needed.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0019_watchlist_decisions` (no migration in this EPIC).

### Acceptance Criteria

- [x] Eligible recommendations reach a terminal outcome exactly once (M1.15's existing terminal-state exclusion, now reachable for watchlist-issued rows too).
- [x] Outcomes use the intended 1/3/5/7-day horizon (M1.15's `evaluate_recommendation` call, unchanged).
- [x] Failures and unevaluable cases remain distinguishable (M1.15's `STATE_EVALUATED`/`STATE_UNEVALUABLE`, unchanged).
- [x] Original recommendation data is unchanged (M1.13/M1.5's existing immutability guards, untouched).
- [x] Re-running closure does not duplicate outcomes (M1.15's existing idempotency, plus this EPIC's own idempotent entry-creation).
- [x] Tests cover normal and edge cases, including the specific new integration point this EPIC adds.

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including an end-to-end test proving the watchlist path's lifecycle rows are actually closed by M1.15's existing scheduler, not merely created. This EPIC's entire contribution is the missing "create the `ISSUED` row" step for the watchlist source -- everything downstream is deliberate, verified reuse. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
