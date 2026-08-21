# EPIC-M1.78 — Daily Market & Prediction Snapshot History

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P0

## Objective
Capture the day-by-day market, evidence, model-input, prediction and trust state required to reconstruct exactly what MRA knew and predicted at each point in time.

## Scope
- Store immutable daily market snapshots for supported securities.
- Capture point-in-time features, evidence references, model/version, prediction, target, stop loss, horizon, score, probability, confidence and trust score.
- Capture data freshness and source metadata.
- Support intraday updates where configured while retaining end-of-day canonical snapshots.
- Preserve every prediction revision rather than overwriting the previous prediction.
- Support complete historical reconstruction for any recommendation.
- Add retention, partitioning and query-performance controls.

## Acceptance Criteria
- Every prediction has a reconstructable as-of snapshot.
- A new day's data never overwrites prior prediction history.
- Prediction revisions are versioned and linked.
- Historical snapshots are immutable.
- The system can reconstruct what data and model produced a past prediction.
- Retention does not silently delete active learning evidence.

## Dependency Chain
**Previous:** M1.20, M1.24, M1.55, M1.66.
**Next:** M1.79, M1.80, M1.81, M1.84.

## Execution Rule
History is append-only evidence. Current state may be updated, but historical snapshots must remain immutable.
