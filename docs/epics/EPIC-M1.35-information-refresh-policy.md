# EPIC-M1.35 — Automatic Information Refresh Policy

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Determine what information must be fetched, when it must be refreshed, and when existing data is sufficiently fresh for analysis.

## Scope
- Define freshness requirements by data type.
- Define market-data refresh cadence.
- Define news/event refresh triggers.
- Define fundamental-data refresh rules.
- Track source timestamp and fetch timestamp.
- Detect stale or missing data before analysis.
- Avoid unnecessary duplicate fetches.
- Record refresh failures explicitly.

## Acceptance Criteria
- [ ] Each supported data type has a defined freshness policy.
- [ ] Analysis can determine whether required data is fresh enough.
- [ ] Stale data triggers refresh or explicit non-qualification.
- [ ] Fetch attempts and failures are auditable.
- [ ] Duplicate unnecessary fetches are avoided.
- [ ] Historical snapshots used by recommendations remain immutable.

## Dependencies
**Previous:** M1.34
**Next:** M1.36

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.35

### Branch

autonomous/epic-m1-35, branched cleanly from `main` (declared dependency M1.34 is already merged).

### Objective

Determine what information must be fetched, when it must be refreshed, and when existing data is fresh enough for analysis -- with every fetch attempt (success or failure) auditable and immutable.

### Design Decisions

- **This repo has only one data type genuinely ingested end to end: market/price data.** There is no news/event or fundamental-data ingestion pipeline in this codebase. Rather than fabricate fetch logic for data that isn't really there, this EPIC defines the policy framework generically -- a `data_type` dimension with a fixed, documented, versioned freshness threshold (`FRESHNESS_POLICY`, `REFRESH_POLICY_VERSION = "RFP-001"`) -- and provides a real, working, tested instantiation (`check_market_data_freshness`) for the one type that's actually backed by ingestion. `NEWS_EVENT` and `FUNDAMENTAL_DATA` exist only as named policy constants, proving the framework is genuinely generic without pretending there's real data behind them. Documented here for reviewer scrutiny, same honest-scoping pattern this platform has used consistently (M1.23/M1.25/M1.27/M1.28/M1.29/M1.30).
- **New table `data_fetch_attempts`** (migration `0024`, chains off M1.32's `0023`): append-only, one row per fetch attempt, immutable after creation (`before_update` guard, same pattern as every other historical-fact row in this platform). Both successful and failed attempts are recorded (scope item "record refresh failures explicitly").
- **`is_data_fresh(data_type, source_timestamp, as_of_timestamp) -> FreshnessCheck`** is a pure, deterministic function: missing data (`source_timestamp=None`) is always the explicit `missing_data` reason, never silently treated as fresh; data beyond the type's policy threshold is explicitly `stale_data`. Normalizes both timestamps to naive before subtracting -- sqlite (this repo's test backend) drops `tzinfo` on `DateTime(timezone=True)` round-trips unlike Postgres, and every timestamp in this system is UTC-based by convention regardless of backend, so this normalization is correctness-preserving on both.
- **"Avoid unnecessary duplicate fetches" (scope item) is enforced inside `record_fetch_attempt` itself**, not left to callers: before recording a new attempt, it checks whether the most recent *successful* attempt for the same `(data_type, scope_key)` is already fresh enough as of the new `requested_at` under that data type's own policy -- if so, the existing attempt is returned unchanged rather than duplicated. A stale or failed prior attempt does not suppress a new one.
- **"Historical snapshots used by recommendations remain immutable" (AC)** holds on two levels: this module's own `DataFetchAttempt` rows are immutable by guard, and this module has no write path to `Prediction`/`MarketPrice`/any other historical recommendation data at all.

### Files Changed

- `app/refresh_policy.py` — new: `is_data_fresh`, `check_market_data_freshness`, `record_fetch_attempt`, `get_fetch_history`, policy constants, `DataFetchAttemptImmutableError`, `UnsupportedDataTypeError`.
- `app/models.py` — new `DataFetchAttempt` model.
- `migrations/versions/0024_data_fetch_attempts.py` — new migration.
- `tests/test_refresh_policy.py` — new: 13 tests.
- `docs/epics/EPIC-M1.35-information-refresh-policy.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_refresh_policy.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0024_data_fetch_attempts`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0023` through `0024` (verified `data_fetch_attempts` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **305 passed, 0 failed** (292 pre-existing from `main` + 13 new).
- `pytest -v tests/test_refresh_policy.py`: **13 passed** — missing source data is explicit `missing_data`, never fabricated; data within/beyond the market-data policy window is correctly fresh/stale; all three defined data types (including the two not yet backed by real ingestion) have a working policy; an unknown data type raises `UnsupportedDataTypeError`; `check_market_data_freshness` correctly reads the latest ingested price (or reports `missing_data` with none at all); successful and failed fetch attempts are both recorded with full provenance; a fetch request while existing data is still fresh is a no-op returning the original attempt (proven: exactly one row persists); a fetch request once existing data has gone stale records a genuinely new attempt; a direct mutation attempt after creation raises `DataFetchAttemptImmutableError`; and the full fetch history returns both attempts in order.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Each supported data type has a defined freshness policy (`FRESHNESS_POLICY`, all three types).
- [x] Analysis can determine whether required data is fresh enough (`is_data_fresh`/`check_market_data_freshness`).
- [x] Stale data triggers refresh or explicit non-qualification (explicit `stale_data`/`missing_data` reasons; downstream callers -- e.g. M1.12's scan -- already treat missing/stale market data as explicit non-qualification, consistent with this module's classification).
- [x] Fetch attempts and failures are auditable (`data_fetch_attempts`, both outcomes recorded).
- [x] Duplicate unnecessary fetches are avoided (proven by test).
- [x] Historical snapshots used by recommendations remain immutable (immutability guard; no write path to recommendation data).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip. The central scope decision -- a generic policy framework with only market data genuinely backed by ingestion -- is documented above for reviewer scrutiny. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->