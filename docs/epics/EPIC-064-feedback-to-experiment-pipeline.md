# EPIC-064 — Feedback-to-Experiment Pipeline

Status: DONE
Execution Status: COMPLETED

## Objective
Turn repeated structured user feedback into testable learning hypotheses and isolated experiments.

## Scope
- Aggregate structured feedback patterns.
- Detect statistically meaningful recurring feedback.
- Form candidate hypotheses.
- Create controlled experiments from approved hypotheses.
- Keep feedback separate from objective outcomes.

## Acceptance Criteria
- One user's opinion cannot directly change production behavior.
- Feedback patterns require minimum evidence before experimentation.
- Every experiment identifies its feedback source and hypothesis.
- Experiments use the controlled framework from EPIC-063.

## Dependencies
Previous: EPIC-063.
Next: EPIC-065.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-064

### Branch

autonomous/epic-m1-69, branched cleanly from `main` (the declared dependency -- EPIC-063 -- is already merged).

### Objective

Turn repeated structured user feedback into testable learning hypotheses and isolated experiments, using EPIC-063's controlled experiment framework.

### Design

Aggregation and recurrence detection are not reimplemented: they are EPIC-048's `compute_feedback_learning_signals`, whose `VERDICT_WEAK` already means "this (category, reason_code) pattern's success rate is statistically meaningfully below baseline, with at least `MIN_SAMPLE_SIZE_FOR_COMPARISON` evaluated samples." This EPIC's only new contribution, `identify_recurring_feedback_patterns`, additionally requires `repeated_prediction_count >= 1` -- at least one prediction where **more than one distinct user** gave the same feedback (EPIC-048's own `REPEATED_PATTERN_MIN_DISTINCT_USERS` gate) -- before a pattern is eligible for experimentation at all. `create_experiment_from_feedback_signal` then creates a real EPIC-063 `Experiment` with `baseline`/`candidate` arms (the same "one model, two disjoint windows" shape EPIC-062 validated), and a `FeedbackDrivenExperiment` link row recording which feedback pattern motivated it.

### One User's Opinion Cannot Change Production Behavior

Doubly true: this module has no write path to `Prediction`/`ScanCandidate`/any scoring table (same structural guarantee EPIC-048 and EPIC-063 already have -- proven by `test_pipeline_never_writes_to_predictions_or_feedback`), and `create_experiment_from_feedback_signal` raises `InsufficientFeedbackEvidenceError` unless the pattern was independently repeated by more than one user on at least one prediction -- `test_single_user_pattern_is_not_recurring` proves a `VERDICT_WEAK` signal where every prediction only ever received feedback from one distinct user is both excluded from `identify_recurring_feedback_patterns` and rejected outright if passed in directly.

### Minimum Evidence Before Experimentation

Both gates apply before any experiment is created: EPIC-048's own sample-size/margin threshold (`VERDICT_WEAK`) *and* this EPIC's own repeated-user gate. Neither alone is sufficient.

### Every Experiment Identifies Its Feedback Source And Hypothesis

The generated `hypothesis` text names the exact category, reason code, repeat count, distinct-user count, and success rate that motivated the experiment; `FeedbackDrivenExperiment` stores the same provenance in structured, queryable columns rather than only in free text, and is unique per `(feedback_category, feedback_reason_code)` -- a pattern that keeps recurring across later pipeline runs reuses its existing experiment rather than spawning a duplicate (`test_pipeline_is_idempotent_across_runs`).

### Experiments Use The Controlled Framework From EPIC-063

`create_experiment_from_feedback_signal` calls EPIC-063's own `create_experiment`/`add_experiment_arm` directly -- no parallel experiment mechanism is built. `test_experiment_uses_m1_68_comparison_framework` proves the resulting experiment can be run through EPIC-063's own `compare_experiment` unchanged.

### Keep Feedback Separate From Objective Outcomes

The `FeedbackDrivenExperiment` link stores only feedback-aggregate provenance; the experiment's actual metrics are computed exclusively from objective `Prediction`/`PredictionOutcome` history by EPIC-063's own `run_experiment_arm`, never from feedback text or ratings.

### Files Changed

- `app/feedback_experiment_pipeline.py` — new: `identify_recurring_feedback_patterns`, `create_experiment_from_feedback_signal`, `get_experiment_link_for_pattern`, error/version constants.
- `app/models.py` — new `FeedbackDrivenExperiment` model.
- `migrations/versions/0050_feedback_experiments.py` — new migration.
- `tests/test_feedback_experiment_pipeline.py` — new: 6 tests.
- `docs/epics/EPIC-064-feedback-to-experiment-pipeline.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_feedback_experiment_pipeline.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0050_feedback_experiments`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0049` through `0050` (verified `feedback_driven_experiments` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **599 passed, 0 failed** (593 pre-existing from `main` + 6 new).
- `pytest -q tests/test_feedback_experiment_pipeline.py -v`: **6 passed** — a single-user pattern is correctly excluded from recurrence detection and rejected outright if forced; a genuinely repeated pattern is identified and spawns a real experiment with baseline/candidate arms; the pipeline is idempotent across repeated runs on the same pattern; the resulting experiment runs cleanly through EPIC-063's own `compare_experiment`; pattern lookup returns the existing link without creating a duplicate; the pipeline never writes to `Prediction`/`PredictionOutcome`/`RecommendationFeedback`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] One user's opinion cannot directly change production behavior (no write path to production tables; repeated-user gate proven by test).
- [x] Feedback patterns require minimum evidence before experimentation (EPIC-048's sample/margin gate + this EPIC's repeated-user gate).
- [x] Every experiment identifies its feedback source and hypothesis (`FeedbackDrivenExperiment` structured columns + hypothesis text).
- [x] Experiments use the controlled framework from EPIC-063 (`create_experiment`/`add_experiment_arm`/`compare_experiment` called directly, unmodified).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that a feedback pattern voiced by only one distinct user per prediction -- even if statistically "weak" by success rate alone -- is excluded from triggering an experiment. This EPIC composes EPIC-048's feedback aggregation with EPIC-063's experiment framework without modifying or duplicating either, and never writes to any production or feedback table. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
