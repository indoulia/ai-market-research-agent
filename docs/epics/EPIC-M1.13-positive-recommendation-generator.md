# EPIC-M1.13 — Positive Recommendation Generator

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
**Priority:** P1

## Objective

Convert evaluated candidates into positive recommendations only when every required positive gate is satisfied.

## Scope

1. Consume candidate predictions, positive-consensus results, score, and selected horizon.
2. Generate a recommendation only when the positive-consensus contract qualifies the candidate.
3. Persist the recommendation with probability, score, horizon, criteria version, model version, and issuance timestamp.
4. Record explicit non-qualification without creating a negative recommendation.
5. Ensure recommendation creation is idempotent for the same candidate/scan context.
6. Add deterministic tests for qualify, reject, duplicate, and incomplete-input cases.

## Non-goals

- SELL/bearish recommendations.
- Portfolio or trading automation.
- Changing the consensus rules.
- LLM override of quantitative qualification.
- UI/dashboard work.

## Acceptance Criteria

- [ ] No recommendation is created unless positive consensus passes.
- [ ] Every recommendation contains the required traceability fields.
- [ ] Failed candidates are not converted into negative recommendations.
- [ ] Duplicate generation for the same scan context is prevented.
- [ ] Missing required evidence produces no recommendation.
- [ ] Tests prove both positive and rejection paths.

## Dependency Chain

### Previous / Required
- **M1.8 — Positive Consensus Engine** — defines the positive qualification gate.
- **M1.9 — Positive Opportunity Scoring** — provides the opportunity score used by the recommendation path.
- **M1.10 — Positive Horizon Selection** — provides the selected 1/3/5/7-day horizon.
- **M1.12 — Market Universe & Daily Candidate Scan** — provides the candidate scan context.

### Next / Unlocks
- **M1.14 — Recommendation Selection & Daily Limit** — selects the strongest qualifying recommendations.
- **M1.15 — Recommendation Lifecycle & Outcome Scheduler** — tracks issued recommendations through their selected horizon.
- **M1.17 — ChatGPT Candidate Discovery** — routes externally discovered candidates through this same recommendation path.

### Chain Position

`M1.8 + M1.9 + M1.10 + M1.12 → M1.13 → M1.14 → M1.15 → M1.16`

M1.17 branches from M1.8 and M1.13 after the core quantitative recommendation path is established.

### Execution Rule

Do not execute M1.14, M1.15, or M1.17 until M1.13 is implemented, reviewed, and merged. Do not bypass missing upstream EPICs.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.13

### Branch

autonomous/epic-m1-13, stacked on the still-open `autonomous/epic-m1-12` branch/PR #27 (M1.12's candidate-scan output is this EPIC's direct input and isn't in `main` yet).

### Undeclared dependency on M1.9 (flagged, and resolved by porting)

