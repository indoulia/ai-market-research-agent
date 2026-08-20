# EPIC-M1.14 — Recommendation Selection & Daily Limit

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P1

## Objective

Select the strongest qualifying positive opportunities from all candidates without allowing marginal or excessive recommendations to dilute the signal.

## Scope

1. Define deterministic ranking using the approved opportunity score and required tie-breakers.
2. Define the minimum score/qualification boundary for selection.
3. Define a configurable maximum number of recommendations per scan/day.
4. Handle ties deterministically.
5. Preserve unselected qualifying candidates as non-selected candidates for auditability.
6. Persist selection-rule version and selection outcome.
7. Add tests for ranking, limits, ties, empty input, and boundary conditions.

## Non-goals

- Changing positive consensus.
- Changing the underlying ML model.
- Portfolio optimization.
- Trading execution.
- LLM-based selection.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Selection is deterministic for identical inputs.
- [ ] Only candidates that already qualify positively can be selected.
- [ ] Daily/scan recommendation limits are enforced.
- [ ] Ties are resolved deterministically.
- [ ] Unselected qualifying candidates remain auditable.
- [ ] Selection-rule version is traceable.
- [ ] Tests cover normal, limit, tie, and boundary cases.

## Dependencies

- M1.13 — Positive Recommendation Generator

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
