# EPIC-M1.19 — Watchlist Positive Analysis

**Status:** DONE  
**Execution Status:** COMPLETED  
**Approved By:** User  
**Priority:** P1

## Objective
Evaluate active watchlist stocks through the existing quantitative prediction, consensus, scoring, and horizon pipeline without creating a recommendation merely because a stock is watched.

## Scope
1. Evaluate active watchlist symbols using point-in-time market/model data.
2. Reuse the existing positive-consensus contract.
3. Reuse the existing opportunity score.
4. Reuse supported 1/3/5/7-day horizon selection.
5. Record qualification and non-qualification reasons.
6. Persist analysis timestamp and relevant model/data versions.
7. Make repeated analysis idempotent for the same watchlist evaluation context.

## Non-goals
- Issuing a recommendation solely from watchlist membership.
- Changing consensus, scoring, or horizon rules.
- Trading automation.
- Outcome learning.

## Acceptance Criteria
- [ ] Watchlist candidates use the same quantitative path as normal candidates.
- [ ] Watchlist membership cannot bypass qualification.
- [ ] Qualification and rejection reasons are traceable.
- [ ] Point-in-time data/model versions are retained.
- [ ] Duplicate evaluations are prevented.
- [ ] Tests cover positive, rejected, stale-data, and duplicate cases.

## Dependency Chain
### Previous / Required
- **M1.18 — Watchlist Intake**
- **M1.8 — Positive Consensus Engine**
- **M1.9 — Positive Opportunity Scoring**
- **M1.10 — Positive Horizon Selection**
- **M1.13 — Positive Recommendation Generator**

### Next / Unlocks
- **M1.20 — Watchlist Decision History**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Do not create a recommendation from watchlist membership alone. All positive qualification must pass the existing deterministic contracts.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.19

### Branch

autonomous/epic-m1-19, branched cleanly from `main` (all five declared dependencies -- M1.18, M1.8, M1.9, M1.10, M1.13 -- are already merged).

### Objective

Evaluate active watchlist (M1.18) stocks through the identical positive-consensus/scoring/horizon pipeline internally scanned and externally discovered candidates already use, so watchlist membership alone can never create a recommendation.

### Design Decisions

- **No new table or migration.** This EPIC's real content -- "reuse the existing consensus/score/horizon pipeline" -- is already fully embodied by M1.13's `generate_recommendation_for_candidate`, reachable via M1.17's `record_discovery` + `route_discovery_through_pipeline`. `app/watchlist_analysis.py`'s `analyze_watchlist_stock` is a thin wrapper: verify the stock is currently active on the watchlist (M1.18's `is_active`), then call the exact same two M1.17 functions M1.17 itself and M1.33 already call, tagged `SOURCE_WATCHLIST` (added to `app/discovery.py` alongside `SOURCE_CHATGPT`/`SOURCE_DAILY_UNIVERSE_SCAN`).
- **Deliberately not built on `app/watchlist.py` (M1.7)'s `evaluate_watchlist_candidate`.** That function only reuses M1.8's consensus contract; score and horizon are caller-supplied kwargs, not computed. This EPIC's scope explicitly requires reusing M1.9's opportunity score and M1.10's horizon selection too (scope items 3-4), which only M1.13's generator provides end to end. `app/watchlist.py` is untouched by this EPIC.
- **"Point-in-time market/model data" (scope item 1) comes from the `ScanCandidate` row** already computed for that stock in a given `scan_id` (M1.12) -- a watchlist stock can only be added if its underlying `Stock` is part of the active universe (M1.18's own validation), so every active watchlist stock is, by construction, a candidate in each day's universe scan once that scan has run.
- **`StockNotOnWatchlistError`** is this EPIC's one genuinely new piece of behavior: `analyze_watchlist_stock` refuses to run for a stock that is not *currently* active on the watchlist (per M1.18's derived state, not a point-in-time snapshot), before touching the pipeline at all -- proven directly by tests for both "never watchlisted" and "watchlisted then removed."
- **Failure-mode reuse, not special-casing:** a scan-excluded stock (`stale_market_data`, etc.) raises M1.13's own `CandidateNotEligibleError` unchanged; there is no watchlist-specific handling of that case, matching how M1.17 already treats the identical situation for externally discovered candidates.
- **Idempotency (scope item 7)** is inherited, not reimplemented: `record_discovery`'s `(scan_id, stock_id, source)` uniqueness and `route_discovery_through_pipeline`'s existing-generation check together make repeated analysis for the same `(scan_id, stock_id)` a true no-op.
- **"Record qualification and non-qualification reasons" / "persist analysis timestamp and relevant model/data versions" (scope items 5-6)** fall out of the reused rows: `RecommendationGeneration.outcome`/`failed_criteria`/`consensus_contract_version` always populate regardless of qualification; a qualifying `Prediction` additionally carries `model_version`, `feature_version`, `scoring_contract_version`, `horizon_selection_version`; and the `DiscoveryRecord`'s `discovered_at` is the analysis timestamp.

### Files Changed

- `app/watchlist_analysis.py` — new: `analyze_watchlist_stock`, `StockNotOnWatchlistError`.
- `app/discovery.py` — added `SOURCE_WATCHLIST` constant (no behavior change to existing M1.17 functions).
- `tests/test_watchlist_analysis.py` — new: 7 tests.
- `docs/epics/EPIC-M1.19-watchlist-positive-analysis.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_watchlist_analysis.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from M1.18's `0018_watchlist_entries`)

### Test Results

- `pytest -q`: **205 passed, 0 failed** (198 pre-existing from `main` + 7 new).
- `pytest -v tests/test_watchlist_analysis.py`: **7 passed** — an active watchlist stock that qualifies is analyzed and produces a real scored `Prediction`; a watchlisted stock with a compelling-looking-but-quantitatively-failing signal (`predicted_probability=0.10`) is still `NOT_QUALIFIED` with `failed_criteria=["model_probability"]` and zero `Prediction` rows -- proving watchlist membership cannot buy qualification; a scan-excluded (`stale_market_data`) candidate raises `CandidateNotEligibleError` unchanged; a stock that was watchlisted and then removed, and a stock that was never watchlisted at all, both raise `StockNotOnWatchlistError` before any analysis; repeated analysis for the same scan/stock is idempotent (one `Prediction` row); and the resulting `DiscoveryRecord` is tagged `SOURCE_WATCHLIST` and linked to its `RecommendationGeneration`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0018_watchlist_entries` (no migration in this EPIC).

### Acceptance Criteria

- [x] Watchlist candidates use the same quantitative path as normal candidates (identical `generate_recommendation_for_candidate` call, via M1.17's routing).
- [x] Watchlist membership cannot bypass qualification (proven by `test_watchlist_membership_cannot_bypass_positive_consensus`).
- [x] Qualification and rejection reasons are traceable (`RecommendationGeneration.outcome`/`failed_criteria`).
- [x] Point-in-time data/model versions are retained (`Prediction`'s version columns when qualifying; `DiscoveryRecord.discovered_at` always).
- [x] Duplicate evaluations are prevented (idempotency test).
- [x] Tests cover positive, rejected, stale-data, and duplicate cases (plus the two watchlist-membership-gating cases this EPIC itself introduces).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence. The decision to build on M1.17's routing machinery rather than M1.7's watchlist evaluator is a documented design choice driven directly by the scope's explicit requirement to reuse M1.9/M1.10, which only M1.13's generator provides. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
