# EPIC-M1.99 — Cross-Sectional Opportunity Ranking

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Select the strongest positive opportunities by comparing candidates against one another using calibrated probability, trust, expected return, risk, evidence quality and stability.

## Scope
- Rank qualified positive candidates across the current universe.
- Support horizon-specific ranking.
- Combine probability, expected return, risk, reward/risk, trust and evidence quality.
- Penalize instability, concentration and weak evidence.
- Preserve ranking snapshots and selection reasons.
- Measure ranking effectiveness against alternatives and benchmarks.

## Acceptance Criteria
- Ranking is deterministic and explainable.
- Only positive-gated candidates enter the recommendation feed.
- Ranking favors evidence-backed, high-trust opportunities.
- Historical ranking decisions are reconstructable.
- Ranking performance can be measured independently from model accuracy.

## Dependencies
Previous: M1.87, M1.98.
Next: M1.100.
