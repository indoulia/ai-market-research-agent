# EPIC-M1.87 — Positive Opportunity Selection & Ranking Optimization

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Select and rank the strongest positive opportunities from the discovered and analyzed candidate universe using trust, expected opportunity, risk and evidence quality.

## Scope
- Rank only candidates that pass the positive-only gate.
- Combine expected return, probability, trust, reward/risk, evidence quality and stability.
- Control concentration and duplicate opportunities.
- Prefer higher-quality opportunities rather than maximizing recommendation count.
- Support horizon-specific ranking.
- Preserve ranking snapshots for later usefulness measurement.

## Acceptance Criteria
- Ranking is deterministic and explainable.
- Only positive-gated candidates can enter the recommendation feed.
- Ranking favors evidence-backed opportunities.
- Low-trust/high-risk candidates cannot outrank stronger candidates without explicit evidence.
- Historical ranking decisions are reconstructable.

## Dependencies
Previous: M1.75, M1.77, M1.81, M1.86.
Next: M1.88, M1.99.

## Execution Rule
The ranking layer must not manufacture positive recommendations. It may only rank candidates that already satisfy the positive-only qualification policy.
