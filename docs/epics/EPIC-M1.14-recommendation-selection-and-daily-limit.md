# EPIC-M1.14 — Recommendation Selection & Daily Limit

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
**Priority:** P1

## Objective

Select the strongest qualifying positive opportunities from all candidates without allowing marginal or excessive recommendations to dilute the signal.

## Scope

1. Define deterministic ranking using the approved opportunity score and required tie-breakers.
2. Define the minimum score/qualification boundary for selection.
3. Define a configurable maximum number of recommendations per scan/day.
4. Handle ties deterministically.
5. Preserve unselected qualifying candidates as non-selected candidates for auditability.
6. Persist selection-rule version and selection outcome.
7. Add tests for ranking, limits, ties, empty input, and boundary conditions.

## Non-goals

- Changing positive consensus.
- Changing the underlying ML model.
- Portfolio optimization.
- Trading execution.
- LLM-based selection.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Selection is deterministic for identical inputs.
- [ ] Only candidates that already qualify positively can be selected.
- [ ] Daily/scan recommendation limits are enforced.
- [ ] Ties are resolved deterministically.
- [ ] Unselected qualifying candidates remain auditable.
- [ ] Selection-rule version is traceable.
- [ ] Tests cover normal, limit, tie, and boundary cases.

## Dependency Chain

### Previous / Required
- **M1.13 — Positive Recommendation Generator** — supplies the qualifying recommendation candidates.

### Next / Unlocks
- **M1.15 — Recommendation Lifecycle & Outcome Scheduler** — tracks selected/issued recommendations through their horizon.

### Chain Position

`M1.8 + M1.9 + M1.10 + M1.12 → M1.13 → M1.14 → M1.15 → M1.16`

M1.17 is a later discovery branch and does not depend on M1.14.

### Execution Rule

Do not execute M1.15 until M1.14 is implemented, reviewed, and merged. Selection must not bypass the recommendation-generator contract.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.14

### Branch

autonomous/epic-m1-14, stacked on the still-open `autonomous/epic-m1-13` branch/PR #28 (this EPIC selects among M1.13's `RecommendationGeneration` rows, which aren't in `main` yet).

### Objective

From all of one scan's M1.13-qualified candidates, deterministically select the strongest positive opportunities by score, enforcing a minimum-score floor and a daily limit, while keeping every qualifying candidate — selected or not — auditable.

### Design Decisions

