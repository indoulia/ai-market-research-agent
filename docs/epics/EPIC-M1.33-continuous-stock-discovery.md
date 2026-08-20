# EPIC-M1.33 — Continuous Stock Discovery

**Status:** APPROVED
**Execution Status:** VALIDATING
**Priority:** P1

## Objective
Continuously discover new stock candidates for analysis without turning discovery into recommendation.

## Scope
- Maintain a discoverable NSE stock universe.
- Run scheduled discovery scans.
- Generate candidates from measurable market signals.
- Deduplicate candidates across scans.
- Persist discovery timestamp, source, and discovery reason.
- Route candidates into the existing positive-analysis pipeline.
- Preserve candidates that fail qualification as backlog/history rather than deleting them.

## Acceptance Criteria
- [ ] Scheduled discovery produces persisted candidates.
- [ ] Every candidate has a deterministic discovery source/reason.
- [ ] Duplicate candidates are prevented within the defined discovery window.
- [ ] Discovery never directly creates a recommendation.
- [ ] Candidates enter M1.13/M1.14 qualification flow.
- [ ] Failed candidates remain traceable.
- [ ] Discovery runs are reproducible for a given data snapshot.

## Non-goals
- Trading execution.
- Changing recommendation qualification rules.
- Autonomous model promotion.
- UI redesign.

## Dependencies
**Previous:** M1.12, M1.13, M1.14
**Next:** M1.34

## Execution Rule
Do not execute until M1.14 is implemented and merged.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.33

### Branch

autonomous/epic-m1-33, branched cleanly from `main` (all three declared dependencies -- M1.12, M1.13, M1.14 -- are already merged).

### Objective

Give the platform one scheduled, idempotent, reproducible entry point that ties the existing daily-scan, discovery-provenance, and qualification pipelines together, so new candidates keep flowing into positive-analysis on a schedule without discovery ever constructing a recommendation itself.

### Design Decisions

