# EPIC-M1.58 — Position Risk Assessment

Status: DONE
Execution Status: COMPLETED

## Objective
Quantify recommendation-level downside, reward/risk, and volatility-adjusted risk so users can understand risk before acting.

## Scope
- Calculate risk from reference price to stop loss.
- Calculate reward from reference price to target.
- Calculate reward/risk ratio.
- Validate target, stop loss, upside, and horizon consistency.
- Preserve calculation/version metadata.
- Do not provide portfolio allocation advice in this EPIC.

## Acceptance Criteria
- Risk calculations are deterministic and auditable.
- Invalid target/SL combinations are rejected.
- Published recommendations expose risk metrics.
- Historical recommendations retain their original risk snapshot.
- Tests cover boundaries and invalid inputs.

## Dependencies
Previous: M1.47.
Next: M1.59.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.58

### Branch

autonomous/epic-m1-58, branched cleanly from `main` (the declared dependency -- M1.47 -- is already merged).

### Objective

Quantify recommendation-level downside, reward/risk, and volatility-adjusted risk so users can understand risk before acting -- without providing portfolio allocation advice.

### Design

`assess_position_risk` builds entirely on top of M1.47's already-published, already-validated `RecommendationPublication` -- it never recomputes or duplicates M1.47's own target/SL/entry-price validation. `risk_percentage`/`reward_percentage`/`reward_risk_ratio` are copied directly from that publication (AC: "published recommendations expose risk metrics").

### Volatility-Adjusted Risk

This module's genuinely new contribution: `risk_in_atr_units = downside_percentage / atr_percent` and `reward_in_atr_units = upside_percentage / atr_percent`, using the underlying `ScanCandidate.atr_percent` (M1.12) as the volatility normalizer -- the objective's "volatility-adjusted risk," expressing risk/reward in units of the stock's own recent volatility rather than a raw, stock-agnostic percentage.

### Horizon Consistency Validation

A fixed, documented, versioned rule flags two failure modes (scope: "validate target, stop loss, upside, and horizon consistency"): a stop tighter than `MIN_ATR_MULTIPLE_STOP` (0.5×ATR) is noise risk, not a real signal-driven stop (`STOP_TOO_TIGHT_FOR_VOLATILITY`); a stop wider than `MAX_ATR_MULTIPLE_PER_HORIZON_DAY` (2.0) × the recommendation's own horizon in days is inconsistent with resolving within that horizon (`STOP_TOO_WIDE_FOR_HORIZON`). Both are proven directly by test with concrete boundary-crossing values.

### Rejecting Invalid Combinations

`assess_position_risk` raises `UnpublishedRecommendationError` if the underlying `RecommendationPublication.published` is `False` -- there is no valid target/SL shape to assess risk from (AC: "invalid target/SL combinations are rejected"), proven directly by test using a `target_return=0` publication that M1.47 itself already rejected.

### Determinism, Auditability, and Immutability

`assess_position_risk` is a pure function of `publication`'s own fields plus the underlying `ScanCandidate.atr_percent` (AC: "risk calculations are deterministic and auditable"). One immutable row per `(prediction_id, assessment_rule_version)`, guarded by `before_update` (`PositionRiskAssessmentImmutableError`) -- historical recommendations retain their original risk snapshot even if re-assessed later (AC), proven directly by test that neither the original `Prediction` nor `RecommendationPublication` is ever mutated.

### No Portfolio Advice

This module has no concept of position sizing, capital, or multiple holdings -- it only assesses one recommendation's own risk shape (scope non-goal: "do not provide portfolio allocation advice in this EPIC").

### Files Changed

- `app/position_risk_assessment.py` — new: `assess_position_risk`, `get_position_risk_assessment`, policy constants, `UnpublishedRecommendationError`, `PositionRiskAssessmentImmutableError`.
- `app/models.py` — new `PositionRiskAssessment` model.
- `migrations/versions/0040_position_risk_assessment.py` — new migration.
- `tests/test_position_risk_assessment.py` — new: 8 tests.
- `docs/epics/EPIC-M1.58-position-risk-assessment.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_position_risk_assessment.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0040_position_risk_assessment`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0039` through `0040` (verified `position_risk_assessments` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **511 passed, 0 failed** (503 pre-existing from `main` + 8 new).
- `pytest -q tests/test_position_risk_assessment.py -v`: **8 passed** — a normal case is horizon-consistent; risk and reward are correctly expressed in ATR units; a stop too tight for the stock's own volatility is flagged; a stop too wide for the recommendation's horizon is flagged; an unpublished (M1.47-rejected) recommendation cannot be risk-assessed; assessment is deterministic/idempotent on rerun; an assessment row is immutable after creation; neither the original `Prediction` nor `RecommendationPublication` is ever mutated.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Risk calculations are deterministic and auditable (pure function of `publication`'s own fields; no randomness).
- [x] Invalid target/SL combinations are rejected (`UnpublishedRecommendationError` for an M1.47-rejected publication).
- [x] Published recommendations expose risk metrics (`risk_percentage`/`reward_percentage`/`reward_risk_ratio` copied from M1.47).
- [x] Historical recommendations retain their original risk snapshot (idempotent by `(prediction_id, assessment_rule_version)`; immutability guard; proven by test).
- [x] Tests cover boundaries and invalid inputs (both horizon-inconsistency boundaries and the unpublished-recommendation case covered explicitly).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof of both horizon-inconsistency boundary conditions. This EPIC is purely additive on top of M1.47's existing, immutable `RecommendationPublication` -- it never recomputes target/SL validation, only adds volatility normalization and a horizon-consistency check on top of it, and explicitly has no position-sizing or portfolio concept. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
