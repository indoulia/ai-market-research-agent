# EPIC-057 — Recommendation Revalidation Engine

Status: DONE
Execution Status: COMPLETED

## Objective
Automatically determine whether an active recommendation remains valid after material market, news, event, or model changes.

## Scope
- Detect material changes in recommendation inputs.
- Revalidate active recommendations.
- Produce UNCHANGED, UPDATED, WITHDRAWN, or EXPIRED outcomes.
- Preserve every prior recommendation version.
- Record the exact revalidation reason and evidence timestamp.

## Acceptance Criteria
- Revalidation is deterministic and idempotent.
- Material invalidation cannot leave a stale recommendation active.
- Historical versions remain immutable.
- Tests cover target/SL proximity, horizon expiry, data changes, and model changes.

## Dependencies
Previous: EPIC-056.
Next: EPIC-058.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-057

### Branch

autonomous/epic-m1-62, branched cleanly from `main` (the declared dependency -- EPIC-056 -- is already merged).

### Objective

Automatically determine whether an active recommendation remains valid after material market, news, event, or model changes, producing an explicit `UNCHANGED`/`UPDATED`/`WITHDRAWN`/`EXPIRED` outcome.

### Design

`revalidate_recommendation` composes EPIC-031's `RecommendationObservation` (current price/return, elapsed time), EPIC-030's `check_market_data_freshness` (stale/missing data), and EPIC-042's `RecommendationPublication` (target/stop-loss proximity) -- it never recomputes any of them. Checks run in a fixed priority order (scope: "detect material changes in recommendation inputs"):
1. **Horizon expiry** — elapsed days meet or exceed the recommendation's own horizon with no closing outcome yet → `EXPIRED`.
2. **Stop-loss proximity** — current return within `PROXIMITY_THRESHOLD` (90%) of the stop → `WITHDRAWN`.
3. **Stale/missing market data** — EPIC-030's own freshness check fails → `WITHDRAWN`.
4. **Model version changed** — a newer `model_version` has been used platform-wide since this prediction was made → `UPDATED`.
5. **Target proximity** — current return within `PROXIMITY_THRESHOLD` of the target → `UPDATED`.
6. Otherwise → `UNCHANGED`.

This directly maps to the AC's four required test categories: target/SL proximity (checks 2 and 5), horizon expiry (check 1), data changes (check 3), and model changes (check 4).

### Preserving Prior Versions

This module has no write path to `Prediction` or any of the tables it reads from -- "historical versions remain immutable" (AC) holds structurally. A caller who decides `UPDATED` warrants an actual new version composes this with EPIC-050's `create_recommendation_revision` separately, using a freshly-scored `Prediction` this module never produces itself -- `revalidate_recommendation` only ever *judges*, matching this platform's established "propose/judge here, act there" split. `test_revalidation_never_writes_to_prediction` proves this directly.

### Determinism & Idempotency

`revalidate_recommendation` is idempotent by `(prediction_id, checked_at)` -- re-running the exact same check at the exact same point in time returns the original outcome unchanged rather than re-deriving it (AC: "revalidation is deterministic and idempotent"), while a later `checked_at` legitimately produces a fresh, independent row in the same append-only history (AC: "record the exact revalidation reason and evidence timestamp").

### Never Leaving a Stale Recommendation Active

Both material-invalidation paths (stop-loss proximity, stale/missing data) resolve to `WITHDRAWN` rather than `UNCHANGED` (AC: "material invalidation cannot leave a stale recommendation active") -- there is no code path where genuinely bad evidence still produces a "no change" verdict.

### Files Changed

- `app/recommendation_revalidation.py` — new: `revalidate_recommendation`, `get_revalidation_history`, outcome constants.
- `app/models.py` — new `RecommendationRevalidationOutcome` model.
- `migrations/versions/0044_recommendation_reval.py` — new migration.
- `tests/test_recommendation_revalidation.py` — new: 9 tests.
- `docs/epics/EPIC-057-recommendation-revalidation.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_recommendation_revalidation.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0044_recommendation_reval`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0043` through `0044` (verified `recommendation_revalidation_outcomes` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **548 passed, 0 failed** (539 pre-existing from `main` + 9 new).
- `pytest -q tests/test_recommendation_revalidation.py -v`: **9 passed** — a normal case is `UNCHANGED`; horizon expiry is detected; stop-loss proximity triggers `WITHDRAWN`; stale market data triggers `WITHDRAWN`; a platform-wide model version change triggers `UPDATED`; target proximity triggers `UPDATED`; revalidation is idempotent for the same `checked_at`; revalidation never writes to `Prediction`; the history retains multiple checks over time.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Revalidation is deterministic and idempotent (idempotent by `(prediction_id, checked_at)`; proven by test).
- [x] Material invalidation cannot leave a stale recommendation active (`WITHDRAWN`, never `UNCHANGED`, for both proximity-to-stop and stale-data cases).
- [x] Historical versions remain immutable (no write path to `Prediction`; proven by test).
- [x] Tests cover target/SL proximity, horizon expiry, data changes, and model changes (all four covered explicitly).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof that revalidation never mutates the underlying `Prediction`. This EPIC composes EPIC-030/EPIC-031/EPIC-042's already-existing outputs into one deterministic, prioritized decision engine without duplicating or touching any of them, and deliberately stops short of actually producing a new recommendation version itself -- that composition with EPIC-050 remains a caller's decision. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
