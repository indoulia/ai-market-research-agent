# EPIC-M1.24 — Historical Recommendation Replay

**Status:** APPROVED  
**Execution Status:** VALIDATING  
**Approved By:** User  
**Priority:** P1

## Objective
Reconstruct historical recommendation decisions from point-in-time inputs so the system can validate rules, scores, confidence, discovery, and learning changes without future-data leakage.

## Scope
1. Replay historical recommendations using their original as-of timestamp.
2. Reconstruct only information that would have been available at that timestamp.
3. Recompute features, predictions, consensus, score, confidence, and horizon where required.
4. Compare replayed decisions with persisted original decisions.
5. Record replay configuration and software/model versions.
6. Detect data leakage or unavailable historical inputs explicitly.
7. Make replay deterministic and repeatable.

## Non-goals
- Changing historical production records.
- Production model promotion.
- Live trading.
- Using future outcomes as model inputs.

## Acceptance Criteria
- [ ] Historical replay is point-in-time safe.
- [ ] Future data cannot enter replay inputs.
- [ ] Replay is deterministic for identical inputs and versions.
- [ ] Original records remain immutable.
- [ ] Missing historical inputs produce explicit replay limitations.
- [ ] Replay differences are attributable to version/input changes.
- [ ] Tests cover leakage and reproducibility cases.

## Dependency Chain
### Previous / Required
- **M1.23 — Recommendation Confidence Analysis**
- **M1.12 — Market Universe & Daily Candidate Scan**
- **M1.13 — Positive Recommendation Generator**

### Next / Unlocks
- **M1.25 — Out-of-Sample Recommendation Validation**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Replay must never use information published after the historical decision timestamp. Any unavailable historical input must be surfaced rather than approximated silently.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.24

### Branch

autonomous/epic-m1-24, branched cleanly from `main` (all three declared dependencies -- M1.23, M1.12, M1.13 -- are already merged).

### Objective

Reconstruct a historical recommendation decision using only market data that existed as of its original scan date, run through the platform's real current consensus/scoring/horizon logic, and compare it against what was actually persisted -- without ever touching production recommendation records.

### Design Decisions

- **New table `replay_runs`** (migration `0020`, chains off M1.23's implicit head, `0019`): one row per replay attempt, linked to the original `RecommendationGeneration` (not `Prediction` -- see below). No uniqueness constraint on that link: a generation can be replayed repeatedly (e.g. after a rule/model change), and each attempt is its own auditable record, deliberately not deduped, so "replay differences are attributable to version/input changes" (AC) can be compared across multiple runs over time.
- **Anchored on `RecommendationGeneration`, not `Prediction`.** A rejected candidate never gets a `Prediction` row at all (M1.13), but "would a rule/model change have flipped this rejection" is exactly the question this EPIC exists to answer, so a rejected generation must be replayable too. The original scan's `scan_date` (via the generation's `ScanCandidate`) supplies the point-in-time cutoff for every replay, regardless of whether the original decision qualified.
- **Reuses `app.scan._evaluate_stock` directly** rather than reimplementing the ~50-line pandas feature-computation pipeline a second time — a deliberate, documented choice to import one internal ("underscore") helper across module boundaries instead of risking two feature implementations drifting apart. `app/scan.py` itself is not modified. Point-in-time safety (scope items 1, 2, 6) comes from bounding the `MarketPrice` query to `timestamp <= cutoff` (`cutoff` derived from the *original* `scan_date`, mirroring `app/scan.py`'s own cutoff computation exactly) *before* any feature computation happens — a future-dated row can never enter the pandas frame `_evaluate_stock` builds, proven directly by `test_future_market_data_never_leaks_into_the_replay`.
- **No write path to `Prediction`, `RecommendationGeneration`, or `ScanCandidate`** -- consensus (M1.8), scoring (M1.9), and horizon selection (M1.10) are called as pure functions directly (`evaluate_positive_consensus`, `compute_positive_opportunity_score`, `select_horizon`), never through `generate_recommendation_for_candidate`, which persists. This is what makes "changing historical production records" (non-goal) structurally impossible rather than merely avoided by convention.
- **Three distinct outcomes, each explicit, never conflated:**
  1. `LIMITATION_NO_HISTORICAL_DATA` -- zero `MarketPrice` rows at all as of the cutoff; nothing to compute or compare (`replayed_qualifies`/`matches_original` both `None`).
  2. `EXCLUDED_AT_REPLAY:<reason>` -- market data exists but is insufficient/stale/invalid as of the cutoff (the same exclusion reasons M1.12's real scan already produces); `matches_original` compares only "did a recommendation exist" (`generation.prediction_id is None`), since exclusion isn't the same dimension as a consensus rejection.
  3. A full recomputation -- consensus, and (if qualifying) score and horizon -- compared against the original via `matches_original = (replayed_qualifies == (generation.outcome == OUTCOME_QUALIFIED))`, with every replayed version field (`model_version`, `feature_version`, `consensus_contract_version`, and when qualifying `scoring_contract_version`/`horizon_selection_version`) persisted alongside (scope item 5).

### Files Changed

- `app/historical_replay.py` — new: `replay_generation`, limitation constants, `REPLAY_RULE_VERSION`.
- `app/models.py` — new `ReplayRun` model.
- `migrations/versions/0020_replay_runs.py` — new migration.
- `tests/test_historical_replay.py` — new: 6 tests.
- `docs/epics/EPIC-M1.24-historical-recommendation-replay.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_historical_replay.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0020_replay_runs`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0019` through `0020` (verified `replay_runs` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **234 passed, 0 failed** (228 pre-existing from `main` + 6 new).
- `pytest -v tests/test_historical_replay.py`: **6 passed** — a qualifying original decision replays identically (same score, same horizon, `matches_original=True`); a rejected original decision replays identically (`matches_original=True`, same failed criteria); adding a `MarketPrice` row dated 30 days after the original scan date (with drastically different, would-change-everything values) produces byte-identical replayed score/horizon/probability to a control run without it -- direct proof of no leakage; a generation with zero historical market data gets the explicit `NO_HISTORICAL_MARKET_DATA` limitation with both comparison fields `None`; a generation whose historical data is present but stale as of the scan date gets `EXCLUDED_AT_REPLAY:stale_market_data` with `matches_original=False` (a real, explicit discrepancy: originally qualified, but replay can't even evaluate it); and two repeated replays of the same generation produce identical results.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Historical replay is point-in-time safe (cutoff-bounded query, before feature computation).
- [x] Future data cannot enter replay inputs (proven directly by the leakage test).
- [x] Replay is deterministic for identical inputs and versions (proven by the repeated-replay test).
- [x] Original records remain immutable (no write path to `Prediction`/`RecommendationGeneration`/`ScanCandidate` anywhere in this module).
- [x] Missing historical inputs produce explicit replay limitations (`NO_HISTORICAL_MARKET_DATA`, `EXCLUDED_AT_REPLAY:*`).
- [x] Replay differences are attributable to version/input changes (every replayed version field persisted alongside the comparison).
- [x] Tests cover leakage and reproducibility cases.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct, adversarial leakage test. Reusing `app.scan._evaluate_stock` across a module boundary despite its underscore-prefixed name was a deliberate choice to avoid duplicating feature-computation logic, documented above for reviewer scrutiny. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
