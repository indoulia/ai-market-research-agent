# EPIC-M1.45 — Continuous Self-Learning Loop

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Connect discovery, recommendation outcomes, learning, evaluation, and safe model promotion into a controlled continuous improvement loop.

## Scope
- Schedule learning-data refresh.
- Detect when sufficient new outcomes are available.
- Rebuild/version the learning dataset.
- Evaluate candidate scoring/model changes.
- Invoke the M1.44 promotion gate.
- Promote only approved candidates.
- Keep the current model when evidence is insufficient.
- Trigger renewed discovery using the active model.
- Preserve a complete lineage from recommendation to model version.

## Acceptance Criteria
- [ ] The loop runs without manual intervention once enabled.
- [ ] No model changes occur without the promotion gate.
- [ ] Insufficient evidence causes no change.
- [ ] Every learning cycle has a unique version and audit record.
- [ ] Active model changes are traceable to comparison evidence.
- [ ] Historical recommendations remain immutable.
- [ ] Failed learning cycles do not stop ordinary recommendation tracking.
- [ ] The system can resume safely after interruption.

## Non-goals
- Autonomous trading.
- Guaranteed improvement.
- Deleting poor historical recommendations.
- Using future information for past predictions.

## Dependencies
**Previous:** M1.44, M1.45 prerequisites M1.33–M1.44
**Next:** Future M2 learning capabilities

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.45

### Branch

autonomous/epic-m1-45, branched cleanly from `main` (the declared dependency -- M1.44 -- and its own prerequisite chain M1.33-M1.44 are all already merged).

### The Complete Loop

`run_self_learning_cycle` connects, in order: (1) a watermark-based trigger on `PredictionOutcome.id` (reused unchanged from M1.32), (2) M1.39's `build_learning_dataset` to (re)build the versioned learning dataset, (3) M1.43's `compare_candidate_model` to evaluate the candidate against production on that dataset, (4) M1.44's `evaluate_promotion` to gate whether the candidate becomes active, and (5) an optional caller-supplied discovery trigger. Every step composes an existing, already-tested EPIC's public entry point wholesale; this module's only genuinely new logic is the trigger, the wiring between steps, the audit row, and the discovery-trigger hook.

### Scheduling / Trigger Rules

Identical to M1.32's watermark mechanism (reused constants `DEFAULT_MIN_NEW_OUTCOMES`, `OUTCOME_RAN`/`OUTCOME_SKIPPED`, `SKIP_REASON_INSUFFICIENT_NEW_EVIDENCE`, imported not redefined): each `SelfLearningCycle` row records the highest `PredictionOutcome.id` it considered; a cycle with fewer new outcomes than `min_new_outcomes` since the last cycle is recorded `SKIPPED` with an explicit reason and never touches the dataset, comparison, or promotion gate (AC: "insufficient evidence causes no change"; scope: "keep the current model when evidence is insufficient"). "The loop runs without manual intervention once enabled" (AC) holds because a caller need only invoke `run_self_learning_cycle` on any schedule (a cron job, a scheduled task) -- the function itself decides whether there is enough new evidence to act on.

### Failure Recovery

"The system can resume safely after interruption" (AC) holds by the same watermark mechanism: the next call to `run_self_learning_cycle` always recomputes `new_outcomes_count` from the last successfully *committed* cycle's watermark, so a crash between cycles never double-counts or loses evidence -- there is no partial-cycle state to recover, only a fresh, correct recomputation. "Failed learning cycles do not stop ordinary recommendation tracking" (AC) holds structurally: this module has no dependency edge from the recommendation-generation pipeline (M1.12-M1.14) into it, and no dependency edge from it back into that pipeline other than reading already-immutable `PredictionOutcome` rows -- a failure here cannot propagate there.

### Model Lineage

