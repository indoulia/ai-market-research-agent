from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.candidate_model_comparison import (
    CANDIDATE_MODEL_COMPARISON_VERSION,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_REGRESSED,
    VERDICT_VALIDATED,
    CandidateModelComparisonReport,
    ModelEvaluation,
    ModelSegmentMetric,
)
from app.db import Base
from app.safe_model_promotion import (
    DECISION_PROMOTED,
    DECISION_REJECTED,
    PROMOTION_RULE_VERSION,
    REASON_CRITICAL_SEGMENT_REGRESSION,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_REGRESSED,
    REASON_VALIDATED,
    ModelPromotionDecisionImmutableError,
    evaluate_promotion,
    get_active_model,
    get_promotion_history,
)

DECIDED_AT = datetime(2026, 8, 21, tzinfo=timezone.utc)
DATASET_VERSION = "HLD-001"


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


def _evaluation(*, model_name, mae, horizon_metrics=(), insufficient=()):
    return ModelEvaluation(
        model_name=model_name,
        evaluated_count=20,
        observed_success_rate=Decimal("0.6"),
        average_predicted_probability=Decimal("0.6"),
        average_realized_return=Decimal("0.02"),
        mean_absolute_calibration_error=mae,
        by_horizon=horizon_metrics,
        by_sector=(),
        by_market_cap_bucket=(),
        by_discovery_source=(),
        by_regime=(),
        insufficient_sample_dimensions=insufficient,
    )


def _comparison(*, verdict, delta, production_eval=None, candidate_eval=None, candidate_name="candidate"):
    return CandidateModelComparisonReport(
        version=CANDIDATE_MODEL_COMPARISON_VERSION,
        dataset_version=DATASET_VERSION,
        production=production_eval or _evaluation(model_name="production", mae=Decimal("0.2")),
        candidate=candidate_eval or _evaluation(model_name=candidate_name, mae=Decimal("0.2")),
        calibration_error_delta=delta,
        verdict=verdict,
    )


def test_validated_comparison_is_promoted(session):
    comparison = _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"))

    decision = evaluate_promotion(session, comparison, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_PROMOTED
    assert decision.decision_reason == REASON_VALIDATED
    assert decision.promotion_rule_version == PROMOTION_RULE_VERSION
    assert decision.dataset_version == DATASET_VERSION


def test_regressed_comparison_is_rejected(session):
    comparison = _comparison(verdict=VERDICT_REGRESSED, delta=Decimal("0.5"))

    decision = evaluate_promotion(session, comparison, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_REJECTED
    assert decision.decision_reason == REASON_REGRESSED


def test_insufficient_evidence_comparison_is_rejected(session):
    comparison = _comparison(verdict=VERDICT_INSUFFICIENT_EVIDENCE, delta=None)

    decision = evaluate_promotion(session, comparison, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_REJECTED
    assert decision.decision_reason == REASON_INSUFFICIENT_EVIDENCE


def test_critical_segment_regression_blocks_promotion_despite_validated_overall(session):
    production_eval = _evaluation(
        model_name="production", mae=Decimal("0.2"),
        horizon_metrics=(ModelSegmentMetric("horizon", "1", 25, Decimal("0.6"), Decimal("0.8"), Decimal("0.1")),),
    )
    candidate_eval = _evaluation(
        model_name="candidate", mae=Decimal("0.2"),
        # horizon 1 calibration error blew up even though the overall MAE held
        horizon_metrics=(ModelSegmentMetric("horizon", "1", 25, Decimal("0.6"), Decimal("0.2"), Decimal("0.5")),),
    )
    comparison = _comparison(
        verdict=VERDICT_VALIDATED, delta=Decimal("0.0"), production_eval=production_eval, candidate_eval=candidate_eval
    )

    decision = evaluate_promotion(session, comparison, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_REJECTED
    assert decision.decision_reason == REASON_CRITICAL_SEGMENT_REGRESSION
    assert decision.regressed_segment_dimension == "horizon"
    assert decision.regressed_segment_key == "1"


def test_segment_regression_ignored_when_either_side_has_insufficient_sample(session):
    production_eval = _evaluation(
        model_name="production", mae=Decimal("0.2"),
        horizon_metrics=(ModelSegmentMetric("horizon", "1", 3, Decimal("0.6"), Decimal("0.67"), Decimal("0.1")),),
        insufficient=("horizon:1",),
    )
    candidate_eval = _evaluation(
        model_name="candidate", mae=Decimal("0.2"),
        horizon_metrics=(ModelSegmentMetric("horizon", "1", 3, Decimal("0.6"), Decimal("0.0"), Decimal("0.6")),),
        insufficient=("horizon:1",),
    )
    comparison = _comparison(
        verdict=VERDICT_VALIDATED, delta=Decimal("0.0"), production_eval=production_eval, candidate_eval=candidate_eval
    )

    decision = evaluate_promotion(session, comparison, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_PROMOTED


def test_promotion_decision_is_immutable_after_creation(session):
    comparison = _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"))
    decision = evaluate_promotion(session, comparison, approver="SYSTEM", decided_at=DECIDED_AT)

    decision.decision = DECISION_REJECTED
    with pytest.raises(ModelPromotionDecisionImmutableError, match="decision"):
        session.flush()
    session.rollback()


def test_active_model_tracks_only_the_latest_promotion_for_its_dataset_version(session):
    assert get_active_model(session, dataset_version=DATASET_VERSION) is None

    evaluate_promotion(
        session, _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"), candidate_name="v2"),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )
    assert get_active_model(session, dataset_version=DATASET_VERSION).candidate_model_name == "v2"

    # a later rejected candidate must not become "active"
    evaluate_promotion(
        session, _comparison(verdict=VERDICT_REGRESSED, delta=Decimal("0.5"), candidate_name="v3"),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )
    assert get_active_model(session, dataset_version=DATASET_VERSION).candidate_model_name == "v2"

    evaluate_promotion(
        session, _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"), candidate_name="v4"),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )
    assert get_active_model(session, dataset_version=DATASET_VERSION).candidate_model_name == "v4"


def test_promotion_history_preserves_every_decision_including_rejected_ones(session):
    evaluate_promotion(
        session, _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0"), candidate_name="v2"),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )
    evaluate_promotion(
        session, _comparison(verdict=VERDICT_REGRESSED, delta=Decimal("0.5"), candidate_name="v3"),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    history = get_promotion_history(session)
    assert [h.candidate_model_name for h in history] == ["v2", "v3"]
    assert [h.decision for h in history] == [DECISION_PROMOTED, DECISION_REJECTED]

    v3_only = get_promotion_history(session, candidate_model_name="v3")
    assert len(v3_only) == 1
    assert v3_only[0].decision_reason == REASON_REGRESSED


def test_promotion_does_not_modify_historical_prediction_tables(session):
    from app.models import Prediction

    before = session.query(Prediction).count()
    evaluate_promotion(session, _comparison(verdict=VERDICT_VALIDATED, delta=Decimal("0.0")), approver="SYSTEM", decided_at=DECIDED_AT)
    after = session.query(Prediction).count()

    assert before == after == 0
