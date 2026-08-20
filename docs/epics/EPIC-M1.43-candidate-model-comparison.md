# EPIC-M1.43 — Candidate Model Comparison

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_STARTED
**Priority:** P1

## Objective
Compare a candidate prediction/scoring model against the current production model using identical historical evaluation rules.

## Scope
- Define comparable model interfaces.
- Run both models on the same point-in-time dataset.
- Compare success rate, return, calibration, and horizon performance.
- Compare by market regime and discovery segment.
- Record statistical/sample-size limitations.
- Produce a reproducible comparison report.

## Acceptance Criteria
- [ ] Both models receive identical eligible inputs.
- [ ] No future information leaks into either model.
- [ ] Metrics use identical outcome definitions.
- [ ] Comparison includes overall and horizon-level performance.
- [ ] Comparison includes relevant market/segment breakdowns.
- [ ] Insufficient evidence is explicitly reported.
- [ ] Candidate is not promoted by this EPIC.

## Dependencies
**Previous:** M1.30, M1.39, M1.41, M1.42
**Next:** M1.44

## Completion Report
Claude must include model versions, dataset version, evaluation period, metrics, limitations, and comparison decision.