This EPIC's own dependency list correctly names M1.9 (Positive Opportunity Scoring), but M1.9's code was **not** available anywhere reachable from this branch: M1.9's PR (#22) merged into the `autonomous/epic-m1-8` branch, never into `main`, and `main` does not contain `app/scoring.py`. Rather than block on an unmerged sibling branch or silently reimplement scoring with different semantics, I ported M1.9's implementation verbatim from `origin/autonomous/epic-m1-9` (commit `c931805`) onto this branch: `app/scoring.py`, `tests/test_positive_opportunity_scoring.py`, the `scoring_contract_version`/`opportunity_score` additions to `Prediction`/`record_recommendation` (`app/models.py`, `app/recommendations.py`), and a migration for those two columns — renumbered `0012_opportunity_score` (chained after this EPIC's own scan-migration `0011`) since the original `0009_opportunity_score` number was never reserved in `main`. Ported code is otherwise unmodified except for the renumbering and one wiring fix below.

### Wiring fix required by porting M1.9 alongside the already-merged M1.10

M1.9 and M1.10 were developed as siblings, each stacked independently on M1.8, so M1.9's own `record_ranked_recommendation` predates M1.10's `horizon_selection_version` requirement and never accounts for it. Since `main` already has M1.10 merged, `record_recommendation` now unconditionally requires `horizon_selection_version` — so M1.9's ported test needed `horizon_selection_version="PHS-001"` added to its recommendation kwargs (one line), matching the exact precedent already established in `tests/test_positive_consensus.py` for the same situation. `app/scoring.py` itself needed no change. Four other currently-passing test files (`tests/test_recommendation_history.py`, `tests/test_positive_horizon_selection.py`, `tests/test_positive_consensus.py`, `tests/test_outcome_evaluation.py`) needed the equivalent one-line addition of `scoring_contract_version`/`opportunity_score` to their own recommendation kwargs, now that those two fields are required by every recommendation.

### Objective

Turn an M1.12 `ScanCandidate` into a positive recommendation when the M1.8 consensus gate, M1.9 score, and M1.10 horizon are all satisfied together — or an explicit, traceable non-qualification record when they are not, never a negative recommendation.

### Design Decisions

- **New model `RecommendationGeneration`** (new table, migration `0013_recommendation_generations`, chains off the ported `0012_opportunity_score`): one row per `scan_candidate_id` (unique), recording `outcome` (`QUALIFIED`/`NOT_QUALIFIED`), the `consensus_contract_version` used, `failed_criteria` (JSON list of criterion names, set only when not qualified), and `prediction_id` (unique, set only when qualified).
- **`generate_recommendation_for_candidate(session, scan_candidate, *, as_of_timestamp, entry_price, target_return, stop_return)`** (`app/recommendation_generator.py`) is the single entry point:
  1. Idempotency check first (scope item 5): an existing `RecommendationGeneration` for this `scan_candidate_id` is returned unchanged rather than re-evaluating or re-generating.
  2. A scan candidate the scan itself already excluded (`eligible=False`) raises `CandidateNotEligibleError` rather than being silently skipped or defaulted into either outcome — there is no signal to qualify or score for one (scope item covering incomplete input).
  3. Runs M1.8's `evaluate_positive_consensus` on the candidate's persisted signals (scope items 1–2). Not qualifying persists a `NOT_QUALIFIED` row with the failed criteria named and creates no `Prediction` row at all (scope item 4 — never a negative recommendation).
  4. Qualifying runs M1.9's `compute_positive_opportunity_score` and M1.10's `record_recommendation_with_selected_horizon` (which itself selects the horizon from `atr_percent` and persists via M1.8's consensus-gated `record_recommendation`), then persists a `QUALIFIED` `RecommendationGeneration` row linking the resulting `Prediction` (scope item 3 — probability, score, horizon, all three contract versions, and issuance timestamp are all on that `Prediction` row already, by construction of the functions being composed).
- **Immutability:** a `before_update` ORM guard (`RecommendationGenerationImmutableError`) rejecting any modification to any field on an existing `RecommendationGeneration` row, matching the same pattern already established for `Prediction`/`WatchlistEvaluation`.

### Files Changed

- `app/recommendation_generator.py` — new: `generate_recommendation_for_candidate`, `CandidateNotEligibleError`, immutability guard.
- `app/scoring.py` — new (ported verbatim from M1.9, see dependency note above).
- `app/models.py` — new `RecommendationGeneration` model; ported `scoring_contract_version`/`opportunity_score` on `Prediction` (M1.9).
- `app/recommendations.py` — ported `scoring_contract_version`/`opportunity_score` wiring into `record_recommendation`/`IMMUTABLE_FIELDS` (M1.9).
- `migrations/versions/0012_opportunity_score.py` — ported M1.9 migration, renumbered.
- `migrations/versions/0013_recommendation_generations.py` — new M1.13 migration.
- `tests/test_recommendation_generation.py` — new: 5 tests.
- `tests/test_positive_opportunity_scoring.py` — new (ported M1.9 tests, one-line horizon fix, see above).
- `tests/test_recommendation_history.py`, `tests/test_positive_horizon_selection.py`, `tests/test_positive_consensus.py`, `tests/test_outcome_evaluation.py` — one-line each: added `scoring_contract_version`/`opportunity_score` to existing recommendation kwargs so they keep passing now those fields are required.
- `docs/epics/EPIC-M1.13-positive-recommendation-generator.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_recommendation_generation.py tests/test_positive_opportunity_scoring.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0013_recommendation_generations`)
- Migration validation against a disposable scratch PostgreSQL database `market_agent_scratch_m113` (created and dropped for this validation only): full `upgrade head` from `<base>` through `0013` (verified `recommendation_generations` and all its columns, and the `predictions` table's new `scoring_contract_version`/`opportunity_score` columns), `downgrade -1` (verified `recommendation_generations` dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **115 passed, 19 failed** (110 pre-existing/M1.12 pass + 5 new pass; the 19 failures are pre-existing on `main` and confirmed unrelated to this branch — same root cause disclosed in EPIC-M1.12's completion report, `record_recommendation` signature drift in test files never updated across earlier EPICs. Not fixed here; still out of scope.)
- `pytest -v tests/test_recommendation_generation.py`: **5 passed** — a qualifying candidate produces both a `QUALIFIED` generation record and a real, queryable `Prediction` with a positive `opportunity_score` and the horizon selected from its `atr_percent`; a candidate failing one consensus criterion (`predicted_probability` below threshold) produces a `NOT_QUALIFIED` record naming exactly that failed criterion and creates zero `Prediction` rows; regenerating for the same scan candidate returns the identical generation row rather than creating a second one; a scan candidate the scan itself already excluded raises `CandidateNotEligibleError` naming its exclusion reason rather than generating anything; and a persisted generation record rejects a direct attempt to modify its `outcome` field.
- `pytest -v tests/test_positive_opportunity_scoring.py`: **21 passed** — the ported M1.9 suite, unchanged in substance.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] No recommendation is created unless positive consensus passes.
- [x] Every recommendation contains the required traceability fields (consensus/scoring/horizon contract versions, probability, score, horizon, issuance timestamp — all already enforced as required, non-nullable `Prediction` columns).
- [x] Failed candidates are not converted into negative recommendations.
- [x] Duplicate generation for the same scan context is prevented (idempotent per `scan_candidate_id`).
- [x] Missing required evidence produces no recommendation (an ineligible candidate raises rather than fabricating an outcome; a candidate missing an individual signal fails that specific consensus criterion explicitly).
- [x] Tests prove both positive and rejection paths (plus duplicate and ineligible-input paths).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip through the full chain M1.8→M1.9→M1.10→M1.12→M1.13. The undeclared M1.9 dependency gap is disclosed above and resolved by porting the existing, already-reviewed-in-spirit M1.9 implementation rather than by silently reinventing it or bypassing the dependency. This is NOT final approval — that remains the reviewer's call, and per the standing contract, Claude will not merge this PR.

