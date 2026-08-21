# EPIC-M3.9 — Learning & Self-Improvement

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P1

## Objective
Expose MRA's controlled learning process so users can understand what the system learned, what experiments ran and why production behavior changed, without exposing unsafe internal controls.

## UI Scope
- Learning summary.
- Recent learning signals.
- Failure patterns discovered.
- Candidate experiments.
- Champion/challenger status.
- Promotions/rejections.
- Trust impact over time.
- Evidence links and concise explanations.
- Read-only by default.

## API Contract
`GET /api/v1/learning/summary`
`GET /api/v1/learning/history`
`GET /api/v1/learning/experiments`
`GET /api/v1/learning/models`
`GET /api/v1/learning/models/{modelId}`

Responses include:
`id`, `type`, `createdAt`, `status`, `evidenceCount`, `methodologyVersion`, `impact`, `modelVersion`, `decisionReason`.

## Acceptance Criteria
- UI never directly modifies production models.
- Every displayed learning claim links to evidence.
- Promotion/rejection states reconcile with M1.123.
- Historical learning decisions remain immutable.
- User can understand improvement without seeing implementation internals.

## Completion Report (2026-08-22)

**Context:** see `docs/epics/EPIC-M3-ROADMAP-NOTE.md` -- this EPIC's number
was renumbered from `M1.140` in the newer combined roadmap. The older
split-track backend chain (`M1.28`-`M1.123`) already implements extensive
learning-loop, experiment, champion/challenger and self-correction logic;
this session's job was to expose it read-only, not reimplement it.

**Already satisfied by existing, merged work -- verified, not
reimplemented** (see `api/services/learning.py`'s module docstring for the
full reasoning on which of two competing generations was chosen where
two existed):
- `app.model_promotion.ModelPromotion` (EPIC-M1.31) -- the append-only
  promotion/rejection log this EPIC's AC anchors on ("reconcile with
  M1.123"), since `app.champion_challenger_shadow` (EPIC-M1.123) also
  writes into this same table for shadow promotions and rollbacks.
- `app.continuous_learning.LearningCycle` (EPIC-M1.32) -- the
  watermark-gated audit trail of when a learning cycle ran or was
  skipped, and which promotion decision (if any) it produced.
- `app.champion_challenger_shadow.ShadowChallengerComparisonReport`/
  `ChampionRollback` (EPIC-M1.123) -- champion/challenger comparison
  evidence and rollback history, including `NoKnownGoodChampionError`'s
  honest "nothing to roll back to" case.
- `app.recommendation_experiments.Experiment`/`ExperimentArm`/
  `ExperimentResult` (EPIC-M1.68) -- the candidate-experiment framework,
  and `app.feedback_experiment_pipeline.FeedbackDrivenExperiment`
  (EPIC-M1.69), which links a recurring feedback pattern to the
  experiment it spawned.
- `app.feedback_learning_signals.compute_feedback_learning_signals`
  (EPIC-M1.53) -- "recent learning signals"/"failure patterns discovered":
  a `VERDICT_WEAK` (category, reason_code) pattern is a discovered
  failure pattern, validated against objective outcomes, never feedback
  text alone.
- Every one of the above already has its own extensive test suite
  (`tests/test_champion_challenger_shadow.py`,
  `tests/test_recommendation_experiments.py`,
  `tests/test_feedback_experiment_pipeline.py`,
  `tests/test_feedback_learning_signals.py`,
  `tests/test_continuous_learning.py`, etc.) -- none of that logic was
  touched this session.
- A parallel, later generation of the same concepts
  (`app.safe_model_promotion.ModelPromotionDecision`,
  `app.continuous_self_learning_loop.SelfLearningCycle`, wired to the
  M1.39/M1.43/M1.44/M1.45 dataset-version chain) exists but is
  deliberately **not** surfaced by this EPIC's endpoints -- mixing both
  registries into one "current production model"/"promotion count"
  answer would produce two disagreeing notions of "current champion".
  The AC's explicit "reconcile with M1.123" anchors this EPIC on the
  `ModelPromotion`/`LearningCycle` generation only.

**Genuine gaps implemented this session** (all read-only; no route can
trigger a learning cycle, promotion, rollback or experiment run):
- `api/schemas/learning.py` -- `LearningSummary`, `LearningHistoryEntry`
  (the unified, cross-table timeline: `id`/`type`/`createdAt`/`status`/
  `evidenceCount`/`methodologyVersion`/`impact`/`modelVersion`/
  `decisionReason`, matching the EPIC's own response-field list),
  `LearningExperiment`.
- `api/services/learning.py` -- `get_learning_summary`, `get_learning_history`
  (merges `LearningCycle`/`ModelPromotion`/`ChampionRollback` rows, sorted
  newest-first, composite `"<table>:<id>"` ids since these are
  independently-keyed tables), `list_learning_experiments` (reports only
  already-persisted `ExperimentResult` rows -- an experiment with arms but
  no result yet is honestly `PENDING`, never fabricated as `READY`).
- `api/routers/learning.py` -- `GET /api/v1/learning/summary`,
  `GET /api/v1/learning/history` (`limit` query param, capped),
  `GET /api/v1/learning/experiments`, wired into `api/app.py`.
- `docs/api/openapi.json` regenerated (`python scripts/export_openapi.py`).
- Flutter: `flutter_app/lib/features/learning/{learning_summary,
  learning_history_entry, learning_experiment, learning_repository,
  learning_screen}.dart` -- a read-only "Learning & Self-Improvement"
  screen (KPI strip, champion/challenger card, failure-pattern list,
  candidate-experiment cards with per-arm results via
  `MraExpandableSection`, and a `TimelineEventRow`-based history feed).
  Reached via a new nested route (`/tracking/learning`) and a "View
  learning insights" entry point added to the existing Tracking screen
  (EPIC-M1.148/M3.7), since Learning isn't one of the app's primary
  bottom-nav destinations -- the same "nested route off an existing
  destination" pattern `recommendation/:id` already uses.

**Deliberately deferred, with rationale:**
- `GET /api/v1/learning/models`/`GET /api/v1/learning/models/{modelId}`
  (present in this doc's own API Contract list, but not among the three
  endpoints this EPIC's execution instructions called out as required):
  `app.models.ModelVersion` is defined in the schema but has zero writers
  anywhere in this codebase -- no EPIC populates it. Building a "model
  registry" endpoint against an always-empty table would either return
  nothing useful or require inventing a new write path, which risks
  fabricating a registry that doesn't genuinely exist yet. Deferred to
  whichever future EPIC actually wires `ModelVersion` writes.
- The parallel `SelfLearningCycle`/`ModelPromotionDecision` generation is
  not surfaced (see above) -- a future EPIC reconciling the two
  promotion-registry generations into one could revisit this.

**Tests (TDD):**
```
python -m pytest tests/test_api_learning.py -q
# 8 passed

python -m pytest -q
# 1430 passed, 9 skipped -- full existing suite, no regressions

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# Formatted 128 files (0 changed)

cd flutter_app && flutter test
# All tests passed! (166 tests, incl. 8 new learning feature tests)
```

**Conclusion:** the underlying learning-loop, champion/challenger and
experiment machinery already existed and was already extensively tested;
this session's real work was three new read-only API endpoints plus
services composing already-tested tables/functions, and one new
read-only Flutter screen exposing them, satisfying every Acceptance
Criterion above. Marking this EPIC `DONE`.
