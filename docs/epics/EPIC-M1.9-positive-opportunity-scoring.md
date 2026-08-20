# EPIC-M1.9 — Positive Opportunity Scoring

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** ChatGPT  
**Priority:** P1

## Objective

Create a transparent score that ranks stocks that already pass the positive-consensus gate, so the platform can prioritize the strongest positive opportunities without turning ranking into a recommendation by itself.

## Why now

Once positive consensus is explicit, the system needs to distinguish strong qualifying opportunities from marginal qualifying opportunities. The score must remain explainable and reproducible.

## Scope

1. Define a deterministic scoring contract using approved positive signals.
2. Normalize component contributions so no single metric dominates accidentally.
3. Produce a total score plus component-level contributions.
4. Support ranking qualifying candidates by score.
5. Persist the scoring-contract version used for a recommendation candidate.
6. Add tests for ordering, boundary values, missing data, and deterministic repeatability.

## Non-goals

- Changing the positive-consensus gate.
- Training a new ML model.
- Automatically optimizing weights from outcomes.
- LLM-based scoring.
- Negative recommendations.
- Portfolio/trading functionality.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Scoring rules are explicitly documented and versioned.
- [ ] Every score component is explainable.
- [ ] Identical inputs always produce identical scores.
- [ ] Missing/invalid inputs are handled explicitly rather than silently defaulted.
- [ ] Qualifying candidates can be deterministically ranked.
- [ ] Score and scoring-contract version are traceable.
- [ ] Tests cover normal, boundary, missing-data, and tie cases.

## Dependencies

- M1.8 — Positive Consensus Engine
- M1.4 — Persist Recommendation History

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.9

### Branch

