# EPIC-M1.13 — Positive Recommendation Generator

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P1

## Objective

Convert evaluated candidates into positive recommendations only when every required positive gate is satisfied.

## Scope

1. Consume candidate predictions, positive-consensus results, score, and selected horizon.
2. Generate a recommendation only when the positive-consensus contract qualifies the candidate.
3. Persist the recommendation with probability, score, horizon, criteria version, model version, and issuance timestamp.
4. Record explicit non-qualification without creating a negative recommendation.
5. Ensure recommendation creation is idempotent for the same candidate/scan context.
6. Add deterministic tests for qualify, reject, duplicate, and incomplete-input cases.

## Non-goals

- SELL/bearish recommendations.
- Portfolio or trading automation.
- Changing the consensus rules.
- LLM override of quantitative qualification.
- UI/dashboard work.

## Acceptance Criteria

- [ ] No recommendation is created unless positive consensus passes.
- [ ] Every recommendation contains the required traceability fields.
- [ ] Failed candidates are not converted into negative recommendations.
- [ ] Duplicate generation for the same scan context is prevented.
- [ ] Missing required evidence produces no recommendation.
- [ ] Tests prove both positive and rejection paths.

## Dependencies

- M1.8 — Positive Consensus Engine
- M1.9 — Positive Opportunity Scoring
- M1.10 — Positive Horizon Selection
- M1.12 — Market Universe & Daily Candidate Scan

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
