from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.position_risk_assessment import (
    MAX_ATR_MULTIPLE_PER_HORIZON_DAY,
    MIN_ATR_MULTIPLE_STOP,
    POSITION_RISK_ASSESSMENT_VERSION,
    REASON_STOP_TOO_TIGHT_FOR_VOLATILITY,
    REASON_STOP_TOO_WIDE_FOR_HORIZON,
    PositionRiskAssessmentImmutableError,
    UnpublishedRecommendationError,
    assess_position_risk,
    get_position_risk_assessment,
)
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2026, 10, 10, tzinfo=timezone.utc)


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


def _make_prediction(session, *, target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), atr_percent=Decimal("0.035")):
    scan = DailyCandidateScan(scan_date=AS_OF.date(), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=target_return, stop_return=stop_return,
    )
    return session.get(Prediction, generation.prediction_id)


def test_normal_case_is_horizon_consistent(session):
    prediction = _make_prediction(session, target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), atr_percent=Decimal("0.035"))
    publication = publish_recommendation(session, prediction, published_at=AS_OF)

    assessment = assess_position_risk(session, prediction, publication, assessed_at=AS_OF)

    assert assessment.horizon_consistent is True
    assert assessment.inconsistency_reason is None
    assert assessment.risk_percentage == Decimal("0.03")
    assert assessment.reward_percentage == Decimal("0.05")
    assert assessment.assessment_rule_version == POSITION_RISK_ASSESSMENT_VERSION


def test_risk_and_reward_are_expressed_in_atr_units(session):
    prediction = _make_prediction(session, target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), atr_percent=Decimal("0.035"))
    publication = publish_recommendation(session, prediction, published_at=AS_OF)

    assessment = assess_position_risk(session, prediction, publication, assessed_at=AS_OF)

    assert abs(assessment.risk_in_atr_units - (Decimal("0.03") / Decimal("0.035"))) < Decimal("0.001")
    assert abs(assessment.reward_in_atr_units - (Decimal("0.05") / Decimal("0.035"))) < Decimal("0.001")


def test_stop_too_tight_for_volatility_is_flagged(session):
    # downside 0.01 / atr 0.035 = 0.286, below MIN_ATR_MULTIPLE_STOP (0.5)
    prediction = _make_prediction(session, target_return=Decimal("0.05"), stop_return=Decimal("-0.01"), atr_percent=Decimal("0.035"))
    publication = publish_recommendation(session, prediction, published_at=AS_OF)

    assessment = assess_position_risk(session, prediction, publication, assessed_at=AS_OF)

    assert assessment.horizon_consistent is False
    assert assessment.inconsistency_reason == REASON_STOP_TOO_TIGHT_FOR_VOLATILITY


def test_stop_too_wide_for_horizon_is_flagged(session):
    # downside 0.10 / atr 0.035 = 2.857, above MAX (2.0 * horizon=1)
    prediction = _make_prediction(session, target_return=Decimal("0.20"), stop_return=Decimal("-0.10"), atr_percent=Decimal("0.035"))
    assert prediction.horizon_days == 1
    publication = publish_recommendation(session, prediction, published_at=AS_OF)

    assessment = assess_position_risk(session, prediction, publication, assessed_at=AS_OF)

    assert assessment.horizon_consistent is False
    assert assessment.inconsistency_reason == REASON_STOP_TOO_WIDE_FOR_HORIZON


def test_unpublished_recommendation_cannot_be_risk_assessed(session):
    prediction = _make_prediction(session, target_return=Decimal("0"), stop_return=Decimal("-0.03"))  # target_return=0 -> rejected by M1.47
    publication = publish_recommendation(session, prediction, published_at=AS_OF)
    assert publication.published is False

    with pytest.raises(UnpublishedRecommendationError):
        assess_position_risk(session, prediction, publication, assessed_at=AS_OF)


def test_assessment_is_deterministic_and_idempotent(session):
    prediction = _make_prediction(session)
    publication = publish_recommendation(session, prediction, published_at=AS_OF)

    first = assess_position_risk(session, prediction, publication, assessed_at=AS_OF)
    second = assess_position_risk(session, prediction, publication, assessed_at=AS_OF)

    assert first.id == second.id
    assert get_position_risk_assessment(session, prediction.id).id == first.id


def test_assessment_is_immutable_after_creation(session):
    prediction = _make_prediction(session)
    publication = publish_recommendation(session, prediction, published_at=AS_OF)
    assessment = assess_position_risk(session, prediction, publication, assessed_at=AS_OF)

    assessment.horizon_consistent = False
    with pytest.raises(PositionRiskAssessmentImmutableError, match="horizon_consistent"):
        session.flush()
    session.rollback()


def test_assessment_never_mutates_the_original_prediction_or_publication(session):
    prediction = _make_prediction(session)
    publication = publish_recommendation(session, prediction, published_at=AS_OF)
    before_prediction = (prediction.entry_price, prediction.horizon_days)
    before_publication = (publication.target_price, publication.stop_loss_price)

    assess_position_risk(session, prediction, publication, assessed_at=AS_OF)

    after_prediction = (prediction.entry_price, prediction.horizon_days)
    after_publication = (publication.target_price, publication.stop_loss_price)
    assert before_prediction == after_prediction
    assert before_publication == after_publication
