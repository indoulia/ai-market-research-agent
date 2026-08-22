# EPIC-066 — Investment Decision Journal

Status: DONE
Execution Status: COMPLETED

## Objective
Give users a durable history of recommendations, decisions, feedback, and outcomes so they can evaluate their own investing behavior alongside system performance.

## Scope
- Record recommendation snapshots linked to user decisions.
- Record user rationale and structured feedback.
- Link decisions to objective outcomes.
- Show system prediction versus actual result.
- Preserve historical records immutably.

## Acceptance Criteria
- A user can inspect the full lifecycle of a decision.
- User actions and system outcomes are clearly separated.
- Historical records remain available after recommendation retirement.
- Journal data is not used as a production learning signal unless explicitly passed through the approved learning pipeline.

## Dependencies
Previous: EPIC-065.
Next: Future roadmap review.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-066

### Branch

autonomous/epic-m1-71, branched cleanly from `main` (the declared dependency -- EPIC-065 -- is already merged).

### Objective

Give users a durable history of recommendations, decisions, feedback, and outcomes so they can evaluate their own investing behavior alongside system performance.

### Design

This is a composition layer over already-immutable platform history, introducing exactly one new table: `UserDecision` -- the one genuinely new fact this platform did not yet record, what the user *did* about a recommendation (`ACTED_ON`/`DISMISSED`/`DEFERRED`). Everything else is read-only composition: EPIC-061's `RecommendationDecisionTrace` supplies the recommendation snapshot (scope: "record recommendation snapshots linked to user decisions" -- the snapshot is EPIC-061's own, not re-captured here); EPIC-047's `RecommendationFeedback` supplies structured feedback; EPIC-005's `PredictionOutcome` and EPIC-033's `OutcomeMeasurement` supply the objective outcome (scope: "show system prediction versus actual result"). `get_journal_entry` composes all four into one `JournalEntry`; `record_decision` is the only new write path in this module.

### User Actions And System Outcomes Are Clearly Separated

`JournalEntry` keeps `decisions` (this module's own, user-authored rows) and `recommendation_snapshot`/`prediction_vs_actual` (system-computed, read from other modules' immutable tables) as distinct fields -- `test_decisions_and_system_outcomes_are_clearly_separated` proves a user's dismissal is tracked completely independently of the objective FAILURE outcome underneath it.

### Full Lifecycle Is Inspectable, Immutably Preserved

`record_decision` always inserts a new row rather than editing a prior one -- a changed mind produces a new, dated decision, and `get_decision_history` returns the complete chronological sequence (`test_changing_a_decision_preserves_full_history`). Existing rows are immutable after creation (`before_update` guard, `test_decision_is_immutable`).

### Historical Records Remain Available After Recommendation Retirement

Every read in this module is keyed by `recommendation_generation_id`/`prediction_id`, never filtered by `Prediction.status` -- `test_journal_survives_recommendation_retirement` proves a fully evaluated (`status == "EVALUATED"`) prediction's journal entry remains exactly as complete as an open one's.

### Journal Data Is Not A Production Learning Signal Unless Passed Through The Approved Pipeline

This module has no write path to `Prediction`, `ScanCandidate`, or any scoring/selection table (proven by `test_journal_never_writes_to_predictions_or_feedback`), and no other module in this platform imports from it -- a `UserDecision` cannot silently influence anything; using it as a learning signal would require a future, separate, explicitly-approved pipeline (mirroring EPIC-064's own feedback-to-experiment gate).

### Files Changed

- `app/investment_decision_journal.py` — new: `record_decision`, `get_decision_history`, `get_journal_entry`, `get_journal_for_user`, error/version constants.
- `app/models.py` — new `UserDecision` model.
- `migrations/versions/0052_user_decisions.py` — new migration.
- `tests/test_investment_decision_journal.py` — new: 8 tests.
- `docs/epics/EPIC-066-investment-decision-journal.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_investment_decision_journal.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0052_user_decisions`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0051` through `0052` (verified `user_decisions` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **615 passed, 0 failed** (607 pre-existing from `main` + 8 new).
- `pytest -q tests/test_investment_decision_journal.py -v`: **8 passed** — invalid decisions are rejected; the full lifecycle (snapshot, decision, feedback, prediction-vs-actual) is composed correctly; user actions and system outcomes stay clearly separated even when they disagree; changing a decision preserves the full prior history rather than overwriting it; a recorded decision is immutable; a journal entry remains fully available after the underlying prediction is retired/evaluated; per-user journal listing returns exactly the generations that user has decided on and no others; the module never writes to `Prediction`/`PredictionOutcome`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] A user can inspect the full lifecycle of a decision (`get_journal_entry`/`get_decision_history`).
- [x] User actions and system outcomes are clearly separated (`JournalEntry`'s distinct fields; proven by test).
- [x] Historical records remain available after recommendation retirement (no status filtering; proven by test).
- [x] Journal data is not used as a production learning signal unless explicitly passed through the approved learning pipeline (no write path to any production table; not imported anywhere else).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that a fully retired recommendation's journal remains completely inspectable. This EPIC composes EPIC-061's decision trace, EPIC-047's feedback, and EPIC-005/EPIC-033's objective outcomes without modifying or duplicating any of them, and introduces exactly one new, narrowly-scoped table for the one fact the platform genuinely lacked. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
