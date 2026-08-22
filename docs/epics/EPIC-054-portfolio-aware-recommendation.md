# EPIC-054 — Portfolio-Aware Recommendation

Status: DONE
Execution Status: COMPLETED

## Objective
Make recommendations aware of existing user holdings and active recommendations without changing the underlying opportunity score.

## Scope
- Represent current holdings and active recommendation exposure.
- Detect sector and correlated-stock concentration.
- Identify duplicate or highly correlated opportunities.
- Explain portfolio-level conflicts.
- Keep recommendation quality separate from allocation decisions.

## Acceptance Criteria
- Portfolio exposure is computed deterministically.
- Concentration/conflict warnings are reproducible.
- Recommendations remain individually auditable.
- No automatic trading or allocation is performed.

## Dependencies
Previous: EPIC-053.
Next: EPIC-055.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-054

### Branch

autonomous/epic-m1-59, branched cleanly from `main` (the declared dependency -- EPIC-053 -- is already merged).

### Objective

Make recommendations aware of a user's existing holdings and the platform's currently-active recommendations, without ever changing the underlying opportunity score.

### Design

`UserHolding` is a new, append-only event log (`HELD`/`SOLD`) -- there is no brokerage integration in this repo, so a holding is only ever what the user explicitly declares via `record_holding`, never inferred or fabricated. `get_current_holdings` derives "current holdings" by reading the latest event per `(user_id, stock_id)`, never by mutating a prior row.

Recommendations are not user-scoped in this platform (EPIC-041 only personalizes *visibility* of the same system-wide picks), so "active recommendation exposure" means every currently open (`Prediction.status == "OPEN"`), currently-selected (EPIC-017's `RecommendationSelection.selected`) recommendation system-wide, combined with one user's own declared holdings.

### Conflict & Concentration Detection

`assess_portfolio_conflict(session, user_id, candidate_stock_id)` checks a candidate stock against the combined exposure and flags:
- **Already held** (scope: "identify duplicate ... opportunities") -- the user already holds this exact stock.
- **Already an active recommendation** -- this stock already has an open, selected, system-wide recommendation.
- **Sector concentration** (scope: "detect sector ... concentration") -- adding this candidate would bring the user's combined holdings + active-recommendation exposure in the candidate's own sector to `SECTOR_CONCENTRATION_THRESHOLD` (3) or more. True price-correlation across stocks is not computed anywhere in this repo, so "correlated-stock concentration" is honestly represented via same-sector grouping only, the one real proxy this platform's data actually supports -- not a fabricated correlation metric.

Every conflict carries an explicit, human-readable reason (scope: "explain portfolio-level conflicts").

### Recommendation Quality Stays Separate

This module never reads `Prediction.opportunity_score`, `predicted_probability`, `confidence`, or any other scoring field for the purpose of changing it -- only `Stock.sector` and open/selected status are read. `test_assessment_never_writes_anything` proves the assessment itself has no write path at all (AC: "no automatic trading or allocation is performed"; scope: "keep recommendation quality separate from allocation decisions").

### Determinism & Auditability

`assess_portfolio_conflict` is a pure function of the current holdings log and the platform's current selection/status state -- deterministic and reproducible (AC), proven directly by `test_conflict_assessment_is_reproducible`. `UserHolding` carries a `before_update` immutability guard for consistency with this platform's append-only-log convention, even though holdings are naturally never edited by design.

### Files Changed

- `app/portfolio_awareness.py` — new: `record_holding`, `get_current_holdings`, `assess_portfolio_conflict`, action/reason constants, `InvalidHoldingError`, `UserHoldingImmutableError`.
- `app/models.py` — new `UserHolding` model.
- `migrations/versions/0041_user_holdings.py` — new migration.
- `tests/test_portfolio_awareness.py` — new: 10 tests.
- `docs/epics/EPIC-054-portfolio-aware-recommendation.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_portfolio_awareness.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0041_user_holdings`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0040` through `0041` (verified `user_holdings` created -- this step caught and required fixing a `stock_id` foreign-key column type mismatch, `sa.BigInteger()` vs. `Stock.id`'s actual `Integer` type), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **521 passed, 0 failed** (511 pre-existing from `main` + 10 new).
- `pytest -q tests/test_portfolio_awareness.py -v`: **10 passed** — an invalid holding action is rejected; current holdings reflect the latest action (held, then sold); an unrelated candidate stock has no conflict; an already-held stock is flagged; an already-active recommendation is flagged; sector concentration is correctly detected at the threshold boundary and correctly *not* triggered for a different sector; the assessment never writes anything; a holding event is immutable after creation; the conflict assessment is reproducible.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above (including the caught-and-fixed FK type issue).

### Acceptance Criteria

- [x] Portfolio exposure is computed deterministically (`get_current_holdings`/`assess_portfolio_conflict` are pure functions of the immutable event log and current selection/status state).
- [x] Concentration/conflict warnings are reproducible (proven directly by test).
- [x] Recommendations remain individually auditable (no scoring field is ever touched by this module).
- [x] No automatic trading or allocation is performed (no write path exists for the assessment itself; only `record_holding`, an explicit user declaration, writes anything).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip that caught a foreign-key column type mismatch before it could reach `main`. This EPIC introduces the first genuine "user portfolio" concept in this platform, honestly scoped to only what can be declared (holdings) or already exists (sector, open/selected status) -- it never fabricates a correlation metric this repo has no data to support, and never touches recommendation scoring. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
