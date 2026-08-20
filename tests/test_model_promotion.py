from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.candidate_model_evaluation import (
    CANDIDATE_MODEL_EVALUATION_VERSION,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_REGRESSED,
    VERDICT_VALIDATED,
    CandidateModelComparisonReport,
    SegmentBucketMetric,
    WindowEvaluation,
)
from app.db import Base
from app.model_promotion import (
    DECISION_PROMOTED,
    DECISION_REJECTED,
    PROMOTION_RULE_VERSION,
    REASON_CRITICAL_HORIZON_REGRESSION,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_REGRESSED,
    REASON_VALIDATED,
    ModelPromotionImmutableError,
    evaluate_promotion,
    get_current_production_model_version,
    get_promotion_history,
)
from app.out_of_sample_validation import EvaluationWindow

DECIDED_AT = datetime(2026, 8, 21, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _window(label):
    return EvaluationWindow(label=label, start=None, end=None)


def _window_eval(*, success_rate, horizon_metrics=(), insufficient=()):
    return WindowEvaluation(
        version=CANDIDATE_MODEL_EVALUATION_VERSION,
        window=_window("w"),
        evaluated_count=20,
        success_count=int(success_rate * 20) if success_rate is not None else 0,
        failure_count=20 - (int(success_rate * 20) if success_rate is not None else 0),
        success_rate=success_rate,
        average_actual_return=Decimal("0.02"),
        average_predicted_return=Decimal("0.05"),
        mean_absolute_calibration_error=Decimal("0.1"),
        by_horizon=horizon_metrics,
        by_sector=(),
        by_market_cap_bucket=(),
        by_discovery_source=(),
        by_regime=(),
        insufficient_sample_dimensions=insufficient,
    )


def _comparison(*, verdict, delta, baseline_eval=None, candidate_eval=None):
    return CandidateModelComparisonReport(
        version=CANDIDATE_MODEL_EVALUATION_VERSION,
        baseline=baseline_eval or _window_eval(success_rate=Decimal("0.6")),
        candidate=candidate_eval or _window_eval(success_rate=Decimal("0.6")),
        success_rate_delta=delta,
        verdict=verdict,
    )


def test_validated_comparison_is_promoted(session):
    comparison = _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"))

    promotion = evaluate_promotion(
        session, comparison, candidate_model_version="v2", baseline_model_version="v1",
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    assert promotion.decision == DECISION_PROMOTED
    assert promotion.decision_reason == REASON_VALIDATED
    assert promotion.promotion_rule_version == PROMOTION_RULE_VERSION


def test_regressed_comparison_is_rejected(session):
    comparison = _comparison(verdict=VERDICT_REGRESSED, delta=Decimal("-0.5"))

    promotion = evaluate_promotion(
        session, comparison, candidate_model_version="v2", baseline_model_version="v1",
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    assert promotion.decision == DECISION_REJECTED
    assert promotion.decision_reason == REASON_REGRESSED


def test_insufficient_evidence_comparison_is_rejected(session):
    comparison = _comparison(verdict=VERDICT_INSUFFICIENT_EVIDENCE, delta=None)

    promotion = evaluate_promotion(
        session, comparison, candidate_model_version="v2", baseline_model_version="v1",
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    assert promotion.decision == DECISION_REJECTED
    assert promotion.decision_reason == REASON_INSUFFICIENT_EVIDENCE


def test_critical_horizon_regression_blocks_promotion_despite_validated_overall(session):
    baseline_eval = _window_eval(
        success_rate=Decimal("0.6"),
        horizon_metrics=(SegmentBucketMetric("horizon", "1", 25, 20, Decimal("0.8")),),
    )
    candidate_eval = _window_eval(
        success_rate=Decimal("0.6"),
        # horizon 1 regressed hard even though the overall rate held
        horizon_metrics=(SegmentBucketMetric("horizon", "1", 25, 5, Decimal("0.2")),),
    )
    comparison = _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"), baseline_eval=baseline_eval, candidate_eval=candidate_eval)

    promotion = evaluate_promotion(
        session, comparison, candidate_model_version="v2", baseline_model_version="v1",
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    assert promotion.decision == DECISION_REJECTED
    assert promotion.decision_reason == REASON_CRITICAL_HORIZON_REGRESSION


def test_horizon_regression_ignored_when_either_side_has_insufficient_sample(session):
    baseline_eval = _window_eval(
        success_rate=Decimal("0.6"),
        horizon_metrics=(SegmentBucketMetric("horizon", "1", 3, 2, Decimal("0.67")),),
        insufficient=("horizon:1",),
    )
    candidate_eval = _window_eval(
        success_rate=Decimal("0.6"),
        horizon_metrics=(SegmentBucketMetric("horizon", "1", 3, 0, Decimal("0.0")),),
        insufficient=("horizon:1",),
    )
    comparison = _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"), baseline_eval=baseline_eval, candidate_eval=candidate_eval)

    promotion = evaluate_promotion(
        session, comparison, candidate_model_version="v2", baseline_model_version="v1",
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    assert promotion.decision == DECISION_PROMOTED


def test_promotion_is_immutable_after_creation(session):
    comparison = _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"))
    promotion = evaluate_promotion(
        session, comparison, candidate_model_version="v2", baseline_model_version="v1",
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    promotion.decision = DECISION_REJECTED
    with pytest.raises(ModelPromotionImmutableError, match="decision"):
        session.flush()
    session.rollback()


def test_current_production_model_tracks_only_the_latest_promotion(session):
    assert get_current_production_model_version(session) is None

    evaluate_promotion(
        session, _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0")),
        candidate_model_version="v2", baseline_model_version="v1", approver="SYSTEM", decided_at=DECIDED_AT,
    )
    assert get_current_production_model_version(session) == "v2"

    # a later rejected candidate must not become "current"
    evaluate_promotion(
        session, _comparison(verdict=VERDICT_REGRESSED, delta=Decimal("-0.5")),
        candidate_model_version="v3", baseline_model_version="v2", approver="SYSTEM", decided_at=DECIDED_AT,
    )
    assert get_current_production_model_version(session) == "v2"

    evaluate_promotion(
        session, _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0")),
        candidate_model_version="v4", baseline_model_version="v2", approver="SYSTEM", decided_at=DECIDED_AT,
    )
    assert get_current_production_model_version(session) == "v4"


def test_promotion_history_preserves_every_decision_including_rejected_ones(session):
    evaluate_promotion(
        session, _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0")),
        candidate_model_version="v2", baseline_model_version="v1", approver="SYSTEM", decided_at=DECIDED_AT,
    )
    evaluate_promotion(
        session, _comparison(verdict=VERDICT_REGRESSED, delta=Decimal("-0.5")),
        candidate_model_version="v3", baseline_model_version="v2", approver="SYSTEM", decided_at=DECIDED_AT,
    )

    history = get_promotion_history(session)
    assert [h.candidate_model_version for h in history] == ["v2", "v3"]
    assert [h.decision for h in history] == [DECISION_PROMOTED, DECISION_REJECTED]

    v3_only = get_promotion_history(session, candidate_model_version="v3")
    assert len(v3_only) == 1
    assert v3_only[0].decision_reason == REASON_REGRESSED
