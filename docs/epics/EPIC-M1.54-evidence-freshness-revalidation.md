# EPIC-M1.54 — Evidence Freshness & Revalidation

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** M1.35, M1.48

## Objective
Ensure recommendation evidence remains fresh enough for the selected horizon and automatically identify recommendations that require revalidation.

## Scope
- Freshness rules by evidence category.
- Horizon-aware freshness thresholds.
- Detect stale, missing, conflicting, and changed information.
- Trigger revalidation when material evidence changes.
- Record revalidation reason and result.

## Acceptance Criteria
- Each evidence category has an explicit freshness policy.
- Freshness is evaluated relative to recommendation horizon.
- Material changes trigger revalidation.
- Stale evidence is visible to users and downstream scoring.
- Revalidation never silently mutates the original snapshot.
- Tests cover fresh, stale, changed, and unavailable evidence.

## Dependency Chain
M1.35/M1.48 → M1.54 → M1.55

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.54

### Branch

autonomous/epic-m1-54, branched cleanly from `main` (both declared dependencies -- M1.35 and M1.48 -- are already merged).

### Objective

Ensure recommendation evidence (M1.48) remains fresh enough for the selected horizon, and record whenever a material change requires revalidation -- without ever mutating the original evidence snapshot.

### Freshness Policy by Evidence Category

Each of M1.48's five evidence categories maps to one of M1.35's existing per-data-type base thresholds (`MARKET_SECTOR`/`TECHNICAL_VOLUME` → `DATA_TYPE_MARKET`; `NEWS`/`EVENT` → `DATA_TYPE_NEWS_EVENT`; `FUNDAMENTAL` → `DATA_TYPE_FUNDAMENTAL`), reused unchanged (AC: "each evidence category has an explicit freshness policy").

### Horizon-Aware Thresholds

`horizon_aware_threshold` scales the base threshold by `HORIZON_FRESHNESS_FRACTION` (0.5) × the prediction's own horizon in days, and never returns a threshold smaller than the base (AC: "freshness is evaluated relative to recommendation horizon"). A 1-day-horizon recommendation gets exactly M1.35's flat threshold; a 7-day-horizon recommendation gets up to 3.5 days of tolerance for market data -- proven directly by `test_horizon_aware_threshold_tolerates_more_staleness_for_longer_horizons`, where 2 days of staleness fails the flat M1.35 threshold but passes the horizon-aware one.

### Detecting Stale, Missing, and Changed Evidence

`revalidate_evidence` checks, in order: (1) evidence already `UNAVAILABLE` at snapshot time → `MISSING`; (2) the snapshot's own `evidence_timestamp` now exceeds the horizon-aware threshold as of `checked_at` → `STALE`; (3) for `TECHNICAL_VOLUME` specifically, a real, cheap re-check via M1.35's `check_market_data_freshness` detects newly-arrived `MarketPrice` data since the snapshot was captured → `CHANGED` (scope: "trigger revalidation when material evidence changes"). `CONFLICTING` is defined as a reserved constant for future evidence categories with two independent sources -- no category in this repo has that shape yet, matching M1.35's own honest-partial-coverage precedent for categories without a real check path.

### Audit Trail

Every check -- fresh or not -- is recorded as a new, immutable `EvidenceRevalidationCheck` row (AC: "record revalidation reason and result"), mirroring M1.35's own `DataFetchAttempt` precedent of logging every attempt, not only the ones that find a problem.

### Never Mutates the Original Snapshot

This module has no write path to `RecommendationEvidenceItem` at all -- `test_revalidation_never_mutates_the_original_snapshot` proves the M1.48 snapshot's `status`/`reference`/`evidence_timestamp`/`is_stale` are byte-for-byte identical before and after a revalidation check that itself found staleness (AC: "revalidation never silently mutates the original snapshot"). `EvidenceRevalidationCheck` itself carries a `before_update` immutability guard.

### Stale Evidence Visibility

Both M1.48's own `RecommendationEvidenceItem.is_stale`/`status` and this EPIC's fresh, horizon-aware `EvidenceRevalidationCheck.revalidation_required`/`reason` are queryable (`get_revalidation_history`), giving downstream consumers (UI, scoring) two complementary, always-available signals of staleness (AC: "stale evidence is visible to users and downstream scoring").

### Files Changed

- `app/evidence_revalidation.py` — new: `revalidate_evidence`, `horizon_aware_threshold`, `get_revalidation_history`, reason constants, `EvidenceRevalidationImmutableError`.
- `app/models.py` — new `EvidenceRevalidationCheck` model.
- `migrations/versions/0037_evidence_revalidation.py` — new migration.
- `tests/test_evidence_revalidation.py` — new: 9 tests.
- `docs/epics/EPIC-M1.54-evidence-freshness-revalidation.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_evidence_revalidation.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0037_evidence_revalidation`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0036` through `0037` (verified `evidence_revalidation_checks` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **478 passed, 0 failed** (469 pre-existing from `main` + 9 new).
- `pytest -q tests/test_evidence_revalidation.py -v`: **9 passed** — the horizon-aware threshold never shrinks below M1.35's base policy; fresh evidence requires no revalidation; stale, missing, and changed evidence each correctly trigger revalidation with the right reason; a longer horizon tolerates more staleness than the flat M1.35 threshold would allow; a revalidation check never mutates the original M1.48 snapshot; a check row is immutable after creation; the full revalidation history retains every check performed.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Each evidence category has an explicit freshness policy (mapped to M1.35's per-data-type base thresholds, reused unchanged).
- [x] Freshness is evaluated relative to recommendation horizon (`horizon_aware_threshold`, proven to tolerate more staleness for a longer horizon).
- [x] Material changes trigger revalidation (`REASON_CHANGED`, detected via a real re-check for `TECHNICAL_VOLUME`).
- [x] Stale evidence is visible to users and downstream scoring (queryable via `get_revalidation_history` and M1.48's own `is_stale`/`status`).
- [x] Revalidation never silently mutates the original snapshot (no write path to `RecommendationEvidenceItem`; proven directly by test).
- [x] Tests cover fresh, stale, changed, and unavailable evidence (all four covered explicitly).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that a longer horizon genuinely tolerates more staleness than M1.35's flat threshold would. This EPIC generalizes M1.35's freshness policy to be horizon-aware without modifying M1.35 itself, and never touches M1.48's own immutable snapshot table. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
