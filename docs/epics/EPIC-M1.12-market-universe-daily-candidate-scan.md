# EPIC-M1.12 — Market Universe & Daily Candidate Scan

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P1

## Objective

Automatically scan the supported NSE universe each trading day and produce a deterministic candidate set for downstream evaluation.

## Scope

1. Define the eligible NSE universe using available persisted/security data.
2. Identify the trading date and prevent duplicate daily scans.
3. Run the existing feature/prediction pipeline across eligible securities.
4. Exclude missing, stale, or invalid market data explicitly.
5. Persist or expose the candidate set with scan timestamp/date and data/model versions.
6. Make the scan idempotent for the same trading date and universe version.
7. Add deterministic tests for eligibility, stale data, duplicates, and empty candidate sets.

## Non-goals

- Final positive recommendation generation.
- New ML model training.
- Portfolio/trading automation.
- UI/dashboard work.
- ChatGPT-assisted discovery.

## Acceptance Criteria

- [ ] A versioned/traceable NSE universe can be scanned.
- [ ] Each eligible security is evaluated at most once per scan.
- [ ] Stale/invalid data is explicitly excluded and observable.
- [ ] Re-running the same scan does not create duplicate scan results.
- [ ] Candidate results retain scan date and relevant data/model versions.
- [ ] Empty/partial scans are handled without fabricating candidates.
- [ ] Tests cover normal, duplicate, stale-data, and empty-universe cases.

## Dependencies

- M1.3 — Yahoo NSE Historical Data Provider
- M1.8 — Positive Consensus Engine

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
