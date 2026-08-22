# EPIC-015 — Market Universe & Daily Candidate Scan

**Status:** DONE  
**Execution Status:** COMPLETED  
**Approved By:** User  
**Priority:** P1

## Objective

Automatically scan the supported NSE universe each trading day and produce a deterministic candidate set for downstream evaluation.

## Scope

1. Define the eligible NSE universe using available persisted/security data.
2. Identify the trading date and prevent duplicate daily scans.
3. Run the existing feature/prediction pipeline across eligible securities.
4. Exclude missing, stale, or invalid market data explicitly.
5. Persist or expose the candidate set with scan timestamp/date and data/model versions.
6. Make the scan idempotent for the same trading date and universe version.
7. Add deterministic tests for eligibility, stale data, duplicates, and empty candidate sets.

## Non-goals

- Final positive recommendation generation.
- New ML model training.
- Portfolio/trading automation.
- UI/dashboard work.
- ChatGPT-assisted discovery.

## Acceptance Criteria

- [ ] A versioned/traceable NSE universe can be scanned.
- [ ] Each eligible security is evaluated at most once per scan.
- [ ] Stale/invalid data is explicitly excluded and observable.
- [ ] Re-running the same scan does not create duplicate scan results.
- [ ] Candidate results retain scan date and relevant data/model versions.
- [ ] Empty/partial scans are handled without fabricating candidates.
- [ ] Tests cover normal, duplicate, stale-data, and empty-universe cases.

## Dependency Chain

### Previous / Required
- **EPIC-003 — Yahoo NSE Historical Data Provider** — supplies the market data required by the scan.
- **EPIC-008 — Positive Consensus Engine** — provides the qualifying criteria used downstream.

### Next / Unlocks
- **EPIC-016 — Positive Recommendation Generator** — consumes the candidate set produced by this EPIC.

### Chain Position

`EPIC-003 + EPIC-008 → EPIC-015 → EPIC-016 → EPIC-017 → EPIC-018 → EPIC-019`

EPIC-020 (ChatGPT Candidate Discovery) branches later from the same quantitative path and depends on EPIC-008 and EPIC-016.

### Execution Rule

Do not execute EPIC-016 until EPIC-015 is implemented, reviewed, and merged. If implementation exposes a dependency defect, report it; do not silently bypass the dependency.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-015

### Branch

autonomous/epic-m1-12, branched directly from `main` (both declared dependencies are already present in `main`: EPIC-003 was merged long ago, and EPIC-008's code — `app/consensus.py` — reached `main` as part of EPIC-010's squash-merged PR #23, even though no EPIC doc marks EPIC-008 `DONE` yet; see dependency note below).

### Dependency note (flagged, not a blocker)

EPIC-008's own PR (#21) merged into an intermediate planning branch, not directly into `main`, and its EPIC doc still reads `APPROVED`/`READY_FOR_EXECUTION`. Its code is nonetheless present in `main` today (verified: `app/consensus.py` exists on `origin/main`) because EPIC-010's PR was based on a branch stacked on top of EPIC-008's work and brought the diff along when squash-merged. This EPIC's EPIC-008 dependency is therefore satisfied by code-on-`main`, not by a merged EPIC-008 PR or a `DONE` doc — flagging so a human can reconcile the bookkeeping (mark EPIC-008 `DONE`) without re-implementing anything.

### Pre-existing defect fixed: broken alembic chain on `main`

`main`'s `migrations/versions/0010_horizon_selection_version.py` declared `down_revision = "0009_opportunity_score"`, but no `0009_opportunity_score` migration file exists on `main` (EPIC-009's own PR merged into a sibling branch, never into `main`) — this is the "3-way migration-numbering collision" flagged in EPIC-007's completion report, materializing here as a fully broken chain: `alembic heads`/`history`/`upgrade` all raised `KeyError: '0009_opportunity_score'` before any change of mine. Since this EPIC's own migration must extend that chain, I corrected `0010`'s `down_revision` to `0008_consensus_contract_version` (the actual, present predecessor) rather than building on top of a broken reference. This is a minimal, targeted fix of a landed defect blocking migrations entirely, not a design change — flagged per the EPIC's own "report defects, don't silently bypass" execution rule.

### Design Decisions

