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

## Dependency Chain

### Previous / Required
- **M1.8 — Positive Consensus Engine** — defines the positive qualification gate.
- **M1.9 — Positive Opportunity Scoring** — provides the opportunity score used by the recommendation path.
- **M1.10 — Positive Horizon Selection** — provides the selected 1/3/5/7-day horizon.
- **M1.12 — Market Universe & Daily Candidate Scan** — provides the candidate scan context.

### Next / Unlocks
- **M1.14 — Recommendation Selection & Daily Limit** — selects the strongest qualifying recommendations.
- **M1.15 — Recommendation Lifecycle & Outcome Scheduler** — tracks issued recommendations through their selected horizon.
- **M1.17 — ChatGPT Candidate Discovery** — routes externally discovered candidates through this same recommendation path.

### Chain Position

`M1.8 + M1.9 + M1.10 + M1.12 → M1.13 → M1.14 → M1.15 → M1.16`

M1.17 branches from M1.8 and M1.13 after the core quantitative recommendation path is established.

### Execution Rule

Do not execute M1.14, M1.15, or M1.17 until M1.13 is implemented, reviewed, and merged. Do not bypass missing upstream EPICs.

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
