# EPIC-M1.33 — Continuous Stock Discovery

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Continuously discover new stock candidates for analysis without turning discovery into recommendation.

## Scope
- Maintain a discoverable NSE stock universe.
- Run scheduled discovery scans.
- Generate candidates from measurable market signals.
- Deduplicate candidates across scans.
- Persist discovery timestamp, source, and discovery reason.
- Route candidates into the existing positive-analysis pipeline.
- Preserve candidates that fail qualification as backlog/history rather than deleting them.

## Acceptance Criteria
- [ ] Scheduled discovery produces persisted candidates.
- [ ] Every candidate has a deterministic discovery source/reason.
- [ ] Duplicate candidates are prevented within the defined discovery window.
- [ ] Discovery never directly creates a recommendation.
- [ ] Candidates enter M1.13/M1.14 qualification flow.
- [ ] Failed candidates remain traceable.
- [ ] Discovery runs are reproducible for a given data snapshot.

## Non-goals
- Trading execution.
- Changing recommendation qualification rules.
- Autonomous model promotion.
- UI redesign.

## Dependencies
**Previous:** M1.12, M1.13, M1.14
**Next:** M1.34

## Execution Rule
Do not execute until M1.14 is implemented and merged.

## Completion Report
Claude must append final implementation evidence, tests, data-validation results, and any deviations here.