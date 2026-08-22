# EPIC-050 — Recommendation Revision & Versioning

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** EPIC-046, EPIC-049

## Objective
Allow a live recommendation to be revised when material new information changes the system view while preserving every prior version and its original prediction.

## Scope
- Immutable recommendation versions.
- Revision reason and triggering evidence.
- New target, SL, horizon, score, confidence, and evidence snapshot when revised.
- Version-to-version comparison.
- Clear active version for users.
- Preserve original and previous outcomes/history.

## Acceptance Criteria
- A revision never overwrites a prior recommendation version.
- Every revision has a reason and timestamp.
- Users can see what changed and why.
- Tracking associates outcomes with the correct version.
- Revisions are deterministic and auditable.
- Tests cover multiple revisions and concurrent/duplicate triggers.

## Dependency Chain
EPIC-046/EPIC-049 → EPIC-050 → EPIC-051

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-050

### Branch

autonomous/epic-m1-55, branched cleanly from `main` (both declared dependencies -- EPIC-046 and EPIC-049 -- are already merged).

### Objective

Allow a live recommendation to be revised when material new information changes the system's view, while preserving every prior version and its original prediction, untouched.

### Design

`Prediction` rows are already immutable (EPIC-004/EPIC-016). A "revision" is always a brand-new `Prediction`, built through the exact same EPIC-009/EPIC-010/EPIC-016 pipeline with fresh inputs by whatever caller decides a revision is warranted (e.g. EPIC-049's revalidation trigger finding `revalidation_required=True`) -- this module's only job is `create_recommendation_revision`, linking that new prediction as the next version of an existing recommendation. It never (re)computes scoring itself, so "new target, SL, horizon, score, confidence, and evidence snapshot when revised" (scope) falls out for free: the revised `Prediction` already carries its own real values, and EPIC-042/EPIC-043 can be run against it exactly as for any other prediction.

### Linear Version Chain

`RecommendationRevision` has a uniqueness constraint on `previous_prediction_id` -- a prediction can be superseded by at most one next version, keeping the chain strictly linear rather than allowing it to branch. `get_active_version` returns the latest revision's prediction, or the original itself if never revised (AC: "clear active version for users").

### Duplicate vs. Concurrent Triggers

Calling `create_recommendation_revision` again with the identical `(previous_prediction, revised_prediction)` pair is idempotent and returns the existing row (covers "duplicate ... triggers"). Calling it again for the same `previous_prediction` with a genuinely *different* `revised_prediction` raises `ConcurrentRevisionError` rather than silently branching the chain (covers "concurrent ... triggers") -- proven directly by test in both directions.

### Revision Reason, Timestamp, and Comparison

Every revision requires one of three structured, validated reasons (`MATERIAL_EVIDENCE_CHANGE`/`EVIDENCE_STALE`/`MANUAL_TRIGGER`) and a `revised_at` timestamp (AC: "every revision has a reason and timestamp"); an optional `triggering_evidence_revalidation_check_id` links directly to the EPIC-049 check that prompted it, where applicable (scope: "revision reason and triggering evidence"). `compare_versions` computes the delta in opportunity score, confidence, predicted probability, target/stop return, and whether the horizon changed between any two chained versions (AC: "users can see what changed and why", combined with the stored reason).

### Preserving History

Because each version is a genuinely separate `Prediction` row, EPIC-005's outcome evaluation, EPIC-031's tracking, and EPIC-043's evidence snapshot already associate correctly with whichever version they were run against -- no new code was needed for "tracking associates outcomes with the correct version" or "preserve original and previous outcomes/history" (AC); it holds by construction of the whole platform's existing per-prediction data model.

### Immutability

`RecommendationRevision` carries a `before_update` guard (`RecommendationRevisionImmutableError`); a revision, once recorded, can never be edited, only superseded by a further revision (AC: "a revision never overwrites a prior recommendation version").

### Files Changed

- `app/recommendation_revision.py` — new: `create_recommendation_revision`, `get_revision_history`, `get_active_version`, `compare_versions`, reason constants, `InvalidRevisionError`, `ConcurrentRevisionError`, `RecommendationRevisionImmutableError`.
- `app/models.py` — new `RecommendationRevision` model.
- `migrations/versions/0038_recommendation_revisions.py` — new migration.
- `tests/test_recommendation_revision.py` — new: 10 tests.
- `docs/epics/EPIC-050-recommendation-revision-versioning.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_recommendation_revision.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0038_recommendation_revisions`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0037` through `0038` (verified `recommendation_revisions` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **488 passed, 0 failed** (478 pre-existing from `main` + 10 new).
- `pytest -q tests/test_recommendation_revision.py -v`: **10 passed** — a revision never overwrites the original; every revision has a reason and timestamp; multiple revisions build a correct linear chain with the active version tracking the latest; the active version is the original itself when never revised; a duplicate trigger is idempotent; a concurrent trigger with a genuinely different revision is rejected; an invalid revision reason and a cross-stock revision are each rejected; version comparison shows the real delta between two versions; a revision row is immutable after creation.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] A revision never overwrites a prior recommendation version (`Prediction` immutability inherited from EPIC-004; `RecommendationRevision` itself guarded too).
- [x] Every revision has a reason and timestamp (`revision_reason` validated against a fixed vocabulary; `revised_at` required).
- [x] Users can see what changed and why (`compare_versions` + `revision_reason`).
- [x] Tracking associates outcomes with the correct version (holds by construction -- each version is its own `Prediction`).
- [x] Revisions are deterministic and auditable (`get_revision_history`, `revision_rule_version`, optional link to the triggering EPIC-049 check).
- [x] Tests cover multiple revisions and concurrent/duplicate triggers (all covered explicitly).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof that duplicate triggers are idempotent while concurrent, conflicting triggers are rejected rather than silently corrupting the version chain. This EPIC never recomputes scoring itself -- it composes whatever fresh `Prediction` a caller (e.g. one wired to EPIC-049's revalidation trigger) already produced through the existing pipeline, and inherits outcome/tracking/evidence correctness for free from this platform's existing per-prediction data model. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
