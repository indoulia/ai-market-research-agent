# EPIC-M1.74 — Evidence Completeness & Point-in-Time Data Quality

> **Note (2026-08-21 QA/integration audit):** This file duplicates
> `EPIC-M1.74-evidence-completeness-point-in-time-data-quality.md`, which is
> `DONE` with a real, verified implementation (`app/evidence_quality_gate.py`).
> No EPIC numbered ≥110 references this file or depends on it as unfinished
> work. Left in place, not deleted/renamed — a human should decide whether to
> formally retire it.

**Status:** READY_FOR_APPROVAL
**Execution Status:** BLOCKED_PENDING_APPROVAL
**Priority:** P0

## Objective
Establish a single quality gate that determines whether market, fundamental, news and event evidence is complete, fresh, point-in-time safe and trustworthy enough for a recommendation.

## Scope
- Combine freshness, source reliability, completeness and provenance signals.
- Detect missing, stale, contradictory and future-dated evidence.
- Enforce point-in-time availability for historical replay and learning.
- Produce explicit evidence-quality states and reasons.
- Prevent insufficient evidence from silently entering score/confidence calculations.
- Preserve quality decisions immutably for each recommendation.
- Add leakage, stale-data and incomplete-evidence tests.

## Acceptance Criteria
- Every recommendation can report evidence coverage by category.
- Future data is rejected from historical evaluation.
- Stale or unreliable evidence lowers/blocks trust according to policy.
- Evidence gaps are visible to users and downstream learning.
- Quality decisions are reproducible and auditable.

## Dependency Chain
**Previous:** M1.72 Fundamental Data Ingestion + M1.73 News & Event Intelligence + M1.35/M1.48/M1.54/M1.64/M1.65.
**Next:** M1.75 Short-Horizon Probability & Outcome Distribution.

## Execution Rule
This is a safety/data-quality boundary, not a scoring enhancement. It must not invent values to improve completeness.
