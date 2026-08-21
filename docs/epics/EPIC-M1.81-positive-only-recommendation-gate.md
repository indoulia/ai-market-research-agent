# EPIC-M1.81 — Positive-Only Recommendation Gate & Abstention

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P0

## Objective
Ensure MRA publishes recommendations only when the evidence supports a positive investment opportunity, while preserving non-positive analysis internally for measurement and learning.

## Scope
- Define the positive recommendation contract.
- Permit only positive actionable outputs to the recommendation feed.
- Suppress HOLD, SELL, AVOID, CAUTIOUS, NEGATIVE and equivalent non-positive recommendation states from user recommendations.
- Allow internal no-recommendation/insufficient-evidence states for safety and learning, but do not present them as recommendations.
- Require minimum probability, score, trust and evidence-quality thresholds.
- Prevent weak positive-looking predictions from passing through due to a single metric.
- Preserve suppressed candidates internally for outcome measurement and model learning.
- Provide a positive recommendation ranking based on expected opportunity and trust.

## Acceptance Criteria
- User recommendation feeds contain only positive actionable opportunities.
- No negative/cautious recommendation is emitted as a recommendation.
- A candidate failing the positive gate is suppressed rather than converted into a negative recommendation.
- Suppression reasons remain auditable internally.
- Positive-only filtering does not contaminate training labels or outcome measurement.

## Dependency Chain
**Previous:** M1.75, M1.77, M1.79, M1.80.
**Next:** M1.84.

## Execution Rule
Positive-only is a presentation/recommendation policy, not a learning-data deletion policy. Negative outcomes and rejected candidates must remain available internally so the system can learn what not to recommend.
