# EPIC-M1.84 — Trust-Driven Learning & Recommendation Control

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_READY
**Priority:** P0

## Objective
Close the daily trust-improvement loop so MRA continuously uses measured outcomes, trust, drift, data quality and model evidence to improve prediction reliability while publishing only positive actionable recommendations.

## Scope
- Recalculate trust from newly closed outcomes on a controlled schedule.
- Update trust by horizon, regime and other sufficiently sampled segments.
- Detect degradation and calibration drift.
- Generate learning/recalibration candidates from evidence.
- Replay candidates against historical point-in-time data.
- Validate candidates out-of-sample.
- Compare candidates against the production baseline.
- Promote only when predefined evidence gates are satisfied.
- Roll back or quarantine models that regress.
- Recompute recommendation eligibility using the current trusted model state.
- Preserve all trust, learning, promotion and recommendation decisions as immutable history.
- Provide longitudinal trust reporting so users can see whether reliability is improving over time.

## Acceptance Criteria
- Trust changes only from measured evidence.
- A daily outcome can contribute to future trust after the defined closure process.
- Trust can increase, decrease or remain unchanged.
- Model changes require replay + out-of-sample validation + promotion gate.
- Regressions can automatically quarantine a candidate or active model according to policy.
- Recommendation eligibility uses current trust and positive-only gates.
- Historical trust and model versions remain reconstructable.
- The system can report trust trend over time.

## Dependency Chain
**Previous:** M1.77, M1.78, M1.79, M1.80, M1.81, M1.82, M1.83, M1.45, M1.57, M1.67.
**Next:** Production observation and evidence-driven refinement only.

## Execution Rule
The system must never learn by silently rewriting history. Every adjustment is a candidate, every candidate is validated, and every promoted model is versioned. Positive-only recommendation output must not remove negative outcomes from internal learning evidence.
