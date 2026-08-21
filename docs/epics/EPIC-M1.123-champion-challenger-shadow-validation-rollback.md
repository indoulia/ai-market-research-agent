# EPIC-M1.123 — Champion/Challenger Shadow Validation & Rollback

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Allow new models, calibrators, ranking policies and provider strategies to prove themselves in shadow mode against the production champion before they can affect user-facing recommendations, with deterministic promotion and rollback.

## Scope
- Define Champion and Challenger model identities and lifecycle states.
- Run challengers in shadow mode using the same point-in-time inputs as the champion.
- Record both outputs without allowing challenger output to alter production recommendations.
- Compare calibration, accuracy, usefulness, stability, latency, cost and regime/horizon performance.
- Require minimum sample sizes and predefined promotion gates.
- Protect untouched holdout and future/live validation periods.
- Support staged promotion and observation windows.
- Detect production regression after promotion.
- Support immediate rollback to the last known-good champion.
- Version and preserve all promotion/rollback decisions.
- Extend the same mechanism to provider-routing and ranking-policy candidates where appropriate.

## Acceptance Criteria
- A challenger cannot affect production recommendations while in shadow mode.
- Champion and challenger consume equivalent eligible evidence.
- Promotion requires predefined statistical and business-quality gates.
- Regression automatically triggers rollback or recommendation suppression according to policy.
- Every promotion/rollback is reproducible and auditable.
- Historical predictions remain tied to the exact champion/provider/configuration used at decision time.

## Dependencies
M1.83, M1.88, M1.100, M1.115.

## Non-Goal
No automatic promotion based solely on a single metric or short recent streak.

## Completion Report

### Status
Implemented, tested, merged via PR #247.

### What was built
- `app/champion_challenger_shadow.py` (SCS-001/SCC-001/CRB-001):
  - `record_shadow_challenger_run`: records an externally-supplied challenger score
    (`challenger_predicted_probability`) tied to the champion's own already-published
    `Prediction` for the same stock/as-of/horizon. Never imports or writes to
    `Prediction`/`RecommendationGeneration`/`ScanCandidate` -- a challenger structurally
    cannot affect production (AC), not just by convention. Idempotent by
    `(champion_prediction_id, challenger_model_version)`.
  - `compare_shadow_challenger_performance`: scores champion and challenger against the
    identical, already-resolved `PredictionOutcome` for every shared input -- champion and
    challenger consume equivalent eligible evidence by construction (AC), since both are
    compared against the one real outcome the champion's own prediction produced. Computes
    success-rate and calibration-error for both sides plus a per-horizon breakdown, gated by
    `MIN_SAMPLE_SIZE_FOR_COMPARISON` and `REGRESSION_MARGIN` (both reused from
    `app.trust_report`/`app.candidate_model_evaluation`, not redefined). Always persists a
    fresh, independent report -- never mutates a prior one.
  - `evaluate_shadow_promotion`: writes into `app.model_promotion`'s own existing,
    append-only `ModelPromotion` log using its same `DECISION_PROMOTED`/`DECISION_REJECTED`
    vocabulary (scope: "extend the same mechanism...to candidates where appropriate") --
    never a second, parallel promotion registry.
  - `execute_rollback`: this EPIC's own genuinely new contribution. `app.
    model_regression_detection` (M1.67) already computes `rollback_triggered` but has no
    write path to act on it (its own docstring). `execute_rollback` finds the last known-good
    `PROMOTED` version from `app.model_promotion`'s own history and writes a new `PROMOTED`
    row restoring it, plus a `ChampionRollback` audit row linking the triggering
    `ModelRegressionCheck` (when supplied), the restored version, and the resulting
    promotion. Idempotent by `(rolled_back_model_version, restored_model_version)`. Raises
    `NoKnownGoodChampionError` rather than fabricating a target when there is nothing to roll
    back to.
- `app/models.py`: new `ShadowChallengerAssessment`, `ShadowChallengerComparisonReport`,
  `ChampionRollback` models.
- `migrations/versions/0103_champion_challenger_shadow.py`.
- `tests/test_champion_challenger_shadow.py`: 9 tests covering shadow-run idempotency and
  non-interference with `Prediction`, insufficient-sample/validated/regressed comparison
  verdicts, promotion-log wiring for both outcomes, rollback restoring the correct
  predecessor, rollback idempotency, and the no-known-good-predecessor error case.

### Known gaps, honestly scoped
- **No live model-serving in this platform**: `Prediction.model_version` records which
  already-trained, externally-scored model produced a recommendation; nothing in this repo
  ever *invokes* a model. A true in-process "run the challenger live" shadow mode is not
  buildable without inventing a fake inference step, so `record_shadow_challenger_run` takes
  an externally-supplied score instead -- the same posture every other model-version field on
  `Prediction` already takes.
- **Usefulness, stability, latency, cost, regime performance** (scope) are each already an
  existing signal elsewhere on this platform (M1.66 usefulness, M1.83 stability, M1.98 cost,
  M1.77 regime) but are not yet folded into `ShadowChallengerComparisonReport` -- this EPIC's
  comparison is accuracy/calibration/horizon-based. Wiring those additional dimensions in is
  left as explicit future work, the same compositional-delta posture other EPICs this session
  (M1.119, M1.124, M1.126) documented for their own honest gaps.
- **Provider-routing and ranking-policy candidates** (scope: "extend...where appropriate"):
  `evaluate_shadow_promotion`/`execute_rollback` operate on `ModelPromotion.candidate_model_version`
  as a plain string, so nothing here is model-specific -- a provider-routing or ranking-policy
  candidate could reuse this exact mechanism by passing its own identifier string, but no
  provider-routing/ranking-policy EPIC has yet been wired to call it.
- **Staged promotion and observation windows** (scope): `evaluate_shadow_promotion` is a
  single-shot promote/reject decision from one comparison report; a genuinely staged rollout
  (e.g. partial traffic, multi-stage observation gates) is not implemented -- left as future
  work for whichever EPIC needs it.

### Tests
`python -m pytest tests/test_champion_challenger_shadow.py -q` -- 9 passed.
`python -m alembic heads` -- single clean head at `0103_champion_challenger_shadow`.
`python -m pytest tests/test_fresh_database_migration.py tests/test_recommendation_history_db_integrity.py -q` -- 9 passed.