- **New table `recommendation_selections`** (migration `0014`, chains off M1.13's `0013`): one row per `(scan_id, recommendation_generation_id)`, recording `rank` (nullable), `selected`, `selection_reason`, and `selection_rule_version`.
- **`select_recommendations_for_scan(session, scan_id, *, min_score=MIN_SCORE_FOR_SELECTION, daily_limit=DEFAULT_DAILY_LIMIT)`** (`app/recommendation_selection.py`) is the single entry point:
  1. Idempotency check first (scope item unstated but required by the platform's standing convention, matching M1.12): an existing set of `RecommendationSelection` rows for the `scan_id` is returned unchanged, regardless of what `min_score`/`daily_limit` the re-run passes — the first run's decision is the historical record, not re-derivable after the fact.
  2. Pulls every `QUALIFIED` `RecommendationGeneration` for the scan (joined through `ScanCandidate`/`Prediction`/`Stock`) and ranks them by `opportunity_score` descending, ties broken by stock symbol ascending (scope item 4) — fully deterministic and repeatable (scope item 1).
  3. A candidate whose score falls strictly below `min_score` (`MIN_SCORE_FOR_SELECTION = 50.00`, a fixed policy constant, scope item 2) is excluded with `reason=BELOW_MIN_SCORE` and no rank — it never competed for a limit slot. A boundary score exactly equal to `min_score` is included (inclusive floor), covered by a dedicated test.
  4. Among candidates passing the floor, rank `1..N`; the top `daily_limit` (`DEFAULT_DAILY_LIMIT = 5`, configurable per call, scope item 3) are `selected=True`/`SELECTED`; the rest keep their rank but are `selected=False`/`DAILY_LIMIT_EXCEEDED` (scope item 5 — unselected qualifying candidates stay auditable with their exact standing, not dropped).
  5. Every row records `selection_rule_version` (scope item 6), so the rule that produced a given selection stays traceable even as the constants change.
- Deliberately does not add its own immutability guard: `RecommendationSelection` rows are never updated after creation by this module (idempotency is enforced by returning existing rows rather than by rejecting writes), and no other code path writes to this table, so a DB-trigger-style guard would be dead code rather than a real protection — unlike `Prediction`/`RecommendationGeneration`, which are mutated by other legitimate code paths (`status` transitions, etc.) that a guard must actively police.

### Files Changed

- `app/recommendation_selection.py` — new: `select_recommendations_for_scan`, `RankedCandidate`, reason/version constants.
- `app/models.py` — new `RecommendationSelection` model.
- `migrations/versions/0014_recommendation_selections.py` — new migration.
- `tests/test_recommendation_selection.py` — new: 7 tests.
- `docs/epics/EPIC-M1.14-recommendation-selection-and-daily-limit.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_recommendation_selection.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0014_recommendation_selections`)
- Migration validation against a disposable scratch PostgreSQL database `market_agent_scratch_m114` (created and dropped for this validation only): full `upgrade head` from `<base>` through `0014` (verified `recommendation_selections` and all its columns), `downgrade -1` (verified the table dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **122 passed, 19 failed** (115 pre-existing/M1.13 pass + 7 new pass; the 19 failures are the same pre-existing-on-`main` set disclosed in EPIC-M1.12/M1.13's completion reports, unrelated to this branch, not fixed here.)
- `pytest -v tests/test_recommendation_selection.py`: **7 passed** — three candidates with distinct scores rank and select in strict descending order; seven qualifying candidates against a `daily_limit=3` select exactly the top 3 (ranks 1–3) and mark the remaining 4 `DAILY_LIMIT_EXCEEDED` with ranks 4–7 preserved; a candidate scored below `min_score` is excluded with `BELOW_MIN_SCORE` and no rank; a score exactly equal to `min_score` is included (inclusive boundary); two identically-scored candidates break their tie by symbol ascending regardless of insertion order; a scan with no qualifying candidates produces zero selection rows without error; and re-selecting the same scan with different parameters returns the original rows unchanged (idempotent).
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Selection is deterministic for identical inputs.
- [x] Only candidates that already qualify positively can be selected (sourced exclusively from `RecommendationGeneration.outcome == QUALIFIED`).
- [x] Daily/scan recommendation limits are enforced.
- [x] Ties are resolved deterministically.
- [x] Unselected qualifying candidates remain auditable.
- [x] Selection-rule version is traceable.
- [x] Tests cover normal, limit, tie, and boundary cases.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip through the full chain M1.8→M1.9→M1.10→M1.12→M1.13→M1.14. No new undeclared dependencies were found this time — M1.13 was this EPIC's only declared dependency and is already present on this stacked branch. This is NOT final approval — that remains the reviewer's call, and per the standing contract, Claude will not merge this PR.

### Reconciliation onto reconciled M1.13 (2026-08-20)

PR #28 (M1.13) was reconciled onto current `main` (its base retargeted from the never-merged `autonomous/epic-m1-12` to `main`; see M1.13's own completion report for detail). This branch (`autonomous/epic-m1-14`) was stacked on the pre-reconciliation `autonomous/epic-m1-13`, so it needed the equivalent rebase.

Reconciliation performed: `git rebase --onto <new-epic-m1-13-tip> c79a674 origin/autonomous/epic-m1-14`, replaying only this branch's own commit (the M1.14 feature commit) onto the reconciled M1.13 branch. This branch's separate CI-fix commit (`c8cb93f`, merged in earlier from `epic-m1-13`) was dropped automatically by the rebase as "patch contents already upstream" — it's already present via the reconciled M1.13 branch it's now stacked on. No source conflicts; no product behavior changed. `base` stays `autonomous/epic-m1-13` (unchanged ref name, now pointing at the reconciled branch).

Verification after reconciliation (fresh `.venv`, `requirements.txt` installed):
- `pytest -q`: **141 passed, 0 failed** (the pre-existing failures noted in the prior run above were already resolved by the CI fix now inherited from the reconciled M1.13 branch).
- `pytest -v tests/test_recommendation_selection.py`: **7 passed**.
- `compileall -q app scripts tests migrations`: exit 0, no output.
- `git diff --check origin/main HEAD`: exit 0, no output.
- `alembic heads`: single head, `0014_recommendation_selections`.
- PostgreSQL round-trip against local `market_agent` database: `downgrade base` → `upgrade head` → `downgrade base` → `upgrade head`, all clean, exactly one head throughout.

### Second reconciliation: rebased after M1.13's own second reconciliation (2026-08-20)

PR #30 merged to `main` mid-session, requiring PR #28 (M1.13) to re-rebase; this branch was re-rebased in turn (`git rebase --onto <new-epic-m1-13-tip> <old-M1.14-feature-commit>~1 HEAD`), replaying only this EPIC's own feature and docs commits — no conflicts. Re-verified: `pytest -q` **141 passed, 0 failed**; `compileall`/`git diff --check` exit 0; `alembic heads` single head `0014_recommendation_selections`; full `upgrade head` → `downgrade base` → `upgrade head` PostgreSQL round-trip against a freshly reset schema, clean throughout.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
