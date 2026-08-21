"""DTOs for GET /api/v1/learning/{summary,history,experiments} (EPIC-M3.9).

Read-only projections over already-merged, already-tested learning-loop
tables -- nothing about promotion, rollback, experiment or feedback-signal
logic is recomputed here:
  - `app.model_promotion.ModelPromotion` (M1.31, extended by M1.123's shadow
    challenger flow) is the single promotion/rejection registry this EPIC's
    AC ("promotion/rejection states reconcile with M1.123") anchors on --
    `app.model_promotion_decision`/`ModelPromotionDecision`, the parallel
    registry the older M1.39/M1.43/M1.44/M1.45 dataset-version chain writes,
    is deliberately not surfaced here (see `api/services/learning.py`'s
    module docstring for the full reasoning).
  - `app.continuous_learning.LearningCycle` (M1.32) is the watermark-gated
    audit trail of when a learning cycle ran/was skipped and which
    promotion decision (if any) it produced.
  - `app.champion_challenger_shadow.ShadowChallengerComparisonReport`/
    `ChampionRollback` (M1.123) supply champion/challenger comparison
    evidence and rollback history.
  - `app.recommendation_experiments.Experiment`/`ExperimentArm`/
    `ExperimentResult` (M1.68) plus `app.feedback_experiment_pipeline.
    FeedbackDrivenExperiment` (M1.69) supply candidate experiments.
  - `app.feedback_learning_signals.compute_feedback_learning_signals`
    (M1.53) supplies "recent learning signals" / "failure patterns
    discovered" -- a `VERDICT_WEAK` signal is a discovered failure pattern.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

# `LearningHistoryEntry.type` vocabulary.
HISTORY_TYPE_LEARNING_CYCLE = "LEARNING_CYCLE"
HISTORY_TYPE_PROMOTION = "PROMOTION"
HISTORY_TYPE_REJECTION = "REJECTION"
HISTORY_TYPE_ROLLBACK = "ROLLBACK"

# `LearningExperiment.status` vocabulary.
EXPERIMENT_STATUS_PENDING = "PENDING"
EXPERIMENT_STATUS_READY = "READY"
EXPERIMENT_STATUS_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class LastLearningCycle(BaseModel):
    id: int
    startedAt: datetime
    outcome: str
    newOutcomesCount: int
    skipReason: str | None
    modelPromotionId: int | None
    cycleRuleVersion: str


class PromotionCounts(BaseModel):
    promoted: int
    rejected: int


class ExperimentCounts(BaseModel):
    total: int
    ready: int
    insufficientSample: int
    pending: int


class LearningSignalSummary(BaseModel):
    """One (category, reason_code) feedback pattern, reprojected verbatim
    from `app.feedback_learning_signals.FeedbackSignal` -- camelCase DTO
    only, no new scoring/verdict logic."""

    category: str
    reasonCode: str
    verdict: str
    totalFeedbackCount: int
    distinctPredictionCount: int
    distinctUserCount: int
    repeatedPredictionCount: int
    evaluatedCount: int
    successRate: Decimal | None


class ChampionChallengerStatus(BaseModel):
    challengerModelVersion: str
    championModelVersion: str
    verdict: str
    sampleCount: int
    championSuccessRate: Decimal | None
    challengerSuccessRate: Decimal | None
    successRateDelta: Decimal | None
    computedAt: datetime
    comparisonRuleVersion: str


class LatestRollback(BaseModel):
    rolledBackModelVersion: str
    restoredModelVersion: str
    decidedAt: datetime
    rollbackRuleVersion: str


class LearningSummary(BaseModel):
    asOf: datetime
    currentModelVersion: str | None
    lastCycle: LastLearningCycle | None
    promotionCounts: PromotionCounts
    rollbackCount: int
    latestRollback: LatestRollback | None
    experimentCounts: ExperimentCounts
    failurePatternCount: int
    recentSignals: list[LearningSignalSummary]
    championChallenger: ChampionChallengerStatus | None
    methodologyVersion: str


class LearningHistoryEntry(BaseModel):
    """One event in the unified learning-history timeline. `id` is a
    composite `"<source-table>:<row id>"` string (not a single row's own
    primary key) since this feed merges rows from several distinct,
    independently-keyed tables -- never a fabricated shared sequence."""

    id: str
    type: str
    createdAt: datetime
    status: str
    evidenceCount: int | None
    methodologyVersion: str
    impact: str
    modelVersion: str | None
    decisionReason: str | None


class LearningExperimentArm(BaseModel):
    armName: str
    modelVersion: str
    windowLabel: str
    horizonDaysFilter: int | None
    sampleCount: int | None
    accuracy: Decimal | None
    verdict: str | None


class LearningExperiment(BaseModel):
    id: int
    name: str
    hypothesis: str
    status: str
    createdAt: datetime
    arms: list[LearningExperimentArm]
    bestArmName: str | None
    feedbackDriven: bool
    feedbackCategory: str | None
    feedbackReasonCode: str | None
    methodologyVersion: str
