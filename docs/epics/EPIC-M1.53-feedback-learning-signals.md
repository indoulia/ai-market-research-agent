# EPIC-M1.53 — Feedback Learning Signals

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** M1.38, M1.39, M1.52

## Objective
Convert repeated, attributable user feedback into measurable learning signals that can be validated against objective outcomes.

## Scope
- Aggregate feedback by recommendation, horizon, model, score, and feedback type.
- Compare feedback with realized outcomes.
- Detect repeated feedback patterns.
- Measure whether feedback sources are historically predictive.
- Produce candidate learning signals; do not directly alter production scoring.

## Acceptance Criteria
- Feedback patterns are measurable with sample counts.
- Objective outcomes remain the primary truth source.
- No production score changes occur from feedback alone.
- Candidate signals are versioned and reproducible.
- Weak/insufficient feedback evidence is explicitly identified.
- Tests cover aggregation, attribution, and insufficient samples.

## Dependency Chain
M1.38/M1.39/M1.52 → M1.53 → M1.56/M1.57

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.53

### Branch

autonomous/epic-m1-53, branched cleanly from `main` (all three declared dependencies -- M1.38, M1.39, M1.52 -- are already merged).

### Objective

Convert repeated, attributable user feedback (M1.52) into measurable candidate learning signals, validated against objective outcomes (M1.38) -- never altering production scoring by itself.

### Aggregation

`compute_feedback_learning_signals` joins every `RecommendationFeedback` row to its `Prediction` and (if closed) `OutcomeMeasurement`. The primary aggregation is by feedback type (`category`, `reason_code`); secondary breakdowns cover horizon (`by_horizon`), model version (`by_model_version`), and score band (`by_score_band`, reusing M1.22's `SCORE_BAND_COUNT`/`SCORE_BAND_WIDTH`) -- scope: "aggregate feedback by recommendation, horizon, model, score, and feedback type." A prediction with multiple feedback events on the same `(category, reason_code)` contributes to `evaluated_count`/`success_count` at most once, never once per raw feedback row, so a single vocal user cannot outweigh the sample count.

### Comparing Feedback With Realized Outcomes

For each `(category, reason_code)` group, `success_rate` is measured only among that group's distinct predictions that have a real, closed `SUCCESS`/`FAILURE` classification from M1.38 -- objective outcomes are the sole truth source (AC: "objective outcomes remain the primary truth source"); feedback text itself is never treated as a label. The verdict (`OK`/`WEAK`/`INSUFFICIENT_SAMPLE`, reused unchanged from M1.28) compares that rate against the overall baseline across all feedback-linked, evaluated predictions.

### Repeated Feedback Pattern Detection

`repeated_prediction_count` counts, within a `(category, reason_code)` group, how many distinct predictions received that same feedback from at least `REPEATED_PATTERN_MIN_DISTINCT_USERS` (2) independent users -- cross-user agreement, not one person repeating themselves (scope: "detect repeated feedback patterns").

### Candidate Signals, Never Applied

This module has no write path to `Prediction`, `ScanCandidate`, or any scoring table at all -- "no production score changes occur from feedback alone" (AC) holds structurally, proven directly by `test_report_is_versioned_and_never_writes_to_predictions`. Every output is explicitly a read-only, versioned (`FEEDBACK_LEARNING_SIGNAL_VERSION`) candidate signal, mirroring M1.29/M1.30/M1.40's "propose, never apply" posture.

### Weak/Insufficient Evidence

Every signal and segment carries the same evidence-gated verdict; an `OPEN` (not-yet-evaluated) recommendation contributes to `distinct_prediction_count` but not `evaluated_count`, so it can never inflate a success rate before the outcome is actually known (AC: "weak/insufficient feedback evidence is explicitly identified").

### Files Changed

- `app/feedback_learning_signals.py` — new: `compute_feedback_learning_signals`, `FeedbackSignal`/`FeedbackSegmentSignal`/`FeedbackLearningSignalReport` dataclasses.
- `tests/test_feedback_learning_signals.py` — new: 7 tests.
- `docs/epics/EPIC-M1.53-feedback-learning-signals.md` — this completion report.

No migration: pure read-side aggregation over existing tables.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_feedback_learning_signals.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0036_recommendation_feedback`, unchanged -- confirms no migration drift)

### Test Results

- `pytest -q`: **469 passed, 0 failed** (462 pre-existing from `main` + 7 new).
- `pytest -q tests/test_feedback_learning_signals.py -v`: **7 passed** — an insufficient feedback sample is explicitly reported; a feedback reason that consistently precedes failure is flagged `WEAK` while a baseline "agree" signal on winners is `OK`; a repeated cross-user pattern is detected; a single prediction with two feedback events is only counted once in `evaluated_count`; an open (not-yet-evaluated) recommendation is excluded from `evaluated_count`; horizon/model/score-band aggregations are all populated; the report is versioned and never writes to `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: passed, single head unchanged (no migration in this EPIC).

### Acceptance Criteria

- [x] Feedback patterns are measurable with sample counts (`total_feedback_count`/`distinct_prediction_count`/`distinct_user_count`/`repeated_prediction_count` on every signal).
- [x] Objective outcomes remain the primary truth source (`success_rate` computed only from M1.38's real `OutcomeMeasurement` classifications, never from feedback text).
- [x] No production score changes occur from feedback alone (no write path exists in this module at all; proven by test).
- [x] Candidate signals are versioned and reproducible (`FEEDBACK_LEARNING_SIGNAL_VERSION`; deterministic aggregation, no randomness).
- [x] Weak/insufficient feedback evidence is explicitly identified (`VERDICT_INSUFFICIENT_SAMPLE`/`VERDICT_WEAK`, reused from M1.28).
- [x] Tests cover aggregation, attribution, and insufficient samples (all covered; see Test Results).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a direct proof that a feedback reason consistently preceding failed recommendations is correctly flagged `WEAK`, while a baseline agreement signal on winners is `OK`. This EPIC composes M1.16/M1.22/M1.28's existing evidence-gating vocabulary and score-band constants, treats M1.38's objective outcomes as the only truth source, and never writes to any table this platform's scoring depends on. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
