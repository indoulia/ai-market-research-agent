# EPIC-047 — Structured User Feedback

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** EPIC-046

## Objective
Allow users to provide structured feedback on recommendation quality without treating opinion as objective outcome truth.

## Scope
- Feedback on target, SL, confidence, market context, news/events, fundamentals, and overall recommendation.
- Pre-outcome and post-outcome feedback.
- Structured reason codes plus optional comment.
- Feedback timestamp and recommendation/model version.
- Immutable feedback records.

## Acceptance Criteria
- User can submit structured feedback for a recommendation.
- Feedback is linked to the exact recommendation version.
- Feedback cannot overwrite objective outcomes.
- Multiple feedback events are retained.
- Feedback can be queried for later analysis.
- Tests cover validation, persistence, duplicates, and historical immutability.

## Dependency Chain
EPIC-046 → EPIC-047 → EPIC-048

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-047

### Branch

autonomous/epic-m1-52, branched cleanly from `main` (the declared dependency -- EPIC-046 -- is already merged).

### Objective

Allow users to submit structured feedback on recommendation quality without ever treating that opinion as objective outcome truth.

### Design

`RecommendationFeedback` is a new, append-only table -- deliberately with **no uniqueness constraint**, unlike almost every other EPIC in this platform (which is idempotent-by-key). A user can legitimately feel the same way twice, or feel differently pre- and post-outcome about the same recommendation; `submit_feedback` always inserts a new row, even one that looks identical to a prior submission (AC: "multiple feedback events are retained").

### Categories & Reason Codes

Seven categories cover the full scope: `TARGET`, `STOP_LOSS`, `CONFIDENCE`, `MARKET_CONTEXT`, `NEWS_EVENTS`, `FUNDAMENTALS`, `OVERALL`. Reason codes are a single shared, structured vocabulary applicable across any category (`AGREE`/`TOO_HIGH`/`TOO_LOW`/`WRONG_DIRECTION`/`MISSING_CONTEXT`/`OUTDATED_DATA`/`OTHER`) plus an optional free-text `comment` (scope: "structured reason codes plus optional comment"). Both are validated before any write; an unknown category or reason code, an empty `user_id`, or an over-length comment all raise `InvalidFeedbackError`.

### Pre-/Post-Outcome Staging

`feedback_stage` is derived automatically -- never user-supplied -- from whether a `PredictionOutcome` already exists for the prediction at submission time, since the system already knows this objectively (scope: "pre-outcome and post-outcome feedback").

### Linked to the Exact Recommendation Version

Every feedback row stores `model_version`, copied from the immutable `Prediction` row at submission time, so a piece of feedback stays linked to the exact recommendation version even after a future model change (AC: "feedback is linked to the exact recommendation version").

### Feedback Cannot Overwrite Objective Outcomes

This module never reads from or writes to `PredictionOutcome`/`OutcomeMeasurement` beyond a single existence check used only to derive `feedback_stage` -- there is no code path here that could alter an objective outcome (AC), proven directly by `test_feedback_cannot_overwrite_objective_outcomes`.

### Immutability & Queryability

`RecommendationFeedback` carries a `before_update` immutability guard (`RecommendationFeedbackImmutableError`) -- a submitted feedback row can never be edited (scope: "immutable feedback records"). `get_feedback_for_prediction`/`get_feedback_for_user`/`get_feedback_by_category` support querying by any of the AC's required dimensions (AC: "feedback can be queried for later analysis").

### Files Changed

- `app/recommendation_feedback.py` — new: `submit_feedback`, `get_feedback_for_prediction`, `get_feedback_for_user`, `get_feedback_by_category`, category/reason/stage constants, `InvalidFeedbackError`, `RecommendationFeedbackImmutableError`.
- `app/models.py` — new `RecommendationFeedback` model.
- `migrations/versions/0036_recommendation_feedback.py` — new migration.
- `tests/test_recommendation_feedback.py` — new: 11 tests.
- `docs/epics/EPIC-047-structured-user-feedback.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_recommendation_feedback.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0036_recommendation_feedback`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0035` through `0036` (verified `recommendation_feedback` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **462 passed, 0 failed** (451 pre-existing from `main` + 11 new).
- `pytest -q tests/test_recommendation_feedback.py -v`: **11 passed** — a user can submit structured feedback; feedback is linked to the exact model version; pre-outcome and post-outcome feedback are staged correctly; feedback never alters the objective `PredictionOutcome`; an invalid category, an invalid reason code, and an empty `user_id` are each rejected; duplicate-looking feedback is retained as two distinct rows, never deduplicated; a feedback row is immutable after creation; feedback is queryable by prediction, user, and category.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] User can submit structured feedback for a recommendation (`submit_feedback`, validated category/reason code).
- [x] Feedback is linked to the exact recommendation version (`model_version` copied from the immutable `Prediction` at submission time).
- [x] Feedback cannot overwrite objective outcomes (no write path to `PredictionOutcome`/`OutcomeMeasurement`; proven by test).
- [x] Multiple feedback events are retained (no uniqueness constraint; proven directly by test).
- [x] Feedback can be queried for later analysis (`get_feedback_for_prediction`/`get_feedback_for_user`/`get_feedback_by_category`).
- [x] Tests cover validation, persistence, duplicates, and historical immutability (all covered; see Test Results).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that duplicate-looking feedback is retained rather than collapsed -- a deliberate departure from this platform's usual idempotent-by-key pattern, since feedback is opinion, not a fact to deduplicate. This EPIC introduces a clean, additive, append-only feedback log that never touches the objective outcome tables it sits alongside. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
