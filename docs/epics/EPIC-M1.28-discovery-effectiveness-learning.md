# EPIC-M1.28 — Discovery Effectiveness Learning

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1

## Objective
Measure which discovery sources and candidate characteristics actually produce successful recommendations.

## Scope
- Record discovery basis for every candidate: universe, market-cap, sector, industry, technical/event trigger, user watchlist, or external discovery.
- Track candidate → recommendation → outcome conversion.
- Measure discovery success by source, segment, and horizon.
- Identify high- and low-performing discovery paths.
- Preserve discovery provenance permanently.

## Non-goals
- Automatically changing discovery rules.
- LLM-controlled recommendations.
- Trading automation.

## Acceptance Criteria
- Every candidate has traceable discovery provenance.
- Discovery effectiveness is measurable after outcomes close.
- Metrics distinguish candidate rejection from recommendation failure.
- Results are segmented by market regime and horizon where available.
- Historical provenance cannot be overwritten.

## Dependency Chain
**Previous:** M1.17, M1.21, M1.26, M1.27  
**Next:** M1.30, M1.32

## Completion Report
`docs/epics/EPIC-M1.28-discovery-effectiveness-learning.md`
