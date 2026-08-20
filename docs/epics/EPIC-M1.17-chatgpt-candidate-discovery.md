# EPIC-M1.17 — ChatGPT Candidate Discovery

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Priority:** P2

## Objective

Allow ChatGPT-assisted discovery of stocks to investigate while keeping final positive recommendation qualification entirely inside the deterministic quantitative engine.

## Scope

1. Define an input contract for externally discovered candidate stocks.
2. Record discovery source, timestamp, and rationale without treating rationale as quantitative evidence.
3. Route discovered candidates through the same market-data, prediction, positive-consensus, scoring, and horizon evaluation as internally discovered candidates.
4. Produce a clear result: qualifying positive candidate or `NOT MATCHING POSITIVE CONSENSUS`.
5. Persist discovery provenance separately from recommendation evidence.
6. Add tests proving discovery input cannot bypass quantitative qualification.

## Non-goals

- Allowing ChatGPT to directly create recommendations.
- LLM-generated probability or success percentages.
- Trading automation.
- Replacing the quantitative engine.
- UI/dashboard work.

## Acceptance Criteria

- [ ] External discovery candidates use the same quantitative evaluation path as internal candidates.
- [ ] Discovery rationale is clearly separated from quantitative evidence.
- [ ] ChatGPT cannot bypass positive-consensus qualification.
- [ ] Non-qualifying candidates are explicitly recorded as `NOT MATCHING POSITIVE CONSENSUS` where applicable.
- [ ] Discovery provenance is traceable.
- [ ] Tests demonstrate bypass prevention.

## Dependencies

- M1.8 — Positive Consensus Engine
- M1.13 — Positive Recommendation Generator

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
