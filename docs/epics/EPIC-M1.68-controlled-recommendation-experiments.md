# EPIC-M1.68 — Controlled Recommendation Experiments

Status: DONE
Execution Status: COMPLETED

## Objective
Provide an isolated framework for comparing recommendation models, scoring rules, and evidence strategies without contaminating production history.

## Scope
- Define experiment configuration and hypothesis.
- Run candidate strategies against historical or controlled evaluation populations.
- Keep experiment data separate from production outcomes.
- Compare accuracy, returns, risk, calibration, and consistency.
- Produce reproducible experiment reports.

## Acceptance Criteria
- Experiments are isolated and versioned.
- No experiment can mutate production model state.
- Comparison metrics use the same objective outcome definitions.
- Results are reproducible from stored configuration.

## Dependencies
Previous: M1.67.
Next: M1.69.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.68

### Branch

autonomous/epic-m1-68, branched cleanly from `main` (the declared dependency -- M1.67 -- is already merged).

### Objective

Provide an isolated framework for comparing recommendation models, scoring rules, and evidence strategies without contaminating production history.

### Design

`Experiment` groups one or more `ExperimentArm`s. Each arm is a fully explicit, stored configuration -- model version, evaluation window (reusing M1.25's `EvaluationWindow`), and an optional horizon-days filter -- describing which slice of already-evaluated production recommendations to measure. `run_experiment_arm` only ever *reads* `Prediction`/`PredictionOutcome`; it writes its computed metrics into a brand-new `ExperimentResult` row in an entirely separate table (AC: "no experiment can mutate production model state"; scope: "keep experiment data separate from production outcomes"). `compare_experiment` runs every arm belonging to an experiment and reports them side by side, picking the best arm by accuracy among only those with sufficient evidence.

### Isolated & Versioned

`Experiment`/`ExperimentArm` are immutable after creation (`before_update` guards on both, mirroring the platform's established `IMMUTABLE_FIELDS` pattern) -- once a hypothesis and its arms' configuration are recorded, they cannot be silently edited (AC: "experiments are isolated and versioned"). Both `Experiment.experiment_version` and every `ExperimentResult.framework_version` are frozen to `EXPERIMENT_FRAMEWORK_VERSION` ("EXP-001") at creation/computation time. Experiment names and per-experiment arm names are uniquely constrained -- `DuplicateExperimentNameError`/`DuplicateExperimentArmNameError` reject collisions rather than silently merging two distinct hypotheses.

### Same Objective Outcome Definitions

Accuracy is computed from the exact same `PredictionOutcome.outcome in (SUCCESS, FAILURE)` definition M1.16/M1.25/M1.67 already use -- this module does not invent a second notion of success (AC: "comparison metrics use the same objective outcome definitions"). Returns, risk (drawdown), and calibration all read the same already-computed `PredictionOutcome`/`Prediction` fields (`actual_return`, `maximum_drawdown`, `predicted_probability`) every prior evaluation EPIC relies on.

### Reproducible From Stored Configuration

Every `ExperimentResult` snapshots the arm's config it was computed from (`arm_config_snapshot`). Since the underlying evaluated-prediction history is itself immutable and append-only, re-running the same arm's config against the same data always yields identical metrics -- proven directly by `test_rerunning_an_arm_is_reproducible` (two independent runs, two separate `ExperimentResult` rows, identical accuracy/return/drawdown/calibration/consistency values and an identical config snapshot).

### Small Samples Never Drive Conclusions

Below `MIN_SAMPLE_SIZE_FOR_COMPARISON` (M1.16, reused unchanged), every metric except `sample_count` is left `None` and the verdict is `INSUFFICIENT_SAMPLE` -- `compare_experiment` never selects an insufficient-sample arm as the "best" arm, even if it happened to have data.

### Metrics Computed

- **Accuracy**: success rate over the arm's evaluated population.
- **Returns**: mean `actual_return`.
- **Risk**: mean `maximum_drawdown`.
- **Calibration**: mean absolute error between `predicted_probability` and the realized binary outcome.
- **Consistency**: population standard deviation of `actual_return` (lower = more consistent).

### Files Changed

- `app/recommendation_experiments.py` — new: `create_experiment`, `add_experiment_arm`, `run_experiment_arm`, `get_arm_results`, `compare_experiment`, error/verdict constants.
- `app/models.py` — new `Experiment`, `ExperimentArm`, `ExperimentResult` models.
- `migrations/versions/0049_experiments.py` — new migration.
- `tests/test_recommendation_experiments.py` — new: 9 tests.
- `docs/epics/EPIC-M1.68-controlled-recommendation-experiments.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_recommendation_experiments.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0049_experiments`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0048` through `0049` (verified `experiments`/`experiment_arms`/`experiment_results` created), `downgrade -1` (verified all three dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **593 passed, 0 failed** (584 pre-existing from `main` + 9 new).
- `pytest -q tests/test_recommendation_experiments.py -v`: **9 passed** — insufficient sample produces no unsafe conclusion; a ready verdict computes exact, hand-verified accuracy/return/drawdown/calibration/consistency values; re-running the same arm is byte-for-byte reproducible across two independent runs; duplicate experiment and arm names are rejected; experiment and arm configuration are immutable after creation; comparing an experiment picks the best *ready* arm by accuracy while correctly excluding an insufficient-sample arm; running experiments never writes to production `Prediction`/`PredictionOutcome` rows.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Experiments are isolated and versioned (unique names, immutable config, frozen `experiment_version`/`framework_version`).
- [x] No experiment can mutate production model state (read-only over `Prediction`/`PredictionOutcome`; proven by test).
- [x] Comparison metrics use the same objective outcome definitions (same `SUCCESS`/`FAILURE` definition as M1.16/M1.25/M1.67).
- [x] Results are reproducible from stored configuration (`arm_config_snapshot`; proven by direct re-run test).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that re-running the same experiment arm configuration against the same underlying data produces byte-for-byte identical metrics. This EPIC reuses M1.25's `EvaluationWindow` and the platform's established outcome/sample-size conventions rather than inventing new ones, and never writes to any production table. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
