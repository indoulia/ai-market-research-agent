# EPIC-M1.7 — Watchlist Positive-Sensus Evaluation

**Status:** APPROVED
**Priority:** P1

## Objective

Allow a user-provided stock to be thoroughly evaluated against the positive-recommendation criteria without forcing a recommendation.

## Dependencies

- M1.3 — Yahoo NSE Historical Data Provider
- M1.5 — Evaluate Recommendation Outcomes

## Scope

1. Accept a configured stock as a watchlist candidate.
2. Run the same positive-opportunity evaluation used for discovered candidates.
3. Promote the stock to a positive recommendation only when all required criteria are satisfied.
4. Otherwise place it in backlog with the explicit reason: `NOT MATCHING POSITIVE CONSENSUS`.
5. Record which required criteria failed.
6. Allow later re-evaluation when new market data is available.

## Acceptance Criteria

- [ ] A user-provided stock can be evaluated independently of market-wide discovery.
- [ ] The same objective positive criteria are applied.
- [ ] A qualifying stock becomes a positive recommendation candidate.
- [ ] A non-qualifying stock enters backlog rather than receiving a negative recommendation.
- [ ] Backlog records explain the failed criteria.
- [ ] Re-evaluation does not overwrite prior evaluations.
- [ ] Tests cover qualifying and non-qualifying watchlist stocks.

## Non-goals

- Sell/negative recommendations.
- Portfolio management.
- Autonomous trading.
- UI/dashboard work.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.7

### Branch

