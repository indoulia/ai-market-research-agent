# EPIC-M1.85 — Prediction Attribution

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P1

## Objective
Determine which evidence, features, market conditions and model signals contributed to successful and failed positive predictions, so MRA can learn what actually drives reliable outcomes.

## Scope
- Attribute prediction decisions to material input factors.
- Preserve point-in-time attribution snapshots.
- Compare attribution patterns for successful vs failed predictions.
- Measure attribution by horizon and market regime.
- Identify consistently useful and consistently misleading factors.
- Feed attribution evidence into controlled experiments and learning.
- Never claim causal impact when only predictive association is established.

## Acceptance Criteria
- Every eligible prediction has explainable attribution evidence.
- Attribution is reproducible from historical inputs.
- Successful and failed predictions can be compared.
- Attribution can be segmented by horizon and regime.
- Historical attribution is immutable.
- Learning consumes attribution as evidence, not as assumed causality.

## Dependencies
Previous: M1.48, M1.66, M1.77, M1.78.
Next: M1.86.
