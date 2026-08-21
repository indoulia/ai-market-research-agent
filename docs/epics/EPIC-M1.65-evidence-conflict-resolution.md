# EPIC-M1.65 — Evidence Conflict Resolution

Status: DONE
Execution Status: COMPLETED

## Objective
Resolve or explicitly surface conflicting market, news, event, and fundamental evidence from multiple sources.

## Scope
- Detect contradictory evidence.
- Compare source reliability and freshness.
- Produce resolved, unresolved, or insufficient-evidence states.
- Reduce confidence when material conflicts remain.
- Preserve all conflicting source evidence for audit.

## Acceptance Criteria
- No source is silently discarded.
- Conflict resolution is deterministic and explainable.
- Unresolved material conflicts can block recommendation qualification.
- Historical evidence remains immutable.

## Dependencies
Previous: M1.64.
Next: M1.66.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.65

### Branch

autonomous/epic-m1-65, branched cleanly from `main` (the declared dependency -- M1.64 -- is already merged).

### Objective

Resolve or explicitly surface conflicting market, news, event, and fundamental evidence for one recommendation, producing an explicit `RESOLVED`/`UNRESOLVED`/`INSUFFICIENT_EVIDENCE` state.

### What "Conflict" Means in This Repo

Given this platform's real evidence sources (M1.48), a literal fact-vs-fact contradiction between two evidence categories cannot happen -- there is no second, independent source for the same fact. `resolve_evidence_conflicts` instead detects the two genuine conflict shapes this platform's data actually supports:
1. **Untrusted-source conflict**: an evidence item that appears `AVAILABLE`/`STALE` (M1.48) whose underlying category M1.64 has separately assessed as untrusted -- the evidence *looks* present, but the reliability layer says not to trust it (scope: "compare source reliability and freshness").
2. **Revalidation conflict**: M1.62's most recent revalidation outcome for this prediction is `WITHDRAWN` or `UPDATED` -- a materially different signal than the "still fully valid" assumption a still-open recommendation currently rests on.

### No Source Silently Discarded

Every M1.48 evidence category present for the prediction is recorded in `evidence_categories_considered`, whether or not it contributed a conflict (AC: "no source is silently discarded"), proven directly by test.

### Deterministic, Explainable States

`INSUFFICIENT_EVIDENCE` when neither an evidence snapshot nor any revalidation history exists yet; `RESOLVED` when evidence exists and zero conflicts are found; `UNRESOLVED` otherwise, with every conflict's category, reason, and detail preserved in the `conflicts` JSON field for audit (scope: "preserve all conflicting source evidence for audit"; AC: "conflict resolution is deterministic and explainable").

### Reducing Confidence & Blocking Qualification

An `UNRESOLVED` resolution computes `confidence_adjustment_ceiling = confidence - CONFIDENCE_CONFLICT_PENALTY (0.15) × conflict_count`, floored at zero -- a new, separate field, never overwriting `Prediction.confidence` itself (scope: "reduce confidence when material conflicts remain"). `blocks_qualification` is set `True` whenever `conflict_count >= MATERIAL_CONFLICT_THRESHOLD` (1) -- a flag a future qualification gate *could* consult (AC: "unresolved material conflicts can block recommendation qualification"); this module itself never intercepts M1.8's consensus engine.

### Historical Immutability

This module has no write path to `Prediction`, `RecommendationEvidenceItem`, or any revalidation/alert table -- `test_resolution_never_mutates_prediction_or_evidence` proves the underlying `Prediction` and M1.48 evidence snapshot are both byte-for-byte unchanged after resolving conflicts (AC: "historical evidence remains immutable"). Idempotent by `(prediction_id, resolved_at)` -- a later `resolved_at` legitimately re-resolves against fresh evidence, never mutating a prior resolution.

### Files Changed

- `app/evidence_conflict_resolution.py` — new: `resolve_evidence_conflicts`, `get_conflict_resolution_history`, state/reason constants.
- `app/models.py` — new `EvidenceConflictResolution` model.
- `migrations/versions/0046_evidence_conflict.py` — new migration.
- `tests/test_evidence_conflict_resolution.py` — new: 7 tests.
- `docs/epics/EPIC-M1.65-evidence-conflict-resolution.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_evidence_conflict_resolution.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0046_evidence_conflict`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0045` through `0046` (verified `evidence_conflict_resolutions` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **572 passed, 0 failed** (565 pre-existing from `main` + 7 new).
- `pytest -q tests/test_evidence_conflict_resolution.py -v`: **7 passed** — no evidence and no revalidation history is `INSUFFICIENT_EVIDENCE`; available evidence with no conflicts considers all five categories; an untrusted-source verdict produces an `UNRESOLVED` conflict that blocks qualification and reduces the confidence ceiling; a `WITHDRAWN` revalidation outcome produces a revalidation conflict; no source is silently discarded (all five categories always considered); resolution is idempotent for the same `resolved_at`; resolution never mutates the underlying `Prediction` or evidence snapshot.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] No source is silently discarded (`evidence_categories_considered` always includes every M1.48 category present; proven by test).
- [x] Conflict resolution is deterministic and explainable (pure function of the evidence snapshot, reliability report, and revalidation history; every conflict carries a reason and detail).
- [x] Unresolved material conflicts can block recommendation qualification (`blocks_qualification`, a consultable flag; proven by test).
- [x] Historical evidence remains immutable (no write path to `Prediction`/`RecommendationEvidenceItem`; proven by test).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof that resolving conflicts never mutates the underlying prediction or evidence snapshot. This EPIC composes M1.48/M1.62/M1.64's existing outputs into two genuine, data-supported conflict types rather than fabricating a fact-vs-fact contradiction this platform's evidence sources cannot actually produce. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