autonomous/epic-m1-7 (stacked on the still-open `autonomous/epic-m1-8` branch/PR #21 — see undeclared-dependency note below)

### Undeclared dependency on M1.8 (flagged)

This EPIC's own doc lists only M1.3 and M1.5 as dependencies (both already merged into `main`). But scope item 2 requires "run the same positive-opportunity evaluation used for discovered candidates" — and the only such mechanism in this repository is EPIC-M1.8's positive-consensus gate (`app/consensus.py`), which did not exist when this EPIC's dependency list was written. Building a second, parallel qualification mechanism here would directly contradict scope item 2 ("the *same* evaluation"), so this implementation reuses M1.8's `evaluate_positive_consensus`/`record_qualifying_recommendation` and is therefore stacked on `autonomous/epic-m1-8` (PR #21, unmerged) rather than on `main`. Flagging this doc/dependency-list gap for the reviewer rather than silently building a duplicate.

### Objective

Let a user-provided (watchlist) stock be evaluated with exactly the same positive-consensus criteria as market-wide discovery, promoting it to a real recommendation when it qualifies, or placing it in an explicit, explained backlog otherwise — never as a negative/sell recommendation.

### Design Decisions

- **New model `WatchlistEvaluation`** (new table, migration `0009_watchlist_evaluations`, chains off M1.8's `0008_consensus_contract_version`): every evaluation run is its own row — `stock_id`, `evaluated_at`, the `consensus_contract_version` used, `qualifies`, `failed_criteria` (JSON list of criterion names), `outcome` (`PROMOTED`/`BACKLOG`), `backlog_reason`, and `prediction_id` (set only when promoted).
- **`evaluate_watchlist_candidate(session, *, stock_id, evaluated_at, consensus_inputs, recommendation_kwargs)`** is the single entry point: it calls M1.8's `evaluate_positive_consensus` directly (scope item 2's "same evaluation"), then either calls M1.8's `record_qualifying_recommendation` (promoting, scope item 3) or inserts a backlog row with `backlog_reason = "NOT MATCHING POSITIVE CONSENSUS"` (the exact string from scope item 4) and the failed criterion names (scope item 5) — never a negative recommendation of any kind, matching the platform's standing product constraint.
- **Re-evaluation (scope item 6):** the function always inserts a new row and never looks up or updates a prior evaluation for the same stock — repeated calls as new market data arrives naturally accumulate history rather than overwrite it. Added `get_watchlist_history(session, stock_id)` to retrieve that full ordered history.
- **Immutability:** added a `before_update` ORM guard (`WatchlistEvaluationImmutableError`) rejecting any modification to any field on an existing `WatchlistEvaluation` row, mirroring the exact pattern already established for `Prediction` (M1.4) and `PredictionOutcome` (M1.5) — every field is a historical fact about that evaluation run, not just re-evaluation semantics enforced by caller discipline.

### Known 3-way migration-numbering collision (flagged, not fixed here)

This branch, M1.9's (`autonomous/epic-m1-9`, PR #22), and M1.10's (`autonomous/epic-m1-10`, PR #23) are three siblings all stacked on `autonomous/epic-m1-8`, none depending on the others. All three independently added a new migration numbered `0009` chaining off `0008_consensus_contract_version` (M1.9: `0009_opportunity_score`; M1.10: `0009_horizon_selection_version`; this EPIC: `0009_watchlist_evaluations`). Whichever of the three merges **last** will need renumbering (to `0010` or `0011` depending on merge order) with an updated `down_revision`, then re-validation — same pattern as the earlier M1.4-SUB-01/M1.5 collision, resolved once already, now recurring three-way. Resolution depends on merge order, outside Claude's control.

### Files Changed

- `app/watchlist.py` — new: `evaluate_watchlist_candidate`, `get_watchlist_history`, immutability guard.
- `app/models.py` — new `WatchlistEvaluation` model.
- `migrations/versions/0009_watchlist_evaluations.py` — new migration (see collision note above).
- `tests/test_watchlist_evaluation.py` — new: 6 tests.
- `docs/epics/EPIC-M1.7-watchlist-positive-sensus.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -v tests/test_watchlist_evaluation.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- Migration validation against a disposable scratch PostgreSQL database (created and dropped for this validation only): full `upgrade head` through `0009` (verified the `watchlist_evaluations` table and all its columns exist), `downgrade -1` (verified the table is dropped entirely), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **62 passed**, 4.19s (56 pre-existing/M1.8 + 6 new).
- `pytest -v tests/test_watchlist_evaluation.py`: **6 passed** — covers a qualifying stock promoted to a real, queryable `Prediction` row; a non-qualifying stock entering backlog with the exact required reason string and zero `Prediction` rows created; a backlog record correctly listing multiple simultaneous failed criteria by name; re-evaluation of the same stock (backlog, then qualifying) producing two independent rows with the first left untouched; a direct attempt to modify a persisted evaluation's `outcome` field rejected by the immutability guard; and history ordering by `evaluated_at` rather than insertion order.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration `0009_watchlist_evaluations` upgrade: applied cleanly on top of the chain through `0008`; table and all 9 columns confirmed present. Downgrade: table confirmed fully dropped. Re-upgrade: clean.

### Acceptance Criteria

- [x] A user-provided stock can be evaluated independently of market-wide discovery.
- [x] The same objective positive criteria are applied (reuses M1.8's `evaluate_positive_consensus` directly).
- [x] A qualifying stock becomes a positive recommendation candidate.
- [x] A non-qualifying stock enters backlog rather than receiving a negative recommendation.
- [x] Backlog records explain the failed criteria.
- [x] Re-evaluation does not overwrite prior evaluations.
- [x] Tests cover qualifying and non-qualifying watchlist stocks.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence. The undeclared dependency on M1.8 and the resulting 3-way migration-numbering collision with M1.9/M1.10 are both real, disclosed risks flagged above rather than silently resolved or hidden. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

### Reconciliation onto current `main` (2026-08-20)

M1.8's `app/consensus.py`, which this EPIC depends on directly, turned out to be byte-identical between this branch's dependency commit and current `main` (`git diff --stat` between them is empty) — main gained an equivalent M1.8 implementation through a different PR, so no consensus-logic reconciliation was needed, only a rebase. This EPIC is genuinely still required: it is the only mechanism in the repository for evaluating a user-supplied stock outside the M1.12 daily scan, and nothing in M1.8–M1.14 supersedes it.

Reconciliation performed:
1. `git rebase --onto origin/main f2b7863 HEAD` (merge-base `f2b7863`, this branch's own M1.8 dependency commit) — replayed only this EPIC's own commit onto current `main`. One conflict, in `app/models.py`: `main` already carries M1.4-SUB-03's `func.now()` portability fix for `ModelVersion.created_at` where this branch's stale parent still had the pre-fix `server_default="now()"`; resolved by keeping `main`'s portable version and appending this EPIC's `WatchlistEvaluation` model unchanged.
2. Resolved the exact 3-way migration collision flagged above: since M1.9's and M1.10's own `0009` claims were each renumbered away during their own reconciliation (M1.9 ported into M1.13 as `0012`; `main`'s actual M1.10 never reserved `0009` at all), this EPIC's `0009_watchlist_evaluations` was the only remaining claimant and keeps its number. But `main`'s `0010_horizon_selection_version` had filled the gap with `down_revision = 0008` directly (skipping the never-merged `0009`), so merging this EPIC as-is would have produced two Alembic heads (`0009` as a dead-end off `0008`, and the real `0008→0010→0011` chain). Fixed by changing `migrations/versions/0010_horizon_selection_version.py`'s `down_revision` from `0008_consensus_contract_version` to `0009_watchlist_evaluations`, slotting the chain to `0008→0009→0010→0011`.
3. Cherry-picked `9049bec` ("fix: repair CI, broken since M1.10 merged onto main", open as PR #30 on `main`, not yet merged) — same root cause as M1.13/M1.14's own CI fixes: `record_recommendation()` on `main` now requires `horizon_selection_version` as a mandatory keyword argument (added when M1.10 landed on `main`), which several pre-existing test files never picked up. Applied cleanly, no conflicts.
4. This EPIC's own `tests/test_watchlist_evaluation.py::_recommendation_kwargs()` helper predates M1.10 and had the same gap; added the same one-line `horizon_selection_version="PHS-001"` fix.

**Note for the reviewer on merge ordering:** this PR now modifies `migrations/versions/0010_horizon_selection_version.py` (a file `main`, PR #28, and PR #29 all also carry unchanged). If PR #26 merges to `main` before PR #28/#29, those two will need a follow-up rebase to pick up the `0009→0010` chain fix; if they merge first, PR #26 will need the equivalent rebase against whatever `main` looks like then. Either order is mechanically fine — only one side needs a small follow-up rebase, not a rewrite.

Verification after reconciliation (fresh `.venv`, `requirements.txt` installed):
- `pytest -q`: **114 passed, 0 failed**.
- `pytest -v tests/test_watchlist_evaluation.py`: 6 passed.
- `compileall -q app scripts tests migrations`: exit 0, no output.
- `git diff --check origin/main HEAD`: exit 0, no output.
- `alembic heads`: single head, `0011_daily_candidate_scan` (this branch targets `main` directly, not the M1.12–14 stack, so it does not include those migrations).
- PostgreSQL round-trip against local `market_agent` database (schema reset first, since the DB is shared with PR #28/#29 validation in this same session): `upgrade head` from `<base>` through `0011` (confirmed the `0008→0009→0010→0011` chain applies in order) → `downgrade base` → `upgrade head` again, all clean, exactly one head throughout.

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
