# EPIC-M1.51 — Recommendation Tracking View

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** M1.36, M1.47, M1.48

## Objective
Give users a clear longitudinal view of every active and completed recommendation from publication through outcome.

## Scope
- Entry/reference price.
- Target and stop loss.
- Horizon and elapsed time.
- Current price and return.
- Target/SL progress.
- Confidence and score at publication.
- Evidence snapshot.
- Outcome status and history.

## Acceptance Criteria
- Active recommendations can be tracked over time.
- Historical recommendations remain viewable after completion.
- Original recommendation values are visible beside current state.
- Tracking updates do not rewrite the original recommendation snapshot.
- Users can inspect outcome history by stock, recommendation, horizon, and date.
- Tests cover active, completed, and missing-data states.

## Dependency Chain
M1.36/M1.47/M1.48 → M1.51 → M1.55+

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.51

### Branch

autonomous/epic-m1-51, branched cleanly from `main` (all three declared dependencies -- M1.36, M1.47, M1.48 -- are already merged).

### Objective

Give users a clear longitudinal view of every active and completed recommendation from publication through outcome, by composing already-merged modules rather than introducing any new persisted state.

### Design

`build_recommendation_tracking_view` assembles one `RecommendationTrackingView` per prediction from:
- **Entry/reference price, horizon, confidence, opportunity score, predicted probability at publication**: read directly from the immutable `Prediction` row.
- **Target/stop-loss, upside/downside percentage, reward/risk**: M1.47's `RecommendationPublication` (`None` if never published).
- **Current price/return, elapsed time**: the latest M1.36 `RecommendationObservation` (day-by-day tracking), `None`/`0` if none recorded yet.
- **Target/SL progress**: `current_return / upside_percentage` and `-current_return / downside_percentage` respectively -- unclamped, so "120% of the way to target" (already surpassed before an outcome closure) is visible rather than hidden.
- **Outcome status and history**: the `PredictionOutcome` row if one exists, else the explicit `OPEN` status -- never fabricated.
- **Evidence snapshot**: M1.48's complete `RecommendationEvidenceItem` set for the prediction.

`get_recommendation_tracking_views` filters by symbol, prediction id, horizon, and/or date range (AC: "users can inspect outcome history by stock, recommendation, horizon, and date") and deliberately applies no filter on completion state, so historical (completed) recommendations remain fully viewable alongside active ones (AC: "historical recommendations remain viewable after completion").

### Immutability

This module is entirely read-only -- it has no write path anywhere, so "tracking updates do not rewrite the original recommendation snapshot" (AC) holds trivially. Every table it reads from is already immutable in its own module (`Prediction`, `RecommendationPublication`, `RecommendationEvidenceItem`, `RecommendationObservation`). `test_tracking_view_never_writes_anything` proves the underlying `Prediction` is untouched by building views.

### Files Changed

- `app/recommendation_tracking_view.py` — new: `build_recommendation_tracking_view`, `get_recommendation_tracking_views`, `RecommendationTrackingView` dataclass, `OUTCOME_STATUS_OPEN`.
- `tests/test_recommendation_tracking_view.py` — new: 8 tests.
- `docs/epics/EPIC-M1.51-recommendation-tracking-view.md` — this completion report.

No migration: pure read-side composition of existing tables.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_recommendation_tracking_view.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0035_confidence_quality`, unchanged -- confirms no migration drift)

### Test Results

- `pytest -q`: **451 passed, 0 failed** (443 pre-existing from `main` + 8 new).
- `pytest -q tests/test_recommendation_tracking_view.py -v`: **8 passed** — an active recommendation shows progress with `OPEN` status and no outcome; a completed recommendation remains fully viewable with the real outcome status; missing market data shows no current price while original values stay intact; a captured evidence snapshot is included in full; original entry price stays visible beside a moved current price; no publication is represented explicitly (`None`, not fabricated); views are filterable by symbol, horizon, prediction id, and date; building views never mutates the underlying `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: passed, single head unchanged (no migration in this EPIC).

### Acceptance Criteria

- [x] Active recommendations can be tracked over time (`RecommendationObservation` history + live progress fields).
- [x] Historical recommendations remain viewable after completion (no completion-state filter anywhere in the query path).
- [x] Original recommendation values are visible beside current state (`entry_price`/`confidence_at_publication`/etc. alongside `current_price`/`current_return`).
- [x] Tracking updates do not rewrite the original recommendation snapshot (no write path exists in this module; proven by test).
- [x] Users can inspect outcome history by stock, recommendation, horizon, and date (`get_recommendation_tracking_views` filter parameters).
- [x] Tests cover active, completed, and missing-data states (all three covered explicitly).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a direct proof that this module never writes anywhere. This EPIC introduces no new persisted state at all -- it purely composes M1.36's daily observations, M1.47's target/stop-loss publication, and M1.48's evidence snapshot with the underlying immutable `Prediction`/`PredictionOutcome` into one coherent, filterable view. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
