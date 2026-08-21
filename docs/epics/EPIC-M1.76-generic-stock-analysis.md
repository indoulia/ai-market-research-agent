# EPIC-M1.76 — Generic Stock Analysis

**Status:** READY_FOR_APPROVAL
**Execution Status:** BLOCKED_PENDING_APPROVAL
**Priority:** P0

## Objective
Allow a user to request a complete current analysis for any supported stock without requiring that stock to already be in the daily recommendation set.

## Scope
- Accept a supported security identifier.
- Fetch or reuse fresh market, fundamental, news and event evidence.
- Apply the current market regime and relevant historical context.
- Produce the existing score, confidence, target, stop loss, upside/downside and horizon outputs.
- Respect explicit user preferences from M1.46 and learned preferences from M1.70 when available.
- Clearly distinguish recommendation, analysis-only, insufficient-evidence and rejected states.
- Show evidence provenance, freshness and conflicts.
- Preserve an immutable analysis/decision trace.

## Non-goals
- Bypassing qualification rules.
- Creating a recommendation solely because a user asks about a stock.
- Automatic trading.

## Acceptance Criteria
- Any supported stock can be analyzed on demand.
- The analysis uses the same authoritative recommendation contracts as scheduled discovery.
- Evidence categories and unavailable data are visible.
- Target/SL/horizon/score/confidence are consistent with existing engines.
- Results are auditable and point-in-time safe.

## Dependency Chain
**Previous:** M1.75 Short-Horizon Probability & Outcome Distribution + M1.72/M1.73/M1.74 + M1.46/M1.70.
**Next:** Future roadmap review.

## Execution Rule
On-demand analysis must not create a second, conflicting scoring path. Reuse the same authoritative engines used by normal recommendations.