- **Deliberately composes existing EPICs rather than reimplementing any of them** (see the module docstring in `app/continuous_discovery.py` for the full mapping): M1.12's `run_daily_candidate_scan` already *is* "maintain a discoverable NSE stock universe" + "generate candidates from measurable market signals" + "deduplicate candidates across scans" (via its `(scan_date, universe_version)` idempotency and `ScanCandidate`'s own uniqueness) -- none of that is rewritten here.
- **New module `app/continuous_discovery.py`, two functions:**
  - `record_discovery_for_scan(session, scan, discovered_at)` gives *every* candidate in a scan -- eligible or not -- a provenance row via M1.17's `record_discovery`, tagged with the new `SOURCE_DAILY_UNIVERSE_SCAN` constant (added to `app/discovery.py` alongside `SOURCE_CHATGPT`). This is the scope item genuinely missing before this EPIC: M1.12 candidates had no discovery-provenance trail at all; only M1.17's externally discovered ones did. Idempotent via `record_discovery`'s own `(scan_id, stock_id, source)` uniqueness.
  - `run_scheduled_discovery_scan(session, scan_date, signal_provider, *, as_of_timestamp, entry_price_for, target_return, stop_return, universe_version, min_score, daily_limit)` is the one call a scheduler makes once per trading day: scan (M1.12) -> discovery provenance (above) -> `generate_recommendation_for_candidate` (M1.13) for every *eligible* candidate -> `select_recommendations_for_scan` (M1.14) over the whole scan. `entry_price_for` is an injected `Callable[[int], Decimal]` (mirrors `scan.py`'s own `SignalProvider` injection pattern) so this module stays decoupled from any specific pricing source/convention.
- **End-to-end idempotency (AC "discovery runs are reproducible for a given data snapshot"):** every stage this function composes is already independently idempotent (M1.12 by `scan_date`+`universe_version`, `record_discovery` by `(scan, stock, source)`, M1.13 by `scan_candidate_id`, M1.14 by `scan_id`), so calling `run_scheduled_discovery_scan` twice for the same day is a true no-op the second time -- not merely "doesn't error," but returns the identical rows.
- **"Discovery never directly creates a recommendation"** holds by construction: `record_discovery_for_scan` only ever writes `DiscoveryRecord` rows (never `Prediction`/`RecommendationGeneration`); recommendation creation happens exclusively inside `generate_recommendation_for_candidate`, called separately and afterward.
- **"Preserve candidates that fail qualification as backlog/history rather than deleting them"** required no new code: `RecommendationGeneration` rows (`OUTCOME_NOT_QUALIFIED` included) and `ScanCandidate` rows (ineligible included) are never deleted by any existing code path; this EPIC's tests assert that directly rather than just asserting it by absence of a `DELETE` statement.
- Ineligible candidates (missing/stale/invalid market data) are skipped for generation (mirrors M1.13's own `CandidateNotEligibleError` boundary) but still get a discovery-provenance row -- "this stock was considered and excluded" is itself worth persisting, distinct from "this stock qualified/didn't qualify."

### Files Changed

- `app/continuous_discovery.py` — new: `run_scheduled_discovery_scan`, `record_discovery_for_scan`, `ContinuousDiscoveryResult`.
- `app/discovery.py` — added `SOURCE_DAILY_UNIVERSE_SCAN` constant (no behavior change to existing M1.17 functions).
- `tests/test_continuous_discovery.py` — new: 5 tests.
- `docs/epics/EPIC-M1.33-continuous-stock-discovery.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_continuous_discovery.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from M1.17's `0016_discovery_records`)

### Test Results

- `pytest -q`: **180 passed, 0 failed** (175 pre-existing from `main` + 5 new).
- `pytest -v tests/test_continuous_discovery.py`: **5 passed** — a qualifying candidate (real technical features off a 25-session rising-price fixture, exactly like `test_daily_candidate_scan.py`'s own fixture) is scanned, discovery-recorded, generated, and selected in one call; an ineligible candidate (no market data at all) still gets a discovery-provenance row but no generation/prediction is ever created; a candidate that fails M1.8 consensus (low `predicted_probability`) is preserved as a `NOT_QUALIFIED` `RecommendationGeneration` row rather than being deleted; calling `record_discovery_for_scan` alone (without the generation step) proves discovery-recording by itself never creates a `RecommendationGeneration`/`Prediction`; and re-running the full scheduled scan for the same day is fully idempotent (identical generation/selection ids, no duplicate rows in any of the four tables it touches).
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0016_discovery_records` (no migration in this EPIC).

### Acceptance Criteria

- [x] Scheduled discovery produces persisted candidates (`run_scheduled_discovery_scan` composes M1.12's scan + persists it as usual).
- [x] Every candidate has a deterministic discovery source/reason (`record_discovery_for_scan`, `SOURCE_DAILY_UNIVERSE_SCAN`, deterministic rationale string).
- [x] Duplicate candidates are prevented within the defined discovery window (M1.12's own `(scan_date, universe_version)` + `ScanCandidate` uniqueness; proven by the idempotency test).
- [x] Discovery never directly creates a recommendation (proven directly by `test_discovery_recording_alone_never_creates_a_recommendation`).
- [x] Candidates enter M1.13/M1.14 qualification flow (identical `generate_recommendation_for_candidate` + `select_recommendations_for_scan` calls).
- [x] Failed candidates remain traceable (proven by `test_non_qualifying_candidate_is_preserved_as_backlog_not_deleted`).
- [x] Discovery runs are reproducible for a given data snapshot (proven by the full idempotency test).

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence. The design deliberately adds the smallest amount of new code that closes the genuine gap (universal discovery provenance + one scheduled orchestration entry point) rather than re-deriving universe management, feature computation, consensus, scoring, or selection, all of which already exist and are already tested by their own EPICs. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->