autonomous/epic-m1-9 (stacked on the still-open `autonomous/epic-m1-8` branch/PR #21, since M1.9 depends on M1.8 and neither has merged yet)

### Objective

A transparent, versioned, deterministic score (`app/scoring.py`) that ranks candidates which already pass the M1.8 positive-consensus gate.

### Design Decisions

- **Contract:** `CONTRACT_VERSION = "POS-001"`. Bumped whenever a weight or ceiling changes.
- **Reuses the exact signals M1.8's consensus gate already qualifies on** (`predicted_probability`, `confidence`, `sma20_distance`, `volume_ratio_20d`) — per scope item 1 ("using approved positive signals"), rather than introducing new ones.
- **Four normalized components, weights summing to 1.00** (so no single metric can dominate by accident, per scope item 2): `probability` (0.40), `confidence` (0.20), `trend` (0.25), `liquidity` (0.15). Each is linearly normalized over a documented `[floor, ceiling]` range and clamped to `[0, 1]` before being multiplied by its weight — `probability`/`confidence`/`liquidity` reuse the consensus gate's own floors (`MIN_PREDICTED_PROBABILITY`, `MIN_CONFIDENCE`, `MIN_VOLUME_RATIO_20D`) so scoring stays consistent with what "qualifying" means; `trend` has no meaningful floor (the gate already requires `sma20_distance > 0`) so it's normalized over `[0, 0.10]` and a non-positive value simply saturates to a 0 contribution rather than erroring.
- **Total score** is the weighted sum, scaled to `[0, 100]` for readability, rounded to 2 decimal places (`Numeric(6, 2)`).
- **Missing vs. invalid data are handled differently, both explicitly (never silently defaulted):** a missing (`None`) field raises `InsufficientScoringDataError` naming the field; an out-of-domain value (probability/confidence outside `[0, 1]`, a negative volume ratio) raises `ValueError`. A negative or zero `sma20_distance` is neither missing nor invalid — it's a legitimate weak/negative-trend reading that saturates to a 0 contribution.
- **Ranking:** `rank_positive_opportunities` sorts descending by `total_score`, breaking exact ties on the candidate key ascending — fully deterministic, including on ties (explicit "tie cases" AC).
- **Enforcement + persistence:** `record_ranked_recommendation(session, consensus_evaluation, score_result, **kwargs)` first checks `consensus_evaluation.qualifies` (reusing M1.8's exact `ConsensusNotQualifiedError`) before ever computing/persisting a score — scoring a non-qualifying candidate is meaningless. Added `Prediction.scoring_contract_version` and `Prediction.opportunity_score` (both new, required, added to `IMMUTABLE_FIELDS`) via migration `0009_opportunity_score`, chaining off M1.8's `0008_consensus_contract_version`. This mirrors M1.8's own pattern of extending `record_recommendation`'s required fields rather than duplicating a parallel persistence path — `app/consensus.py`'s `record_qualifying_recommendation` did not need any code change, since it already forwards `**recommendation_kwargs` straight through to `record_recommendation`.
- Retrofitted the same pre-existing test fixtures updated in M1.8 (`tests/test_recommendation_history.py`, `tests/test_outcome_evaluation.py`, `tests/test_recommendation_history_db_integrity.py`, `tests/test_positive_consensus.py`) with `scoring_contract_version="POS-001"` / `opportunity_score=Decimal("70.00")`, since both fields are now required on every `Prediction` row.

### Files Changed

- `app/scoring.py` — new: scoring contract, component computation, ranking, and the gated+scored recording function.
- `app/models.py` — added `Prediction.scoring_contract_version`, `Prediction.opportunity_score`.
- `app/recommendations.py` — `record_recommendation` now requires both new fields; added to `IMMUTABLE_FIELDS`.
- `migrations/versions/0009_opportunity_score.py` — new migration.
- `tests/test_positive_opportunity_scoring.py` — new: 21 tests.
- `tests/test_recommendation_history.py`, `tests/test_outcome_evaluation.py`, `tests/test_recommendation_history_db_integrity.py`, `tests/test_positive_consensus.py` — updated fixtures for the two new required fields.
- `docs/epics/EPIC-M1.9-positive-opportunity-scoring.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -v tests/test_positive_opportunity_scoring.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- Migration validation against a disposable scratch PostgreSQL database (created and dropped for this validation only): full `upgrade head` through `0009` (verified both new columns `NOT NULL`), `downgrade -1` (verified both dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **77 passed**, 4.27s (56 pre-existing/M1.8 + 21 new in `test_positive_opportunity_scoring.py`).
- `pytest -v tests/test_positive_opportunity_scoring.py`: **21 passed** — covers a maximal-input case (score exactly 100.00), a floor-input case, a strict strong > moderate > weak ordering, each of the three linear-normalization boundaries at exactly floor/ceiling, the trend component's 0/ceiling/beyond-ceiling saturation behavior including a negative value saturating rather than erroring, every field missing raising `InsufficientScoringDataError` by name, four invalid-value cases raising `ValueError`, determinism/repeatability, ranking order (descending), an exact-tie case breaking deterministically on candidate key, and end-to-end recording of a qualifying+scored candidate with both `opportunity_score` and `scoring_contract_version` traced on the persisted row, plus rejection of a non-qualifying candidate before any scoring/persistence.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration `0009` upgrade: applied cleanly on top of the full chain through `0008`; both columns confirmed `NOT NULL`. Downgrade: both confirmed dropped. Re-upgrade: clean.

### Acceptance Criteria

- [x] Scoring rules are explicitly documented and versioned.
- [x] Every score component is explainable (`ComponentScore.detail` on every component).
- [x] Identical inputs always produce identical scores.
- [x] Missing/invalid inputs are handled explicitly rather than silently defaulted.
- [x] Qualifying candidates can be deterministically ranked.
- [x] Score and scoring-contract version are traceable.
- [x] Tests cover normal, boundary, missing-data, and tie cases.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence. The specific weights/ceilings chosen are a design decision within the EPIC's deliberately open scope, documented above for reviewer scrutiny. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
