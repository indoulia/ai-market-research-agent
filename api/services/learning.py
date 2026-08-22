"""Query services backing GET /api/v1/learning/{summary,history,experiments}
(EPIC-M3.9).

**Scope decision: which promotion registry is "the" one.** This codebase
has two generations of "compare a candidate model, then gate its
promotion": the older `app.model_promotion.ModelPromotion` (M1.31), which
`app.champion_challenger_shadow` (M1.123) *also* writes into for shadow
promotions/rollbacks, and a separate, later `app.safe_model_promotion.
ModelPromotionDecision` (M1.44/45) used by the parallel M1.39/M1.43/M1.44/
M1.45 "self-learning cycle" dataset-version chain. EPIC-M3.9's own
Acceptance Criteria says promotion/rejection states must "reconcile with
M1.123" -- that anchors this module on `ModelPromotion` specifically (the
one table M1.123's shadow-challenger flow and M1.31's evidence gate both
share), not `ModelPromotionDecision`. Mixing both registries into one
"current production model" answer would risk two different, disagreeing
notions of "current champion"; this module deliberately surfaces only the
M1.123-reconciled one. Same reasoning applies to `LearningCycle` (M1.32,
wired to `ModelPromotion`) vs. `SelfLearningCycle` (M1.45, wired to
`ModelPromotionDecision`) -- only `LearningCycle` is surfaced.

Every function here is read-only: no experiment is (re-)run, no promotion
evaluated, no rollback executed as a side effect of a GET (AC: "UI never
directly modifies production models"). Where a computed value would
require *running* something (e.g. `run_experiment_arm`), this module reads
only whatever has already been persisted and reports "no evidence yet"
rather than materializing new rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.champion_challenger_shadow import get_rollback_history
from app.continuous_learning import OUTCOME_RAN, get_learning_cycle_history
from app.discovery_effectiveness import VERDICT_WEAK
from app.feedback_learning_signals import compute_feedback_learning_signals
from app.model_promotion import DECISION_PROMOTED, DECISION_REJECTED, get_current_production_model_version, get_promotion_history
from app.models import Experiment, ExperimentArm, ExperimentResult, FeedbackDrivenExperiment, ShadowChallengerComparisonReport
from app.recommendation_experiments import EXPERIMENT_FRAMEWORK_VERSION, VERDICT_INSUFFICIENT_SAMPLE, VERDICT_READY, get_arm_results

from ..schemas.learning import (
    EXPERIMENT_STATUS_INSUFFICIENT_SAMPLE,
    EXPERIMENT_STATUS_PENDING,
    EXPERIMENT_STATUS_READY,
    HISTORY_TYPE_LEARNING_CYCLE,
    HISTORY_TYPE_PROMOTION,
    HISTORY_TYPE_REJECTION,
    HISTORY_TYPE_ROLLBACK,
    ChampionChallengerStatus,
    ExperimentCounts,
    LastLearningCycle,
    LatestRollback,
    LearningExperiment,
    LearningExperimentArm,
    LearningHistoryEntry,
    LearningSignalSummary,
    LearningSummary,
    PromotionCounts,
)

LEARNING_SUMMARY_VERSION = "LSI-001"

# "Recent learning signals"/"failure patterns discovered" are capped so the
# summary stays a compact overview -- the same posture `TrackingSummary` and
# `DiscoverySummary` already take (a bounded snapshot, not a full dump).
MAX_RECENT_SIGNALS = 10
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200

# EPIC-M3.13 — API Scope: "Pagination and bounded payloads". Experiments
# accumulate over the lifetime of the platform just like history events;
# this endpoint had no limit at all before this epic. Same bound as
# history since both are "most recent N" overviews, not full archives.
DEFAULT_EXPERIMENTS_LIMIT = 50
MAX_EXPERIMENTS_LIMIT = 200


def _latest_champion_challenger(session: Session) -> ShadowChallengerComparisonReport | None:
    return session.scalar(select(ShadowChallengerComparisonReport).order_by(ShadowChallengerComparisonReport.id.desc()).limit(1))


def get_learning_summary(session: Session) -> LearningSummary:
    cycles = get_learning_cycle_history(session)
    last_cycle = cycles[-1] if cycles else None

    promotions = get_promotion_history(session)
    promoted = sum(1 for p in promotions if p.decision == DECISION_PROMOTED)
    rejected = sum(1 for p in promotions if p.decision == DECISION_REJECTED)

    rollbacks = get_rollback_history(session)
    latest_rollback = rollbacks[-1] if rollbacks else None

    experiments = tuple(session.scalars(select(Experiment).order_by(Experiment.id.asc())).all())
    ready = insufficient = pending = 0
    for experiment in experiments:
        status = _experiment_status(session, experiment)
        if status == EXPERIMENT_STATUS_READY:
            ready += 1
        elif status == EXPERIMENT_STATUS_INSUFFICIENT_SAMPLE:
            insufficient += 1
        else:
            pending += 1

    feedback_report = compute_feedback_learning_signals(session)
    failure_signals = [s for s in feedback_report.signals if s.verdict == VERDICT_WEAK]
    recent_signals = sorted(
        feedback_report.signals,
        key=lambda s: (s.verdict != VERDICT_WEAK, -s.total_feedback_count),
    )[:MAX_RECENT_SIGNALS]

    latest_comparison = _latest_champion_challenger(session)

    return LearningSummary(
        asOf=_now(),
        currentModelVersion=get_current_production_model_version(session),
        lastCycle=(
            LastLearningCycle(
                id=last_cycle.id,
                startedAt=last_cycle.started_at,
                outcome=last_cycle.outcome,
                newOutcomesCount=last_cycle.new_outcomes_count,
                skipReason=last_cycle.skip_reason,
                modelPromotionId=last_cycle.model_promotion_id,
                cycleRuleVersion=last_cycle.cycle_rule_version,
            )
            if last_cycle is not None
            else None
        ),
        promotionCounts=PromotionCounts(promoted=promoted, rejected=rejected),
        rollbackCount=len(rollbacks),
        latestRollback=(
            LatestRollback(
                rolledBackModelVersion=latest_rollback.rolled_back_model_version,
                restoredModelVersion=latest_rollback.restored_model_version,
                decidedAt=latest_rollback.decided_at,
                rollbackRuleVersion=latest_rollback.rollback_rule_version,
            )
            if latest_rollback is not None
            else None
        ),
        experimentCounts=ExperimentCounts(total=len(experiments), ready=ready, insufficientSample=insufficient, pending=pending),
        failurePatternCount=len(failure_signals),
        recentSignals=[
            LearningSignalSummary(
                category=s.category,
                reasonCode=s.reason_code,
                verdict=s.verdict,
                totalFeedbackCount=s.total_feedback_count,
                distinctPredictionCount=s.distinct_prediction_count,
                distinctUserCount=s.distinct_user_count,
                repeatedPredictionCount=s.repeated_prediction_count,
                evaluatedCount=s.evaluated_count,
                successRate=s.success_rate,
            )
            for s in recent_signals
        ],
        championChallenger=(
            ChampionChallengerStatus(
                challengerModelVersion=latest_comparison.challenger_model_version,
                championModelVersion=latest_comparison.champion_model_version,
                verdict=latest_comparison.verdict,
                sampleCount=latest_comparison.sample_count,
                championSuccessRate=latest_comparison.champion_success_rate,
                challengerSuccessRate=latest_comparison.challenger_success_rate,
                successRateDelta=latest_comparison.success_rate_delta,
                computedAt=latest_comparison.computed_at,
                comparisonRuleVersion=latest_comparison.comparison_rule_version,
            )
            if latest_comparison is not None
            else None
        ),
        methodologyVersion=LEARNING_SUMMARY_VERSION,
    )


def _now():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Event:
    id: str
    type: str
    created_at: object
    status: str
    evidence_count: int | None
    methodology_version: str
    impact: str
    model_version: str | None
    decision_reason: str | None


def _cycle_events(session: Session) -> list[_Event]:
    events = []
    for cycle in get_learning_cycle_history(session):
        if cycle.outcome == OUTCOME_RAN:
            impact = f"Learning cycle evaluated {cycle.new_outcomes_count} new outcome(s) and re-ran the promotion gate."
        else:
            impact = f"Learning cycle skipped: {cycle.skip_reason or 'insufficient new evidence'} ({cycle.new_outcomes_count} new outcome(s))."
        events.append(
            _Event(
                id=f"cycle:{cycle.id}",
                type=HISTORY_TYPE_LEARNING_CYCLE,
                created_at=cycle.created_at,
                status=cycle.outcome,
                evidence_count=cycle.new_outcomes_count,
                methodology_version=cycle.cycle_rule_version,
                impact=impact,
                model_version=None,
                decision_reason=cycle.skip_reason,
            )
        )
    return events


def _promotion_events(session: Session) -> list[_Event]:
    events = []
    for promotion in get_promotion_history(session):
        is_promoted = promotion.decision == DECISION_PROMOTED
        impact = (
            f"Model '{promotion.candidate_model_version}' promoted to production"
            + (f" over baseline '{promotion.baseline_model_version}'" if promotion.baseline_model_version else "")
            + "."
            if is_promoted
            else f"Model '{promotion.candidate_model_version}' rejected ({promotion.decision_reason})."
        )
        events.append(
            _Event(
                id=f"promotion:{promotion.id}",
                type=HISTORY_TYPE_PROMOTION if is_promoted else HISTORY_TYPE_REJECTION,
                created_at=promotion.created_at,
                status=promotion.decision,
                evidence_count=None,
                methodology_version=promotion.promotion_rule_version,
                impact=impact,
                model_version=promotion.candidate_model_version,
                decision_reason=promotion.decision_reason,
            )
        )
    return events


def _rollback_events(session: Session) -> list[_Event]:
    events = []
    for rollback in get_rollback_history(session):
        events.append(
            _Event(
                id=f"rollback:{rollback.id}",
                type=HISTORY_TYPE_ROLLBACK,
                created_at=rollback.created_at,
                status="ROLLED_BACK",
                evidence_count=None,
                methodology_version=rollback.rollback_rule_version,
                impact=f"Rolled back from '{rollback.rolled_back_model_version}' to last known-good '{rollback.restored_model_version}'.",
                model_version=rollback.restored_model_version,
                decision_reason="ROLLBACK",
            )
        )
    return events


def get_learning_history(session: Session, *, limit: int = DEFAULT_HISTORY_LIMIT) -> list[LearningHistoryEntry]:
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    events = _cycle_events(session) + _promotion_events(session) + _rollback_events(session)
    events.sort(key=lambda e: (e.created_at, e.id), reverse=True)
    return [
        LearningHistoryEntry(
            id=e.id,
            type=e.type,
            createdAt=e.created_at,
            status=e.status,
            evidenceCount=e.evidence_count,
            methodologyVersion=e.methodology_version,
            impact=e.impact,
            modelVersion=e.model_version,
            decisionReason=e.decision_reason,
        )
        for e in events[:limit]
    ]


def _status_from_verdicts(latest_verdicts: list[str]) -> str:
    if not latest_verdicts:
        return EXPERIMENT_STATUS_PENDING
    if any(v == VERDICT_READY for v in latest_verdicts):
        return EXPERIMENT_STATUS_READY
    if any(v == VERDICT_INSUFFICIENT_SAMPLE for v in latest_verdicts):
        return EXPERIMENT_STATUS_INSUFFICIENT_SAMPLE
    return EXPERIMENT_STATUS_PENDING


def _experiment_status(session: Session, experiment: Experiment) -> str:
    arms = session.scalars(select(ExperimentArm).where(ExperimentArm.experiment_id == experiment.id)).all()
    latest_verdicts = []
    for arm in arms:
        results = get_arm_results(session, arm.id)
        if results:
            latest_verdicts.append(results[-1].verdict)
    return _status_from_verdicts(latest_verdicts)


def list_learning_experiments(session: Session, *, limit: int = DEFAULT_EXPERIMENTS_LIMIT) -> list[LearningExperiment]:
    """Never runs `run_experiment_arm`/`compare_experiment` (both mutating,
    result-persisting operations) as a side effect of this read-only GET --
    only already-persisted `ExperimentResult` rows are reported. An
    experiment with arms but no results yet is `PENDING`, not fabricated as
    `READY`/`INSUFFICIENT_SAMPLE`."""
    limit = max(1, min(limit, MAX_EXPERIMENTS_LIMIT))
    experiments = tuple(
        session.scalars(select(Experiment).order_by(Experiment.id.desc()).limit(limit)).all()
    )

    out: list[LearningExperiment] = []
    for experiment in experiments:
        arms = session.scalars(
            select(ExperimentArm).where(ExperimentArm.experiment_id == experiment.id).order_by(ExperimentArm.id.asc())
        ).all()

        arm_dtos = []
        latest_verdicts: list[str] = []
        best_arm_name: str | None = None
        best_accuracy = None
        for arm in arms:
            results = get_arm_results(session, arm.id)
            latest: ExperimentResult | None = results[-1] if results else None
            if latest is not None:
                latest_verdicts.append(latest.verdict)
            arm_dtos.append(
                LearningExperimentArm(
                    armName=arm.arm_name,
                    modelVersion=arm.model_version,
                    windowLabel=arm.window_label,
                    horizonDaysFilter=arm.horizon_days_filter,
                    sampleCount=latest.sample_count if latest is not None else None,
                    accuracy=latest.accuracy if latest is not None else None,
                    verdict=latest.verdict if latest is not None else None,
                )
            )
            if latest is not None and latest.verdict == VERDICT_READY and latest.accuracy is not None:
                if best_accuracy is None or latest.accuracy > best_accuracy:
                    best_accuracy = latest.accuracy
                    best_arm_name = arm.arm_name

        feedback_link = session.scalar(
            select(FeedbackDrivenExperiment).where(FeedbackDrivenExperiment.experiment_id == experiment.id)
        )

        out.append(
            LearningExperiment(
                id=experiment.id,
                name=experiment.name,
                hypothesis=experiment.hypothesis,
                status=_status_from_verdicts(latest_verdicts),
                createdAt=experiment.created_at,
                arms=arm_dtos,
                bestArmName=best_arm_name,
                feedbackDriven=feedback_link is not None,
                feedbackCategory=feedback_link.feedback_category if feedback_link is not None else None,
                feedbackReasonCode=feedback_link.feedback_reason_code if feedback_link is not None else None,
                methodologyVersion=EXPERIMENT_FRAMEWORK_VERSION,
            )
        )
    return out
