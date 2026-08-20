# EPIC-M1.36 — Longitudinal Recommendation Tracking

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_STARTED
**Priority:** P1

## Objective
Track every recommendation from issuance through its selected horizon using immutable daily observations.

## Scope
- Record recommendation entry state.
- Capture daily price/return observations.
- Track progress against horizon.
- Preserve original score, probability, horizon, model, and data snapshot.
- Record interim status without overwriting prior observations.
- Support 1/3/5/7-day tracking where applicable.

## Acceptance Criteria
- [ ] Every issued recommendation has a tracking lifecycle.
- [ ] Daily observations are immutable and timestamped.
- [ ] Original recommendation attributes never change retrospectively.
- [ ] Tracking handles missing market data explicitly.
- [ ] Horizon completion is deterministic.
- [ ] Historical tracking can be reconstructed for any recommendation.

## Dependencies
**Previous:** M1.15, M1.35
**Next:** M1.37, M1.38

## Completion Report
Claude must provide lifecycle evidence, persistence design, tests, and sample historical reconstruction.