- **New tables** (migration `0011_daily_candidate_scan`, chains off the corrected `0010`): `daily_candidate_scans` (one row per `scan_date` + `universe_version`, unique-constrained on that pair) and `scan_candidates` (one row per evaluated stock per scan, unique-constrained on `(scan_id, stock_id)`).
- **`run_daily_candidate_scan(session, scan_date, signal_provider, universe_version=...)`** (`app/scan.py`) is the single entry point:
  - Universe = active stocks (`Stock.is_active`), ordered deterministically by symbol.
  - Per stock, market data already persisted in `MarketPrice` up to `scan_date` (Asia/Kolkata session boundary, matching `app/market_data/quality.py`'s `NSE_TIMEZONE` convention) is run through the existing feature pipeline (`app/features/technical.py add_basic_features`), then handed to an injected `SignalProvider.predict(...)` for `predicted_probability`/`confidence` — mirroring the `DailyHistoryProvider` protocol already used in `app/market_data/ingest.py`, so the scan stays deterministic/testable without depending on a trained model.
  - Explicit exclusions, each with its own `exclusion_reason` string and no recommendation ever fabricated from missing/stale/invalid data: `missing_market_data` (no persisted prices at all), `stale_market_data` (latest available session older than `scan_date`), `invalid_market_data` (feature pipeline yields NaN for any of `sma20_distance`/`volume_ratio_20d`/`atr_percent`, e.g. from insufficient price history).
  - **Idempotency (scope items 2 and 6):** the function checks for an existing `DailyCandidateScan` row for `(scan_date, universe_version)` first and, if found, returns it and its persisted candidates unchanged rather than re-scanning — enforced at the application layer and backed by a DB unique constraint.
- Every `ScanCandidate` records the `model_version`/`feature_version` used, so the candidate set stays traceable even as the model or feature pipeline evolves — matching the versioning convention already established by `app/consensus.py`/`app/horizon.py`.

### Files Changed

- `app/scan.py` — new: `run_daily_candidate_scan`, `SignalProvider` protocol, `CandidateSignals`, `ScanSummary`.
- `app/models.py` — new `DailyCandidateScan` and `ScanCandidate` models.
- `migrations/versions/0011_daily_candidate_scan.py` — new migration.
- `migrations/versions/0010_horizon_selection_version.py` — fixed broken `down_revision` (see defect note above).
- `tests/test_daily_candidate_scan.py` — new: 8 tests.
- `docs/epics/EPIC-015-market-universe-daily-candidate-scan.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_daily_candidate_scan.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` / `alembic history` (confirms a single clean head, `0011_daily_candidate_scan`, after the `0010` fix)
- Migration validation against a disposable scratch PostgreSQL database `market_agent_scratch_m112` (created and dropped for this validation only): full `upgrade head` from `<base>` through `0011` (verified `daily_candidate_scans` and `scan_candidates` and all their columns exist with expected types), `downgrade -1` (verified both tables are dropped by `0011`'s downgrade), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **88 passed, 17 failed, 3 errored** (80 pre-existing pass + 8 new pass; the 17 failed + 3 errored are pre-existing on `main` *before this branch's changes* — confirmed by running the identical suite against unmodified `main` via `git stash`, which produced the same 17 failed/3 errored, just without the 8 new tests. Root cause: `tests/test_recommendation_calibration.py`, `tests/test_positive_recommendation_performance.py`, `tests/test_fresh_database_migration.py`, `tests/test_model_timestamp_portability.py`, and `tests/test_recommendation_history_db_integrity.py` call `record_recommendation(...)` without the `consensus_contract_version`/`horizon_selection_version` keyword arguments that EPIC-008/EPIC-010 later made required — those test files were never updated when the signature changed. Out of scope for this EPIC to fix; flagged here for the reviewer since it's a real, disclosed defect on `main`, not something this branch introduced.)
- `pytest -v tests/test_daily_candidate_scan.py`: **8 passed** — covers an eligible stock with sufficient history producing signals; missing market data excluded explicitly; stale market data excluded explicitly; insufficient history (NaN features) excluded as invalid; an inactive stock excluded from the universe entirely; an empty universe producing a scan with zero candidates and no error; re-running the same `(scan_date, universe_version)` not duplicating the scan or its candidates; and a different `universe_version` for the same date producing an independent second scan.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] A versioned/traceable NSE universe can be scanned.
- [x] Each eligible security is evaluated at most once per scan.
- [x] Stale/invalid data is explicitly excluded and observable.
- [x] Re-running the same scan does not create duplicate scan results.
- [x] Candidate results retain scan date and relevant data/model versions.
- [x] Empty/partial scans are handled without fabricating candidates.
- [x] Tests cover normal, duplicate, stale-data, and empty-universe cases.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip. Two pre-existing defects on `main` are disclosed above rather than silently hidden or silently fixed beyond what was necessary: the EPIC-008 doc/merge bookkeeping gap (code present, doc/PR state stale) and the broken alembic chain (fixed, since it fully blocked migrations and this EPIC needed to extend the chain). The 17 failed/3 errored pre-existing test failures are unrelated to this EPIC's scope and are not fixed here. This is NOT final approval — that remains the reviewer's call, and per the standing contract, Claude will not merge this PR.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