Every `SelfLearningCycle` row records `dataset_version` (M1.39), `comparison_version` (M1.43), and `model_promotion_decision_id` (a foreign key into M1.44's immutable `model_promotion_decisions` log) -- a complete, queryable chain from one learning cycle back through the exact comparison evidence and dataset version that produced its promotion decision (AC: "active model changes are traceable to comparison evidence"; scope: "preserve a complete lineage from recommendation to model version"). `get_self_learning_cycle_history` returns the full, immutable, chronologically ordered sequence (AC: "every learning cycle has a unique version and audit record").

### Promotion Evidence

This module never recomputes or second-guesses M1.44's decision -- it calls `evaluate_promotion` exactly once per cycle and records whatever it returns, promoted or rejected (AC: "no model changes occur without the promotion gate"). There is no code path in this module that could change the active model outside that call.

### Discovery Triggering

"Trigger renewed discovery using the active model" (scope) is implemented as an optional, caller-supplied `trigger_discovery: Callable[[], None] | None` parameter -- this module never calls any external service (ChatGPT, a live market feed) itself. Discovery is triggered only after a cycle actually ran (never on a `SKIPPED` cycle), regardless of whether the candidate was promoted or rejected, since there is always some active model (newly promoted or the prior one) to discover with. `SelfLearningCycle.discovery_triggered` records whether it fired.

### End-to-End Validation

`test_enough_new_outcomes_runs_the_full_pipeline` proves a single call wires all three composed EPICs together (`dataset_version`, `comparison_version`, and `model_promotion_decision_id` all populated from one cycle). `test_discovery_is_triggered_after_a_cycle_runs`/`test_discovery_is_not_triggered_when_cycle_is_skipped` prove the discovery hook fires exactly when it should. `test_watermark_advances_incrementally_across_cycles` and `test_rerunning_immediately_with_no_new_outcomes_is_skipped` prove resumability. `test_learning_cycle_never_writes_to_predictions` proves historical immutability directly.

### Design Decisions

- **New table `self_learning_cycles`** (migration `0030`, chains off M1.44's `0029`), deliberately separate from M1.32's `learning_cycles` table for the same reason M1.44 kept its own table separate from M1.31's: the evidence and lineage shape differs structurally (`dataset_version`/`comparison_version`/`model_promotion_decision_id` vs. M1.32's `discovery_effectiveness_version`/`calibration_candidate_version`/`candidate_model_evaluation_version`/`model_promotion_id`). M1.32's own module and table are left completely untouched.
- **Reuses rather than duplicates**: M1.32's watermark trigger constants (imported directly, not redefined), M1.39's `build_learning_dataset`, M1.43's `compare_candidate_model`/`ModelFunction`, M1.44's `evaluate_promotion`.
- **No autonomous trading, no promotion based on training performance alone, no deletion of historical recommendations, no future information for past predictions** (all four non-goals) hold structurally: this module has no trading code path, its only evidence input is M1.43's dataset-scoped comparison (itself built from M1.39's point-in-time-safe frozen columns), and it never deletes or backdates anything.

### Files Changed

- `app/continuous_self_learning_loop.py` — new: `run_self_learning_cycle`, `get_self_learning_cycle_history`, `CYCLE_RULE_VERSION`.
- `app/models.py` — new `SelfLearningCycle` model.
- `migrations/versions/0030_self_learning_cycles.py` — new migration.
- `tests/test_continuous_self_learning_loop.py` — new: 8 tests.
- `docs/epics/EPIC-M1.45-continuous-self-learning-loop.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_continuous_self_learning_loop.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0030_self_learning_cycles`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0029` through `0030` (verified `self_learning_cycles` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **389 passed, 0 failed** (381 pre-existing from `main` + 8 new).
- `pytest -q tests/test_continuous_self_learning_loop.py -v`: **8 passed** — empty history is `SKIPPED` with an explicit reason and no discovery trigger; enough new outcomes runs the full pipeline with dataset/comparison/promotion all populated; discovery is not triggered on a skipped cycle; discovery is triggered after a cycle actually runs; rerunning immediately with no new outcomes is skipped; the watermark advances incrementally across cycles; no `Prediction` row is ever mutated by a cycle; the full cycle history reports the correct RAN/SKIPPED sequence.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] The loop runs without manual intervention once enabled (a single `run_self_learning_cycle` call per schedule tick is sufficient; the trigger decides whether to act).
- [x] No model changes occur without the promotion gate (`evaluate_promotion` is the sole decision point, called exactly once per `RAN` cycle).
- [x] Insufficient evidence causes no change (`SKIPPED` cycles never touch the dataset, comparison, or promotion gate).
- [x] Every learning cycle has a unique version and audit record (`SelfLearningCycle` row per attempt, `dataset_version`/`comparison_version` recorded).
- [x] Active model changes are traceable to comparison evidence (`model_promotion_decision_id` foreign key into M1.44's immutable log).
- [x] Historical recommendations remain immutable (no write path to `Prediction`/`PredictionOutcome`; proven by test).
- [x] Failed learning cycles do not stop ordinary recommendation tracking (no dependency edge from the recommendation pipeline into this module).
- [x] The system can resume safely after interruption (watermark recomputed fresh from the last committed cycle every time).

### Claude Assessment

I believe this implementation satisfies all eight acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof of the discovery-trigger hook firing exactly when it should. This EPIC composes M1.39/M1.43/M1.44's entry points wholesale and reuses M1.32's watermark trigger unchanged, adding only the wiring, lineage, and an optional, decoupled discovery-trigger hook as genuinely new logic. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
