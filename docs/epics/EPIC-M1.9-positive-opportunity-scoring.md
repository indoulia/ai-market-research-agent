# EPIC-M1.9 — Positive Opportunity Scoring

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P1

## Objective

Create a transparent score that ranks stocks that already pass the positive-consensus gate, so the platform can prioritize the strongest positive opportunities without turning ranking into a recommendation by itself.

## Why now

Once positive consensus is explicit, the system needs to distinguish strong qualifying opportunities from marginal qualifying opportunities. The score must remain explainable and reproducible.

## Scope

1. Define a deterministic scoring contract using approved positive signals.
2. Normalize component contributions so no single metric dominates accidentally.
3. Produce a total score plus component-level contributions.
4. Support ranking qualifying candidates by score.
5. Persist the scoring-contract version used for a recommendation candidate.
6. Add tests for ordering, boundary values, missing data, and deterministic repeatability.

## Non-goals

- Changing the positive-consensus gate.
- Training a new ML model.
- Automatically optimizing weights from outcomes.
- LLM-based scoring.
- Negative recommendations.
- Portfolio/trading functionality.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Scoring rules are explicitly documented and versioned.
- [ ] Every score component is explainable.
- [ ] Identical inputs always produce identical scores.
- [ ] Missing/invalid inputs are handled explicitly rather than silently defaulted.
- [ ] Qualifying candidates can be deterministically ranked.
- [ ] Score and scoring-contract version are traceable.
- [ ] Tests cover normal, boundary, missing-data, and tie cases.

## Dependencies

- M1.8 — Positive Consensus Engine
- M1.4 — Persist Recommendation History

## Completion Report

<!-- Claude: populate this section only after implementation. Preserve review history; never erase prior review findings. -->

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
