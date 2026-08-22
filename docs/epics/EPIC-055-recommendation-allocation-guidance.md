# EPIC-055 — Recommendation Allocation Guidance

Status: DONE
Execution Status: COMPLETED

## Objective
Provide optional risk-aware allocation guidance based on user constraints without executing trades.

## Scope
- Define user allocation/risk limits.
- Calculate a suggested allocation range from risk and confidence.
- Respect portfolio and concentration constraints.
- Explain why an allocation is constrained.
- Keep allocation separate from recommendation quality.

## Acceptance Criteria
- Guidance is deterministic and capped by user limits.
- No automatic order execution exists.
- Missing risk information prevents unsafe guidance.
- Tests cover concentration and limit boundaries.

## Dependencies
Previous: EPIC-054.
Next: EPIC-056.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-055

### Branch

autonomous/epic-m1-60, branched cleanly from `main` (the declared dependency -- EPIC-054 -- is already merged).

### Objective

Provide optional, risk-aware allocation guidance based on user-declared constraints without ever executing a trade.

### Design

`UserAllocationLimit` is versioned and append-only -- the same "a user can change limits without mutating history" pattern EPIC-041 already established for `UserPreference`. Guidance itself (`AllocationGuidance`) is a pure, read-only computation, never persisted: it is explicitly advisory, not a financial record, and this module has no write path for it at all (AC: "no automatic order execution exists").

### Missing Risk Information Blocks Guidance

`generate_allocation_guidance` requires a horizon-consistent EPIC-053 `PositionRiskAssessment` as its sole risk input. If none is supplied, or the one supplied is itself flagged horizon-inconsistent, guidance is refused outright (`INSUFFICIENT_RISK_INFORMATION`, `suggested_allocation_percentage=None`) rather than falling back to a fabricated risk estimate (AC: "missing risk information prevents unsafe guidance").

### Suggested Allocation Range From Risk and Confidence

A fixed, documented formula -- `MAX_BASE_ALLOCATION_PERCENTAGE × confidence / (1 + risk_in_atr_units)` -- scales the suggestion up with confidence and down with EPIC-053's volatility-adjusted risk, then caps it at the user's own `max_position_percentage` (AC: "guidance is deterministic and capped by user limits").

### Portfolio and Concentration Constraints

Reuses EPIC-054's `assess_portfolio_conflict` directly (scope: "respect portfolio and concentration constraints"): a stock the user already holds or already has an active recommendation for is hard-blocked (`suggested_allocation_percentage=0`, `BLOCKED`); a sector at its concentration threshold halves the suggestion rather than blocking it outright (`CONSTRAINED`) -- a soft constraint, honestly distinct from the hard block for actual existing exposure.

### Explaining Constraints

Every guidance result carries an explicit `reasons` tuple (`CAPPED_BY_USER_LIMIT`, `SECTOR_CONCENTRATION`, `ALREADY_EXPOSED`, `NO_RISK_ASSESSMENT`, `HORIZON_INCONSISTENT_RISK`) (scope: "explain why an allocation is constrained").

### Recommendation Quality Stays Separate

Guidance never reads or writes `Prediction.opportunity_score` or any other scoring field for the purpose of changing it -- only `confidence` (as an input, never mutated) and EPIC-053/EPIC-054's own outputs are consulted (scope: "keep allocation separate from recommendation quality"). `test_guidance_is_reproducible_and_never_writes_to_prediction` proves this directly.

### Files Changed

- `app/allocation_guidance.py` — new: `set_allocation_limit`, `get_current_allocation_limit`, `generate_allocation_guidance`, `AllocationGuidance` dataclass, status/reason constants, `InvalidAllocationLimitError`.
- `app/models.py` — new `UserAllocationLimit` model.
- `migrations/versions/0042_user_allocation_limits.py` — new migration.
- `tests/test_allocation_guidance.py` — new: 9 tests.
- `docs/epics/EPIC-055-recommendation-allocation-guidance.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_allocation_guidance.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0042_user_allocation_limits`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0041` through `0042` (verified `user_allocation_limits` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **530 passed, 0 failed** (521 pre-existing from `main` + 9 new).
- `pytest -q tests/test_allocation_guidance.py -v`: **9 passed** — a missing risk assessment and a horizon-inconsistent one both prevent guidance; a normal case produces a guided allocation within the default limit; a tighter user limit caps the suggestion with the correct reason; an already-held stock is blocked at zero allocation; sector concentration constrains (halves) but does not block; an invalid allocation limit (out of range) is rejected; a new user gets a default limit idempotently; guidance is reproducible and never writes to `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Guidance is deterministic and capped by user limits (fixed formula; capped at `max_position_percentage`; proven by test).
- [x] No automatic order execution exists (guidance itself has no write path at all; only `set_allocation_limit`, an explicit user declaration, writes anything).
- [x] Missing risk information prevents unsafe guidance (`INSUFFICIENT_RISK_INFORMATION` for both a missing and a horizon-inconsistent risk assessment).
- [x] Tests cover concentration and limit boundaries (sector concentration and user-limit capping both covered explicitly).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including direct proof that guidance is refused outright without valid risk information and that it never writes to `Prediction`. This EPIC composes EPIC-041's versioned-limit pattern, EPIC-053's volatility-adjusted risk, and EPIC-054's portfolio-conflict assessment into one coherent, purely advisory guidance layer, without duplicating or touching any of them. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