### Reconciliation onto `main` (2026-08-20)

GitHub reported this PR as targeting `main` yet not mergeable, because its actual base branch was `autonomous/epic-m1-12` (M1.12's own feature branch), which was never merged into `main` — `main` instead got M1.12 through a separate PR (#27) whose commit is a byte-for-byte identical tree to `epic-m1-12`'s own M1.12 commit. There was no M1.9/M1.10 divergence to reconcile: `main`'s M1.6/M1.10/M1.11 history is the same commit chain this branch was built on, and M1.9 was already handled by porting it directly into this EPIC's own commit (see above) rather than depending on an external branch.

Reconciliation performed: `git rebase --onto origin/main <merge-base> HEAD`, merge-base `02d8624`. Git dropped the duplicate M1.12 commit automatically ("patch contents already upstream") and replayed only this branch's own commits (M1.13 feature commit, the CI fix, and the CI-retrigger chore) directly onto current `main`. No source file conflicts; no product behavior changed. PR base retargeted from `autonomous/epic-m1-12` to `main` to match.

Verification after reconciliation (all commands run against the rebased tree, from a fresh `.venv` with `requirements.txt` installed):
- `pytest -q`: **134 passed, 0 failed** (the branch's own earlier CI fix — "same root cause as PR #30 on main" — already resolved the pre-existing failures noted in the prior run above; confirmed clean post-rebase).
- `pytest -v tests/test_positive_opportunity_scoring.py tests/test_recommendation_generation.py tests/test_fresh_database_migration.py`: **29 passed**.
- `compileall -q app scripts tests migrations`: exit 0, no output.
- `git diff --check origin/main HEAD`: exit 0, no output.
- `alembic heads`: single head, `0013_recommendation_generations`.
- PostgreSQL round-trip against local `market_agent` database: `downgrade base` → `upgrade head` → `downgrade base` → `upgrade head`, all clean, exactly one head throughout.

### Second reconciliation: PR #30 merged to `main` mid-session (2026-08-20)

While this reconciliation was in progress, PR #30 (the CI fix from `main`, referenced above) was merged to `main` as `0a4edb5`. Re-ran the rebase (`git rebase --onto origin/main 3bf98da HEAD`) to pick up the new `main` tip. This branch's own equivalent CI-fix commit now partially overlapped `0a4edb5`: both added `consensus_contract_version`/`horizon_selection_version` to the same four test files, but this branch's version additionally added `scoring_contract_version`/`opportunity_score` (required once M1.13's own migration `0012` landed, which `main`'s standalone PR #30 fix predates). Resolved as a union — kept both additions, in the three files where they touch adjoining lines (`test_model_timestamp_portability.py`, `test_positive_recommendation_performance.py`, `test_recommendation_calibration.py`); `test_fresh_database_migration.py`'s fix was already fully covered by `0a4edb5` and needed no further change on this branch.

Re-verified after this second reconciliation: `pytest -q` **134 passed, 0 failed**; `compileall`/`git diff --check` both exit 0; `alembic heads` single head `0013_recommendation_generations`; full PostgreSQL `upgrade head` → `downgrade base` → `upgrade head` round-trip against a freshly reset schema, clean throughout.

### Third reconciliation: PR #26 (M1.7) merged to `main` mid-session (2026-08-20)

PR #26 also merged to `main` (as `89c381a`) while this reconciliation was in progress. Re-ran the rebase (`git rebase --onto origin/main 0a4edb5 HEAD`) — no conflicts; M1.7 and M1.13 touch disjoint parts of `app/models.py` (M1.7 appends `WatchlistEvaluation` after `ModelVersion`; M1.13 adds fields to `Prediction` and a new `RecommendationGeneration` class after `ScanCandidate`). The only fallout: `main` now carries M1.7's `tests/test_watchlist_evaluation.py`, whose `_recommendation_kwargs()` helper predates this EPIC's `scoring_contract_version`/`opportunity_score` requirement — same root cause as the four other test files already fixed above, now a fifth. Added the same one-line kwargs.

Re-verified after this third reconciliation: `pytest -q` **140 passed, 0 failed**; `compileall`/`git diff --check` both exit 0; `alembic heads` single head `0013_recommendation_generations`; full PostgreSQL `upgrade head` → `downgrade base` → `upgrade head` round-trip against a freshly reset schema, clean throughout.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
