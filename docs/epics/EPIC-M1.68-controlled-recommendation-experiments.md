# EPIC-M1.68 — Controlled Recommendation Experiments

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Provide an isolated framework for comparing recommendation models, scoring rules, and evidence strategies without contaminating production history.

## Scope
- Define experiment configuration and hypothesis.
- Run candidate strategies against historical or controlled evaluation populations.
- Keep experiment data separate from production outcomes.
- Compare accuracy, returns, risk, calibration, and consistency.
- Produce reproducible experiment reports.

## Acceptance Criteria
- Experiments are isolated and versioned.
- No experiment can mutate production model state.
- Comparison metrics use the same objective outcome definitions.
- Results are reproducible from stored configuration.

## Dependencies
Previous: M1.67.
Next: M1.69.

## Completion Report
Update this EPIC with final implementation evidence before merge.
