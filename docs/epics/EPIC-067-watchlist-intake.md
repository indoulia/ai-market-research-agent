# EPIC-067 — Watchlist Intake

**Status:** DONE  
**Execution Status:** COMPLETED  
**Approved By:** User  
**Priority:** P1

## Objective
Establish a deterministic, persistent intake boundary for stocks that users or other discovery sources want the recommendation system to monitor.

## Scope
1. Define a watchlist entry contract for symbol, source, timestamp, and active state.
2. Validate symbols against the supported NSE/security universe.
3. Make repeated intake idempotent.
4. Preserve watchlist history rather than silently overwriting prior intake events.
5. Expose enough persisted context for downstream watchlist analysis.
6. Add deterministic tests for valid, invalid, duplicate, inactive, and unknown-symbol cases.

## Non-goals
- Generating recommendations.
- Changing positive-consensus rules.
- Automatic trading.
- Learning from outcomes.
- UI/dashboard implementation.

## Acceptance Criteria
- [ ] Valid watchlist entries are persisted with provenance and timestamps.
- [ ] Unsupported symbols are rejected explicitly.
- [ ] Duplicate intake is idempotent.
- [ ] Historical intake information is auditable.
- [ ] Active/inactive state is deterministic.
- [ ] Tests cover normal and boundary cases.

## Dependency Chain
### Previous / Required
- **EPIC-015 — Market Universe & Daily Candidate Scan** — establishes the supported market/security universe.
- **EPIC-020 — ChatGPT Candidate Discovery** — establishes the external discovery/provenance pattern where applicable.

### Next / Unlocks
- **EPIC-068 — Watchlist Positive Analysis**

### Chain Position
`EPIC-015 + EPIC-020 → EPIC-067 → EPIC-068 → EPIC-069 → EPIC-070 → EPIC-071 → EPIC-072 → EPIC-073 → EPIC-074`

## Execution Rule
Do not execute until dependencies are implemented, reviewed, and merged. Watchlist intake must remain an input/provenance boundary and must not bypass quantitative qualification.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-067

### Branch

autonomous/epic-m1-18, branched cleanly from `main` (both declared dependencies, EPIC-015 and EPIC-020, are already merged).

### Objective

Establish a deterministic, persistent, append-only intake boundary recording which stocks are requested to be watched (and by whom/when), distinct from and prior to EPIC-007's evaluation step.

### Design Decisions

- **New table `watchlist_entries`** (migration `0018`, chains off EPIC-029's `0017`): one row per intake *event* (`ACTIVATE`/`DEACTIVATE`), never one mutable row per stock. This is what makes "preserve watchlist history rather than silently overwriting prior intake events" hold by construction, and what makes "active/inactive state is deterministic" well-defined: current state is always the most recent event's `action`, derived, never a separately-mutated flag that could drift from history.
- **Two distinct error types for the two distinct failure modes the EPIC names separately** ("invalid" vs "unknown-symbol"/"inactive"): `InvalidSymbolError(ValueError)` for a malformed/blank symbol string (pure input validation, no DB lookup attempted at all), and `UnsupportedSymbolError(RuntimeError)` for a well-formed symbol that's either not in the `stocks` table at all ("unknown symbol") or present but `is_active=False` ("inactive symbol") — both are explicit, distinguishable-by-message rejections, never a silent no-op.
- **Idempotency is defined per-stock, not per-`(stock, source)`:** re-requesting to activate a stock that's already active (from any source) is a no-op returning the existing latest entry, rather than creating a redundant duplicate — "the watchlist" is one shared membership state; `source` is provenance on each event, not a separate parallel watchlist. This was a genuine design choice (the EPIC doesn't specify), documented here for reviewer scrutiny.
- **Removing a stock that was never added still records an explicit `DEACTIVATE` event** rather than being treated as a no-op with no return value — an explicit "not watched" request is itself worth an auditable record, and this keeps the function's return type uniform (always a real `WatchlistEntry`, never `None`).
- **Symbol snapshot:** `WatchlistEntry.symbol` denormalizes the requested symbol at intake time (normalized to uppercase, trimmed) rather than only the `stock_id` FK, so a stock's `symbol` changing later can't retroactively alter what was actually recorded as requested.
- **Immutability guard** (`WatchlistEntryImmutableError`, `before_update` event listener) mirrors `DiscoverySegment`'s pattern — defense-in-depth on top of the "never update, only insert" design, consistent with this repo's standing convention for historical-fact rows.
- Deliberately does **not** touch `app/watchlist.py` (EPIC-007's evaluation step) at all — EPIC-067 is a strictly earlier, separate boundary; EPIC-068 (Watchlist Positive Analysis) is the EPIC that will wire this intake list into EPIC-007's evaluation path.

### Files Changed

- `app/watchlist_intake.py` — new: `add_to_watchlist`, `remove_from_watchlist`, `is_active`, `get_latest_entry`, `get_watchlist_history`, `get_active_watchlist`, error types.
- `app/models.py` — new `WatchlistEntry` model.
- `migrations/versions/0018_watchlist_entries.py` — new migration.
- `tests/test_watchlist_intake.py` — new: 9 tests.
- `docs/epics/EPIC-067-watchlist-intake.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_watchlist_intake.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0018_watchlist_entries`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0017` through `0018` (verified `watchlist_entries` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **198 passed, 0 failed** (189 pre-existing from `main` + 9 new).
- `pytest -v tests/test_watchlist_intake.py`: **9 passed** — covering every case the EPIC scope names by name: a valid symbol is added with full provenance; a blank/malformed symbol raises `InvalidSymbolError` before any DB lookup; an unknown symbol and a known-but-inactive symbol each raise `UnsupportedSymbolError` with a distinguishable message and no row created; duplicate intake for an already-active stock is idempotent (no second row); a remove-then-readd cycle preserves the complete three-event history in order; removing a never-added symbol still records an explicit event; `get_active_watchlist` lists only currently-active stocks; and a direct mutation attempt after creation raises `WatchlistEntryImmutableError`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Valid watchlist entries are persisted with provenance and timestamps.
- [x] Unsupported symbols are rejected explicitly (`UnsupportedSymbolError`, two distinguishable messages).
- [x] Duplicate intake is idempotent.
- [x] Historical intake information is auditable (`get_watchlist_history`, append-only).
- [x] Active/inactive state is deterministic (derived from the latest event only).
- [x] Tests cover normal and boundary cases, including every case the scope names explicitly.

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip. The per-stock (not per-`(stock, source)`) idempotency rule was a genuine judgment call given the EPIC's silence on the point, documented above for reviewer scrutiny. This EPIC deliberately does not wire into EPIC-007's evaluation path — that integration is EPIC-068's job. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
