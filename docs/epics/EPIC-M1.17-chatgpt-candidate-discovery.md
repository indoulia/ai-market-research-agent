# EPIC-M1.17 — ChatGPT Candidate Discovery

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
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

## Dependency Chain

### Previous / Required
- **M1.8 — Positive Consensus Engine** — defines the positive qualification gate.
- **M1.13 — Positive Recommendation Generator** — provides the same quantitative recommendation path used by internally discovered candidates.

### Next / Unlocks
- No downstream EPIC is currently committed. Future discovery enhancements must be separately defined and approved.

### Chain Position

`M1.8 → M1.13 → M1.17`

M1.17 is a side branch from the core recommendation path. It does **not** require M1.14, M1.15, or M1.16 to execute.

### Execution Rule

Do not execute M1.17 until M1.8 and M1.13 are implemented, reviewed, and merged. ChatGPT discovery must never bypass quantitative qualification.

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
