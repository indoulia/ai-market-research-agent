# EPIC-021 — Market Regime Detection

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1

## Objective
Classify the market environment at recommendation time so performance can be measured by regime and future scoring can use regime-aware evidence.

## Scope
- Define deterministic market-regime categories.
- Calculate regime from information available at `as_of_timestamp` only.
- Persist regime and regime version with recommendation context.
- Support historical replay without future-data leakage.
- Add deterministic tests for each regime and boundary.

## Non-goals
- Changing recommendation scores.
- Automatic model promotion.
- Trading decisions.

## Acceptance Criteria
- Every recommendation can be associated with a regime when sufficient data exists.
- Regime classification is reproducible for the same inputs.
- No future data is used.
- Regime version is traceable.
- Historical replay produces the same regime for the same historical timestamp.

## Dependency Chain
**Previous:** EPIC-018, EPIC-070, EPIC-073  
**Next:** EPIC-022, EPIC-024

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-021

### Branch

autonomous/epic-m1-26, branched cleanly from `main` (all three declared dependencies -- EPIC-018, EPIC-070, EPIC-073 -- are already merged).

### Objective

Classify the market environment for each daily candidate scan from breadth and volatility, deterministically and point-in-time safely, so performance can later be measured by regime.

### Design Decisions

- **This repo has no market-wide index data source** (e.g. a NIFTY 50 feed) -- only per-stock `MarketPrice` history. "Market regime" is therefore defined as an aggregate over the platform's own scanned universe on a given day: breadth (the fraction of that day's *eligible* `ScanCandidate` rows with a positive `sma20_distance`) and average volatility (mean `atr_percent` across the same population), rather than an external index. This is a genuine, documented scope decision open to reviewer adjustment.
- **New table `market_regimes`** (migration `0021`), one immutable row per `scan_id` (unique). No new column on `Prediction`/`RecommendationGeneration`: a recommendation's regime is derivable by joining through its already-existing `ScanCandidate.scan_id`, so "persist regime and regime version with recommendation context" (scope item 3) is satisfied without touching any already-merged, heavily-tested table.
- **`_classify(breadth_positive_ratio, average_atr_percent) -> str`** is a pure function over two ratios, with fixed, documented, versioned threshold constants (`REGIME_RULE_VERSION = "REG-001"`, `BULLISH_BREADTH_THRESHOLD = 0.60`, `BEARISH_BREADTH_THRESHOLD = 0.40`, `HIGH_VOLATILITY_ATR_THRESHOLD = 0.03`) -- a deterministic step function, never learned from outcomes. Six possible labels (`BULLISH`/`BEARISH`/`NEUTRAL` × `LOW_VOL`/`HIGH_VOL`), or just the trend label alone when no ATR% data exists at all (explicit, not a fabricated volatility guess).
- **"No future data is used" (AC) holds for free**, not by new logic in this module: `ScanCandidate.sma20_distance`/`atr_percent` are themselves already computed by EPIC-015 only from `MarketPrice` rows up to that scan's cutoff. Regime classification reads those already-point-in-time-safe fields; no new query against raw price history is introduced here.
- **"Support historical replay without future-data leakage" (scope item 4)** is satisfied by keeping `_classify` a pure function independent of any database read -- a future replay caller (EPIC-073-style) can feed it a replayed breadth ratio/average ATR% computed from point-in-time-only candidates and get the identical deterministic label. This EPIC does not itself modify `app/historical_replay.py`; that integration is left to a caller.
- **Idempotent by `scan_id` uniqueness** (`classify_market_regime`), matching this platform's established scan-scoped idempotency pattern (e.g. EPIC-017's `select_recommendations_for_scan`): the first classification is the historical record and is never re-derived, even if more candidates are added to the scan afterward (proven directly by a test).
- **Ineligible candidates are excluded from breadth/volatility** entirely (only `eligible=True` rows contribute), and a scan with zero eligible candidates raises `InsufficientRegimeEvidenceError` rather than fabricating a regime (AC: "when sufficient data exists").

### Files Changed

- `app/market_regime.py` — new: `classify_market_regime`, `_classify`, threshold/version constants, `InsufficientRegimeEvidenceError`.
- `app/models.py` — new `MarketRegime` model.
- `migrations/versions/0021_market_regimes.py` — new migration.
- `tests/test_market_regime.py` — new: 7 tests.
- `docs/epics/EPIC-021-market-regime-detection.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_market_regime.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0021_market_regimes`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0020` through `0021` (verified `market_regimes` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **248 passed, 0 failed** (241 pre-existing from `main` + 7 new).
- `pytest -v tests/test_market_regime.py`: **7 passed** — a scan with zero eligible candidates raises `InsufficientRegimeEvidenceError`; ineligible candidates are correctly excluded from the breadth calculation (also raising, since none remain eligible); a 6/10 positive-breadth, low-ATR population classifies `BULLISH_LOW_VOL`; a 4/10 positive-breadth, high-ATR population classifies `BEARISH_HIGH_VOL`; an exact 5/10 (50%) breadth classifies `NEUTRAL_LOW_VOL`; a population with no ATR data at all omits the volatility suffix entirely (`BULLISH`, not a fabricated `BULLISH_LOW_VOL`); and re-classifying the same scan after adding more candidates returns the original, unchanged row.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every recommendation can be associated with a regime when sufficient data exists (joinable via `scan_id`; `InsufficientRegimeEvidenceError` when not).
- [x] Regime classification is reproducible for the same inputs (`_classify` is a pure function; `classify_market_regime` is idempotent).
- [x] No future data is used (inherits EPIC-015's own point-in-time-safe feature computation).
- [x] Regime version is traceable (`regime_rule_version` on every row).
- [x] Historical replay produces the same regime for the same historical timestamp (`_classify`'s purity makes this true by construction for any caller feeding it point-in-time-derived ratios).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip. The central scope decision -- defining "market regime" as scan-universe breadth/volatility rather than an external index this repo doesn't have -- is documented above for reviewer scrutiny. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
