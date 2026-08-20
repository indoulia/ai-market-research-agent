# EPIC-M1.8 — Positive Consensus Engine

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P1

## Objective

Define and implement the deterministic decision layer that turns model/data signals into a **positive recommendation candidate** only when the required positive criteria are satisfied.

## Why now

M1.4–M1.7 establish recommendation history, objective outcomes, performance measurement, and watchlist evaluation. We now need one explicit, testable definition of what "positive consensus" means instead of allowing individual callers to invent their own thresholds.

## Scope

1. Define a single versioned positive-consensus contract.
2. Define required signals/criteria and their minimum thresholds using the capabilities already present in the repository.
3. Produce an explainable evaluation result containing PASS/FAIL per criterion and an overall qualifying decision.
4. Ensure only qualifying candidates can enter the positive-recommendation path.
5. Persist the criteria/contract version used for a recommendation.
6. Add deterministic unit tests for qualifying, borderline, and failing cases.

## Non-goals

- New ML model development.
- LLM-based final recommendation decisions.
- Negative/sell recommendations.
- Portfolio management or trading.
- UI/dashboard work.
- Optimizing thresholds from historical data; that belongs in a later learning/calibration EPIC.

## Acceptance Criteria

- [ ] Positive consensus is represented by one explicit versioned contract.
- [ ] Every required criterion has a deterministic pass/fail rule.
- [ ] Evaluation output explains each criterion result.
- [ ] A stock cannot become a positive recommendation unless the contract qualifies it.
- [ ] The contract version is traceable for every resulting recommendation.
- [ ] Tests cover positive, borderline, and failing candidates.
- [ ] No subjective LLM decision is required for final qualification.

## Dependencies

- M1.3 — Yahoo NSE Historical Data Provider
- M1.4 — Persist Recommendation History

## Completion Report

<!-- Claude: populate this section only after implementation. Preserve review history; never erase prior review findings. -->

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
