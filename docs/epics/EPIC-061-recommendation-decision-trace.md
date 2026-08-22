# EPIC-061 — Recommendation Decision Trace

Status: DONE
Execution Status: COMPLETED

## Objective
Make every recommendation reproducible from its exact inputs, evidence, rules, model, score, target, SL, and confidence versions.

## Scope
- Capture input feature snapshot.
- Capture evidence sources and timestamps.
- Capture scoring and confidence versions.
- Capture target/SL methodology.
- Capture qualification and rejection reasons.
- Provide a deterministic decision trace.

## Acceptance Criteria
- A historical recommendation can be reconstructed without current data.
- Every material decision has an explicit reason.
- Trace data is immutable.
- Trace output is suitable for debugging and user explanation.

## Dependencies
Previous: EPIC-060.
Next: EPIC-062.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-061

### Branch

autonomous/epic-m1-66, branched cleanly from `main` (the declared dependency -- EPIC-060 -- is already merged).

### Objective

Make every recommendation decision -- qualified or rejected -- reproducible from its exact inputs, evidence, rules, model, score, target, SL, and confidence versions, consolidated into one immutable, self-contained row.

### Design

Every field this module captures is already immutable somewhere else in this platform (`Prediction` via EPIC-004/EPIC-016, `RecommendationGeneration` via EPIC-008, `RecommendationPublication` via EPIC-042, `RecommendationEvidenceItem` via EPIC-043) -- `capture_decision_trace`'s own contribution is consolidation, not new computation: denormalizing all of it into one row so a historical decision can be reconstructed from a single query (AC: "a historical recommendation can be reconstructed without current data").

### Captures Both Qualified and Rejected Decisions

A rejected `RecommendationGeneration` has no `Prediction` at all -- every `Prediction`/EPIC-042/EPIC-043-derived field is `None` for it, and `rejection_reasons` carries EPIC-008's own `failed_criteria` directly (scope: "capture qualification and rejection reasons"; AC: "every material decision has an explicit reason"), proven by `test_rejected_trace_captures_rejection_reasons`. For the qualification-time timestamp of a rejected candidate (which has no `Prediction.as_of_timestamp`), the trace falls back to the originating scan's own `scan_date`.

### Honest Partial Coverage

If EPIC-042/EPIC-043 haven't run yet for a qualified prediction at the moment `capture_decision_trace` is called, the trace records `None`/`[]` for those fields rather than fabricating them -- the same honest partial-coverage pattern used throughout this platform, proven directly by `test_trace_without_publication_or_evidence_yet_records_none_honestly`.

### Immutability

Idempotent by `recommendation_generation_id` -- a decision, once traced, is never re-derived, even if EPIC-042/EPIC-043 are run again later with different results (AC: "trace data is immutable"), proven by `test_trace_is_idempotent`. This module has no write path to any of the tables it reads from -- `test_trace_never_mutates_source_tables` proves the underlying `Prediction`/`RecommendationGeneration` are untouched.

### Suitable for Debugging and User Explanation

Every version string (`model_version`, `feature_version`, `consensus_contract_version`, `horizon_selection_version`, `scoring_contract_version`, `target_stop_methodology_version`), every raw feature input (`sma20_distance`, `volume_ratio_20d`, `atr_percent`), and the full evidence-category snapshot (flattened to plain JSON, so it survives even if EPIC-043's own table structure ever changed) are all present on one row -- a single, human-readable object suitable for both automated debugging and a user-facing "why was this recommended/rejected" explanation (AC: "trace output is suitable for debugging and user explanation").

### Files Changed

- `app/decision_trace.py` — new: `capture_decision_trace`, `get_decision_trace`, `DECISION_TRACE_VERSION`.
- `app/models.py` — new `RecommendationDecisionTrace` model.
- `migrations/versions/0047_decision_trace.py` — new migration.
- `tests/test_decision_trace.py` — new: 5 tests.
- `docs/epics/EPIC-061-recommendation-decision-trace.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_decision_trace.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0047_decision_trace`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0046` through `0047` (verified `recommendation_decision_traces` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **577 passed, 0 failed** (572 pre-existing from `main` + 5 new).
- `pytest -q tests/test_decision_trace.py -v`: **5 passed** — a qualified trace captures the full decision including target/SL and all five evidence categories; a rejected trace captures the real EPIC-008 rejection reasons with no `Prediction`; a trace built before EPIC-042/EPIC-043 have run honestly records `None`/empty rather than fabricating; the trace is idempotent across two calls at different `traced_at` values; the trace never mutates the underlying `Prediction`/`RecommendationGeneration`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] A historical recommendation can be reconstructed without current data (every input/version/evidence field denormalized onto one immutable row).
- [x] Every material decision has an explicit reason (`rejection_reasons` from EPIC-008's `failed_criteria` for rejected candidates; the full evidence/version trail for qualified ones).
- [x] Trace data is immutable (idempotent by `recommendation_generation_id`; no write path to source tables; proven by test).
- [x] Trace output is suitable for debugging and user explanation (one flat, self-contained, human-readable row per decision).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof that a rejected candidate's real EPIC-008 rejection reasons are captured correctly. This EPIC consolidates rather than recomputes -- every value it stores already exists immutably somewhere else in this platform; its only new contribution is bringing them together into one self-contained, queryable row per decision. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
