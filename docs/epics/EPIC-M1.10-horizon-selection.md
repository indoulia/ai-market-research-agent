# EPIC-M1.10 — Positive Horizon Selection

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** ChatGPT  
**Priority:** P1

## Objective

Select and record the most appropriate positive recommendation horizon within the platform's 1–7 trading-day target, using deterministic evidence rather than a fixed default for every stock.

## Why now

The platform explicitly targets short horizons. A recommendation should state whether its positive opportunity is expected to mature in 1, 3, 5, or 7 trading days rather than treating all opportunities identically.

## Scope

1. Define supported horizons: 1, 3, 5, and 7 trading days.
2. Define deterministic horizon-selection rules based on available model/data evidence.
3. Record the selected horizon and the evidence/rule version used.
4. Handle insufficient data explicitly.
5. Add tests for each supported horizon and boundary conditions.

## Non-goals

- Long-term investment horizons.
- Automatic trading.
- Retrospective horizon changes after recommendation issuance.
- Learning/optimizing horizon rules from outcomes; that is a later EPIC.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Only 1/3/5/7 trading-day horizons can be issued.
- [ ] Horizon selection is deterministic and documented.
- [ ] Selected horizon is stored with the recommendation.
- [ ] Horizon selection cannot be silently changed after issuance.
- [ ] Insufficient evidence produces no invalid horizon.
- [ ] Tests cover all supported horizons and edge cases.

## Dependencies

- M1.8 — Positive Consensus Engine
- M1.4 — Persist Recommendation History

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.10

### Branch

autonomous/epic-m1-10 (stacked on the still-open `autonomous/epic-m1-8` branch/PR #21, since M1.10 depends on M1.8 and it hasn't merged yet — sibling to M1.9's branch, not built on top of it)

### Objective

Deterministically select which supported horizon (1/3/5/7 trading days) fits a candidate, from evidence already available in the repository, and record the selection rule's version alongside it.

### Design Decisions

- **Evidence signal:** `atr_percent` (Average True Range as a percentage of price) — already computed by `app/features/technical.py`, the only volatility measure currently in the repository, and a natural, explainable proxy for "how many trading days a given percentage move is likely to take."
- **Rule (`SELECTION_VERSION = "PHS-001"`):** a fixed, documented step function — higher volatility maps to a shorter horizon (a move is expected to resolve sooner), lower volatility to a longer one: `>= 3.5% -> 1 day`, `>= 2.0% -> 3 days`, `>= 1.0% -> 5 days`, otherwise `7 days`. Every threshold and the fallback are asserted at module load to be one of `VALID_HORIZON_DAYS` and asserted to be strictly descending (the order the first-match-wins scan depends on) — a configuration bug here fails immediately at import time, not silently at runtime.
- **Not learned/optimized from historical outcomes** (per non-goal) — fixed product/policy constants, bumped via `SELECTION_VERSION` if changed.
- **Missing vs. invalid evidence:** `atr_percent=None` (e.g. fewer than 14 trading sessions of history, so the rolling ATR window can't be computed) raises `InsufficientHorizonEvidenceError` explicitly rather than defaulting to a horizon; a negative `atr_percent` (a data-quality impossibility) raises `ValueError`.
- **Persistence + enforcement:** `record_recommendation_with_selected_horizon(session, consensus_evaluation, atr_percent, **kwargs)` selects the horizon first, then routes through M1.8's `record_qualifying_recommendation` (so a non-qualifying candidate still can't be recorded) with `horizon_days` and the new `horizon_selection_version` traced. Added `Prediction.horizon_selection_version` (new, required, added to `IMMUTABLE_FIELDS`) via migration `0009_horizon_selection_version`, chaining off `0008_consensus_contract_version` — the existing `horizon_days` field (M1.4) was already immutable, so "cannot be silently changed after issuance" was already true for the horizon value itself; this EPIC adds traceability for *which rule* chose it.
- Retrofitted the same pre-existing test fixtures (`tests/test_recommendation_history.py`, `tests/test_outcome_evaluation.py`, `tests/test_recommendation_history_db_integrity.py`, `tests/test_positive_consensus.py`) with `horizon_selection_version="PHS-001"`, since the field is now required on every `Prediction` row.

### Known merge-order collision (flagged, not fixed here)

This branch and M1.9's branch (`autonomous/epic-m1-9`, PR #22) are siblings — both stacked on `autonomous/epic-m1-8`, neither depends on the other. Both independently added a new migration numbered `0009` chaining off `0008_consensus_contract_version` (M1.9: `0009_opportunity_score`; this EPIC: `0009_horizon_selection_version`). Whichever PR merges **second** will hit the same migration-history collision already documented and resolved once before (EPIC-M1.4-SUB-01 vs. EPIC-M1.5) — two revisions both claiming `down_revision=0008_consensus_contract_version`. Resolution depends on merge order, which is outside Claude's control (Claude does not merge PRs); the second-merged one will need renumbering to `0010` with an updated `down_revision`, then re-validation. Flagged here rather than resolved, per the same precedent.

### Files Changed

- `app/horizon.py` — new: horizon-selection rule, `select_horizon`, and the gated+selected recording function.
- `app/models.py` — added `Prediction.horizon_selection_version`.
- `app/recommendations.py` — `record_recommendation` now requires `horizon_selection_version`; added to `IMMUTABLE_FIELDS`.
- `migrations/versions/0009_horizon_selection_version.py` — new migration (see collision note above).
- `tests/test_positive_horizon_selection.py` — new: 17 tests.
- `tests/test_recommendation_history.py`, `tests/test_outcome_evaluation.py`, `tests/test_recommendation_history_db_integrity.py`, `tests/test_positive_consensus.py` — updated fixtures for the new required field.
- `docs/epics/EPIC-M1.10-horizon-selection.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -v tests/test_positive_horizon_selection.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- Migration validation against a disposable scratch PostgreSQL database (created and dropped for this validation only): full `upgrade head` through `0009` (verified the column `NOT NULL`), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **73 passed**, 4.20s (56 pre-existing/M1.8 + 17 new in `test_positive_horizon_selection.py`).
- `pytest -v tests/test_positive_horizon_selection.py`: **17 passed** — covers all four supported horizons at both above-threshold and exact-boundary values (inclusive `>=`), the fallback horizon below every threshold, missing evidence raising `InsufficientHorizonEvidenceError`, negative evidence raising `ValueError`, determinism/repeatability, a full qualifying-candidate record with horizon and selection version traced, a missing-evidence case that persists nothing at all, and both `horizon_days` and `horizon_selection_version` independently rejecting post-issuance modification.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration `0009_horizon_selection_version` upgrade: applied cleanly on top of the chain through `0008`; column confirmed `NOT NULL`. Downgrade: confirmed dropped. Re-upgrade: clean.

### Acceptance Criteria

- [x] Only 1/3/5/7 trading-day horizons can be issued (asserted at module load, not just tested).
- [x] Horizon selection is deterministic and documented.
- [x] Selected horizon is stored with the recommendation.
- [x] Horizon selection cannot be silently changed after issuance (both `horizon_days` and the new `horizon_selection_version` are immutable).
- [x] Insufficient evidence produces no invalid horizon (raises before any horizon is chosen).
- [x] Tests cover all supported horizons and edge cases.

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence. The evidence signal (ATR%) and specific thresholds chosen are a design decision within the EPIC's deliberately open scope ("based on available model/data evidence"), documented above for reviewer scrutiny. The migration-numbering collision with M1.9 is a real, disclosed risk flagged for whoever merges second, exactly per the established precedent. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
