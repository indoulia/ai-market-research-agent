# EPIC-043 — Recommendation Evidence Snapshot

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** EPIC-030, EPIC-042

## Objective
Capture the evidence that justified a recommendation so users and future learning can see what the system knew when the decision was made.

## Scope
- Fundamental evidence.
- News evidence.
- Event evidence.
- Market and sector evidence.
- Technical/volume evidence.
- Source, timestamp, freshness, and evidence status.
- Recommendation-time immutable snapshot.

## Acceptance Criteria
- Every recommendation records all required evidence categories or an explicit unavailable state.
- Every evidence item has source/reference metadata and timestamp where available.
- Stale evidence is clearly identified.
- Historical snapshots cannot be silently overwritten.
- UI/API can retrieve the complete recommendation evidence snapshot.
- Tests cover missing, stale, and fresh evidence.

## Dependency Chain
EPIC-030 → EPIC-043 → EPIC-044/EPIC-049+

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-043

### Branch

autonomous/epic-m1-48, branched cleanly from `main` (both declared dependencies -- EPIC-030 and EPIC-042 -- are already merged).

### Objective

Capture the evidence that justified a recommendation -- fundamental, news, event, market/sector, and technical/volume -- as an immutable, per-category snapshot frozen at recommendation time.

### Evidence Categories & Sourcing

- **Technical/volume**: real, always available for any qualified recommendation -- sourced directly from the `ScanCandidate` EPIC-016 generated it from, freshness checked via EPIC-030's own `check_market_data_freshness`.
- **Market/sector**: real where available -- `Stock.sector` (always present) and EPIC-021's `MarketRegime` for the originating scan ("where available", this platform's established pattern since not every scan is classified).
- **News**: real where available -- EPIC-020's `DiscoveryRecord.rationale` is the one genuine qualitative narrative this platform records about why a candidate was surfaced; exposed as "news evidence" rather than fabricating a news-article feed that doesn't exist.
- **Fundamental** and **event**: no ingestion pipeline exists for either in this repo, so both are always recorded `UNAVAILABLE` -- an honest, explicit statement of what the system did not know, never a fabricated value (AC: "every recommendation records all required evidence categories or an explicit unavailable state"). This mirrors EPIC-030's own honest-partial-coverage stance for exactly these two data types.

### Source/Reference/Timestamp Metadata

Every evidence item records a `source` (e.g. `DISCOVERY:CHATGPT`, `SCAN_CANDIDATE_TECHNICALS`, `STOCK_SECTOR+MARKET_REGIME`), a `reference` (the actual free-text evidence value), and an `evidence_timestamp` where a real one exists (AC: "every evidence item has source/reference metadata and timestamp where available"). Categories with no real timestamp (`FUNDAMENTAL`, `EVENT`, or `MARKET_SECTOR` with only a static sector and no classified regime) leave `evidence_timestamp` as `None` rather than fabricating one.

### Freshness / Staleness

Reuses EPIC-030's `is_data_fresh`/`check_market_data_freshness`/`DATA_TYPE_MARKET`/`DATA_TYPE_NEWS_EVENT` unchanged -- technical/volume evidence is checked against the underlying `MarketPrice` freshness, market/sector evidence's regime component is checked against the classified scan's own date, and news evidence is checked against the discovery's own timestamp. `status` is `STALE` whenever the underlying data exists but has aged past its type's freshness threshold (AC: "stale evidence is clearly identified"), distinct from `UNAVAILABLE` (no data exists at all).

### Immutability & Retrieval

One row per `(prediction_id, evidence_category)`, unique-constrained and idempotent: `capture_evidence_snapshot` returns the original five rows unchanged on a rerun, even if the underlying evidence (a stock's sector, a later market-price update) has since changed (AC: "historical snapshots cannot be silently overwritten"). `RecommendationEvidenceItem` carries a `before_update` immutability guard (`RecommendationEvidenceImmutableError`). `get_evidence_snapshot(session, prediction_id)` retrieves the complete, consistently-ordered snapshot in one call (AC: "UI/API can retrieve the complete recommendation evidence snapshot").

### Files Changed

- `app/evidence_snapshot.py` — new: `capture_evidence_snapshot`, `get_evidence_snapshot`, category/status constants, `RecommendationEvidenceImmutableError`.
- `app/models.py` — new `RecommendationEvidenceItem` model.
- `migrations/versions/0033_evidence_items.py` — new migration (named `0033_evidence_items` rather than the fuller `0033_recommendation_evidence_items` -- the latter is 34 characters, exceeding this repo's `alembic_version.version_num VARCHAR(32)` column; caught by the real-Postgres migration validation step, not by the SQLite-backed unit tests, which is exactly why that validation step exists).
- `tests/test_evidence_snapshot.py` — new: 11 tests.
- `docs/epics/EPIC-043-recommendation-evidence-snapshot.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_evidence_snapshot.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0033_evidence_items`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0032` through `0033` (verified `recommendation_evidence_items` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply) -- this step caught and required fixing the revision-id length issue above.

### Test Results

- `pytest -q`: **425 passed, 0 failed** (414 pre-existing from `main` + 11 new). This run includes this repo's real-Postgres integrity tests (`tests/test_fresh_database_migration.py`, `tests/test_recommendation_history_db_integrity.py`), which caught the revision-id length regression before it reached `main`.
- `pytest -q tests/test_evidence_snapshot.py -v`: **11 passed** — fundamental and event are always `UNAVAILABLE`; every category is captured or explicitly unavailable with a valid status and version; technical/volume evidence is `AVAILABLE` when the market price is current and `STALE` when it's five days old; technical/volume is `UNAVAILABLE` with no market price at all; news evidence captures the real discovery rationale and source, and is `UNAVAILABLE` without a discovery record; market/sector evidence includes both sector and regime when classified, and sector alone (no regime mention) when not; the snapshot is idempotent across reruns and immutable after creation; the complete snapshot is retrievable in the documented category order.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every recommendation records all required evidence categories or an explicit unavailable state (`FUNDAMENTAL`/`EVENT` always `UNAVAILABLE`; `NEWS`/`MARKET_SECTOR` `UNAVAILABLE` when no underlying data exists).
- [x] Every evidence item has source/reference metadata and timestamp where available (`source`/`reference`/`evidence_timestamp` populated whenever real data backs a category).
- [x] Stale evidence is clearly identified (`STATUS_STALE`, distinct from `UNAVAILABLE`, via EPIC-030's reused freshness checks).
- [x] Historical snapshots cannot be silently overwritten (idempotent capture; `before_update` immutability guard, proven by test).
- [x] UI/API can retrieve the complete recommendation evidence snapshot (`get_evidence_snapshot`, one call, consistently ordered).
- [x] Tests cover missing, stale, and fresh evidence (all three states tested for technical/volume; missing/available tested for news and market/sector).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip that caught and required fixing a revision-id length bug before it could reach `main`. This EPIC composes EPIC-030's freshness policy, EPIC-021's regime classification, EPIC-020's discovery rationale, and EPIC-016's own technical fields into a purely additive, honestly-partial evidence layer -- it never fabricates data for the two categories (fundamental, event) this repo has no real ingestion pipeline for. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
