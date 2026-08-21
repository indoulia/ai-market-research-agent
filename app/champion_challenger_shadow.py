"""EPIC-M1.123: let a challenger model prove itself against the production
champion on the exact same real-world inputs and outcomes, before it can
ever affect a user-facing recommendation -- and let a regressed champion
be rolled back to the last known-good one deterministically.

**Why this needs a new mechanism, not just M1.30/M1.43's existing
comparison reports**: `compare_candidate_model` (M1.43) and
`compare_disjoint_windows` (M1.30) compare two *disjoint time windows* --
"the model active during period A" vs "the model active during period
B." That is a real-world A/B-over-time comparison, never a genuine
shadow run: nothing in this platform lets two models see the *same*
point-in-time input and the *same* eventual real outcome simultaneously.

**Honest platform limitation**: this repo has no live model-serving
component of its own -- `Prediction.model_version` records which
already-trained, externally-scored model produced a recommendation, but
nothing here ever *invokes* a model. A true "run the challenger inside
this codebase in shadow mode" is therefore not implementable without
inventing a fake inference step. Instead, `record_shadow_challenger_run`
takes an externally-computed challenger score (the same score an offline
batch-scoring job would produce, exactly as `Prediction.predicted_
probability` already is for the champion) and records it *tied to the
champion's own already-published prediction* for the same stock/as-of/
horizon -- so the champion's real, eventual `PredictionOutcome` is
directly reusable as the challenger's ground truth too, with zero
extra machinery.

**A challenger cannot affect production recommendations (AC)**: this
module has no import of `app.recommendations`, `app.discovery`, or any
function that writes `Prediction`/`RecommendationGeneration`/
`ScanCandidate` -- there is no code path from a `ShadowChallengerAssessment`
to a real recommendation, by construction, not by convention.

**Champion and challenger consume equivalent eligible evidence (AC)**:
guaranteed structurally -- the challenger's score is recorded against
the champion's own `Prediction` row, so both are compared using the
exact same `as_of_timestamp`, `stock_id`, and eventual `PredictionOutcome`.
There is no separate challenger-side evidence snapshot to drift from the
champion's.

**Promotion reuses M1.31's existing mechanism (scope: "extend the same
mechanism...")**: `evaluate_shadow_promotion` writes into the very same
`ModelPromotion` log `app.model_promotion` already owns, using its same
`DECISION_PROMOTED`/`DECISION_REJECTED` vocabulary and the same
`REGRESSION_MARGIN` -- "current production model" and "rollback to the
previous one" both continue to fall out of that one append-only log,
never a second parallel promotion registry.

**Support immediate rollback (AC)**: `execute_rollback` is this EPIC's
own genuinely new contribution -- `app.model_regression_detection`
(M1.67) already computes `rollback_triggered` but, by its own docstring,
has no write path to actually perform one. `execute_rollback` finds the
last known-good `PROMOTED` version from `app.model_promotion`'s own
history and writes a new `PROMOTED` row restoring it, plus a
`ChampionRollback` audit row linking the trigger, the restored version,
and the resulting promotion -- idempotent by
`(rolled_back_model_version, restored_model_version)` so a repeated
trigger for the same regression never rolls back twice.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .model_promotion import (
    DECISION_PROMOTED,
    DECISION_REJECTED,
    PROMOTION_RULE_VERSION,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_REGRESSED,
    REASON_VALIDATED,
    get_promotion_history,
)
from .candidate_model_evaluation import REGRESSION_MARGIN
from .models import (
    ChampionRollback,
    ModelPromotion,
    ModelRegressionCheck,
    Prediction,
    PredictionOutcome,
    ShadowChallengerAssessment,
    ShadowChallengerComparisonReport,
)
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

SHADOW_RULE_VERSION = "SCS-001"
COMPARISON_RULE_VERSION = "SCC-001"
ROLLBACK_RULE_VERSION = "CRB-001"

REASON_ROLLBACK = "ROLLBACK"


class NoKnownGoodChampionError(RuntimeError):
    """Raised when a rollback is requested but the promotion log has no
    prior `PROMOTED` version to restore -- never fabricates a target."""


def record_shadow_challenger_run(
    session: Session,
    champion_prediction: Prediction,
    *,
    challenger_model_version: str,
    challenger_predicted_probability: Decimal,
    challenger_confidence: Decimal | None = None,
    recorded_at: datetime,
) -> ShadowChallengerAssessment:
    """Idempotent by `(champion_prediction_id, challenger_model_version)`.
    Never writes to `Prediction` or any recommendation-facing table --
    structurally cannot affect production (AC)."""
    existing = session.scalar(
        select(ShadowChallengerAssessment).where(
            ShadowChallengerAssessment.champion_prediction_id == champion_prediction.id,
            ShadowChallengerAssessment.challenger_model_version == challenger_model_version,
        )
    )
    if existing is not None:
        return existing

    assessment = ShadowChallengerAssessment(
        champion_prediction_id=champion_prediction.id,
        champion_model_version=champion_prediction.model_version,
        challenger_model_version=challenger_model_version,
        challenger_predicted_probability=challenger_predicted_probability,
        challenger_confidence=challenger_confidence,
        recorded_at=recorded_at,
        shadow_rule_version=SHADOW_RULE_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_shadow_assessment_history(session: Session, champion_prediction_id: int) -> tuple[ShadowChallengerAssessment, ...]:
    return tuple(
        session.scalars(
            select(ShadowChallengerAssessment)
            .where(ShadowChallengerAssessment.champion_prediction_id == champion_prediction_id)
            .order_by(ShadowChallengerAssessment.id.asc())
        ).all()
    )


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def compare_shadow_challenger_performance(
    session: Session,
    *,
    challenger_model_version: str,
    champion_model_version: str,
    window: EvaluationWindow,
    computed_at: datetime,
) -> ShadowChallengerComparisonReport:
    """Always computes and persists a fresh, independent report -- never
    mutates a prior one (AC: "every promotion/rollback is reproducible
    and auditable"), mirroring M1.99's own effectiveness-report posture.
    Champion and challenger are scored against the identical, already-
    resolved `PredictionOutcome` for each shared point-in-time input."""
    rows = session.execute(
        select(Prediction, PredictionOutcome, ShadowChallengerAssessment)
        .join(ShadowChallengerAssessment, ShadowChallengerAssessment.champion_prediction_id == Prediction.id)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(
            ShadowChallengerAssessment.challenger_model_version == challenger_model_version,
            Prediction.model_version == champion_model_version,
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
    ).all()

    if window.start is not None:
        rows = [r for r in rows if r[0].as_of_timestamp >= window.start]
    if window.end is not None:
        rows = [r for r in rows if r[0].as_of_timestamp <= window.end]

    sample_count = len(rows)
    champion_calibration_errors: list[Decimal] = []
    challenger_calibration_errors: list[Decimal] = []
    champion_success_flags: list[Decimal] = []
    challenger_success_flags: list[Decimal] = []
    by_horizon_groups: dict[int, list[tuple[Decimal, Decimal]]] = {}

    for prediction, outcome, shadow in rows:
        actual = Decimal("1") if outcome.outcome == "SUCCESS" else Decimal("0")
        champion_calibration_errors.append(abs(prediction.predicted_probability - actual))
        challenger_calibration_errors.append(abs(shadow.challenger_predicted_probability - actual))

        champion_success = Decimal("1") if outcome.outcome == "SUCCESS" else Decimal("0")
        challenger_call = Decimal("1") if shadow.challenger_predicted_probability >= Decimal("0.5") else Decimal("0")
        challenger_success = Decimal("1") if challenger_call == actual else Decimal("0")
        champion_success_flags.append(champion_success)
        challenger_success_flags.append(challenger_success)

        by_horizon_groups.setdefault(prediction.horizon_days, []).append((champion_success, challenger_success))

    champion_success_rate = _mean(champion_success_flags)
    challenger_success_rate = _mean(challenger_success_flags)
    success_rate_delta = (
        challenger_success_rate - champion_success_rate
        if champion_success_rate is not None and challenger_success_rate is not None
        else None
    )

    by_horizon = [
        {
            "horizon_days": horizon_days,
            "sample_count": len(pairs),
            "champion_success_rate": str(_mean([p[0] for p in pairs])),
            "challenger_success_rate": str(_mean([p[1] for p in pairs])),
        }
        for horizon_days, pairs in sorted(by_horizon_groups.items())
    ]

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        verdict = REASON_INSUFFICIENT_EVIDENCE
    elif success_rate_delta is not None and success_rate_delta <= -REGRESSION_MARGIN:
        verdict = REASON_REGRESSED
    else:
        verdict = REASON_VALIDATED

    report = ShadowChallengerComparisonReport(
        challenger_model_version=challenger_model_version,
        champion_model_version=champion_model_version,
        window_label=window.label,
        sample_count=sample_count,
        champion_success_rate=champion_success_rate,
        challenger_success_rate=challenger_success_rate,
        success_rate_delta=success_rate_delta,
        champion_calibration_error=_mean(champion_calibration_errors),
        challenger_calibration_error=_mean(challenger_calibration_errors),
        by_horizon=by_horizon,
        verdict=verdict,
        computed_at=computed_at,
        comparison_rule_version=COMPARISON_RULE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_comparison_report_history(session: Session, challenger_model_version: str) -> tuple[ShadowChallengerComparisonReport, ...]:
    return tuple(
        session.scalars(
            select(ShadowChallengerComparisonReport)
            .where(ShadowChallengerComparisonReport.challenger_model_version == challenger_model_version)
            .order_by(ShadowChallengerComparisonReport.id.asc())
        ).all()
    )


def evaluate_shadow_promotion(
    session: Session,
    comparison: ShadowChallengerComparisonReport,
    *,
    approver: str,
    decided_at: datetime,
) -> ModelPromotion:
    """Writes into `app.model_promotion`'s own append-only log (scope:
    "extend the same mechanism to...candidates where appropriate") --
    never a second, parallel promotion registry. Deterministic from
    `comparison` alone (AC: "promotion decision is reproducible from
    stored evidence"): the same report always yields the same decision."""
    if comparison.verdict == REASON_INSUFFICIENT_EVIDENCE:
        decision, reason = DECISION_REJECTED, REASON_INSUFFICIENT_EVIDENCE
    elif comparison.verdict == REASON_REGRESSED:
        decision, reason = DECISION_REJECTED, REASON_REGRESSED
    else:
        decision, reason = DECISION_PROMOTED, REASON_VALIDATED

    promotion = ModelPromotion(
        candidate_model_version=comparison.challenger_model_version,
        baseline_model_version=comparison.champion_model_version,
        evidence_report_version=comparison.comparison_rule_version,
        success_rate_delta=comparison.success_rate_delta,
        decision=decision,
        decision_reason=reason,
        decided_at=decided_at,
        approver=approver,
        promotion_rule_version=PROMOTION_RULE_VERSION,
    )
    session.add(promotion)
    session.commit()
    session.refresh(promotion)
    return promotion


def _last_known_good_before(promotion_history: tuple[ModelPromotion, ...], regressed_model_version: str) -> str | None:
    promoted = [p for p in promotion_history if p.decision == DECISION_PROMOTED]
    for index in range(len(promoted) - 1, -1, -1):
        if promoted[index].candidate_model_version == regressed_model_version and index > 0:
            return promoted[index - 1].candidate_model_version
    return None


def execute_rollback(
    session: Session,
    *,
    regressed_model_version: str,
    decided_at: datetime,
    approver: str,
    triggering_check: ModelRegressionCheck | None = None,
) -> ChampionRollback:
    """Finds the last known-good `PROMOTED` version preceding
    `regressed_model_version` in `app.model_promotion`'s own history and
    writes a new `PROMOTED` row restoring it, plus this audit record.
    Idempotent by `(rolled_back_model_version, restored_model_version)`
    -- a repeated trigger for the same regression never rolls back
    twice. Raises `NoKnownGoodChampionError` rather than fabricating a
    target when there is nothing to roll back to."""
    history = get_promotion_history(session)
    restored_model_version = _last_known_good_before(history, regressed_model_version)
    if restored_model_version is None:
        raise NoKnownGoodChampionError(
            f"no known-good promoted version exists before {regressed_model_version!r} to roll back to"
        )

    existing = session.scalar(
        select(ChampionRollback).where(
            ChampionRollback.rolled_back_model_version == regressed_model_version,
            ChampionRollback.restored_model_version == restored_model_version,
        )
    )
    if existing is not None:
        return existing

    promotion = ModelPromotion(
        candidate_model_version=restored_model_version,
        baseline_model_version=regressed_model_version,
        evidence_report_version=(triggering_check.detection_rule_version if triggering_check is not None else ROLLBACK_RULE_VERSION),
        success_rate_delta=None,
        decision=DECISION_PROMOTED,
        decision_reason=REASON_ROLLBACK,
        decided_at=decided_at,
        approver=approver,
        promotion_rule_version=PROMOTION_RULE_VERSION,
    )
    session.add(promotion)
    session.flush()

    rollback = ChampionRollback(
        rolled_back_model_version=regressed_model_version,
        restored_model_version=restored_model_version,
        triggering_model_regression_check_id=(triggering_check.id if triggering_check is not None else None),
        resulting_model_promotion_id=promotion.id,
        decided_at=decided_at,
        approver=approver,
        rollback_rule_version=ROLLBACK_RULE_VERSION,
    )
    session.add(rollback)
    session.commit()
    session.refresh(rollback)
    return rollback


def get_rollback_history(session: Session) -> tuple[ChampionRollback, ...]:
    return tuple(session.scalars(select(ChampionRollback).order_by(ChampionRollback.id.asc())).all())
