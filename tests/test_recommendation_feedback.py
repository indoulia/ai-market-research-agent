from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, PredictionOutcome, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.recommendation_feedback import (
    CATEGORY_CONFIDENCE,
    CATEGORY_OVERALL,
    CATEGORY_TARGET,
    FEEDBACK_RULE_VERSION,
    FEEDBACK_STAGE_POST_OUTCOME,
    FEEDBACK_STAGE_PRE_OUTCOME,
    REASON_AGREE,
    REASON_TOO_HIGH,
    InvalidFeedbackError,
    RecommendationFeedbackImmutableError,
    get_feedback_by_category,
    get_feedback_for_prediction,
    get_feedback_for_user,
    submit_feedback,
)

AS_OF = datetime(2026, 8, 1, tzinfo=timezone.utc)


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


def _make_prediction(session, symbol="AAA", scan_date=date(2026, 8, 1)):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id), stock


def test_user_can_submit_structured_feedback(session):
    prediction, _ = _make_prediction(session)

    feedback = submit_feedback(
        session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH,
        comment="target seems aggressive given recent volatility", submitted_at=AS_OF,
    )

    assert feedback.category == CATEGORY_TARGET
    assert feedback.reason_code == REASON_TOO_HIGH
    assert feedback.comment == "target seems aggressive given recent volatility"
    assert feedback.feedback_rule_version == FEEDBACK_RULE_VERSION


def test_feedback_is_linked_to_the_exact_model_version(session):
    prediction, _ = _make_prediction(session)

    feedback = submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_OVERALL, reason_code=REASON_AGREE, submitted_at=AS_OF)

    assert feedback.model_version == prediction.model_version
    assert feedback.prediction_id == prediction.id


def test_pre_outcome_feedback_is_staged_correctly(session):
    prediction, _ = _make_prediction(session)

    feedback = submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_OVERALL, reason_code=REASON_AGREE, submitted_at=AS_OF)

    assert feedback.feedback_stage == FEEDBACK_STAGE_PRE_OUTCOME


def test_post_outcome_feedback_is_staged_correctly(session):
    prediction, stock = _make_prediction(session)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("106"), high=Decimal("107"), low=Decimal("105"), close=Decimal("106"),
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)

    feedback = submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_OVERALL, reason_code=REASON_AGREE, submitted_at=AS_OF)

    assert feedback.feedback_stage == FEEDBACK_STAGE_POST_OUTCOME


def test_feedback_cannot_overwrite_objective_outcomes(session):
    prediction, stock = _make_prediction(session)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("106"), high=Decimal("107"), low=Decimal("105"), close=Decimal("106"),
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    before = (outcome.outcome, outcome.actual_return)

    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_OVERALL, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)

    after_outcome = session.get(PredictionOutcome, outcome.id)
    assert (after_outcome.outcome, after_outcome.actual_return) == before


def test_invalid_category_is_rejected(session):
    prediction, _ = _make_prediction(session)

    with pytest.raises(InvalidFeedbackError):
        submit_feedback(session, prediction, user_id="user-1", category="NOT_A_CATEGORY", reason_code=REASON_AGREE, submitted_at=AS_OF)


def test_invalid_reason_code_is_rejected(session):
    prediction, _ = _make_prediction(session)

    with pytest.raises(InvalidFeedbackError):
        submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_OVERALL, reason_code="NOT_A_REASON", submitted_at=AS_OF)


def test_empty_user_id_is_rejected(session):
    prediction, _ = _make_prediction(session)

    with pytest.raises(InvalidFeedbackError):
        submit_feedback(session, prediction, user_id="", category=CATEGORY_OVERALL, reason_code=REASON_AGREE, submitted_at=AS_OF)


def test_duplicate_looking_feedback_is_retained_not_deduplicated(session):
    prediction, _ = _make_prediction(session)

    first = submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_CONFIDENCE, reason_code=REASON_AGREE, submitted_at=AS_OF)
    second = submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_CONFIDENCE, reason_code=REASON_AGREE, submitted_at=AS_OF)

    assert first.id != second.id
    history = get_feedback_for_prediction(session, prediction.id)
    assert len(history) == 2


def test_feedback_is_immutable_after_creation(session):
    prediction, _ = _make_prediction(session)
    feedback = submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_OVERALL, reason_code=REASON_AGREE, submitted_at=AS_OF)

    feedback.reason_code = REASON_TOO_HIGH
    with pytest.raises(RecommendationFeedbackImmutableError, match="reason_code"):
        session.flush()
    session.rollback()


def test_feedback_can_be_queried_by_prediction_user_and_category(session):
    prediction_a, _ = _make_prediction(session, symbol="AAA", scan_date=date(2026, 8, 1))
    prediction_b, _ = _make_prediction(session, symbol="BBB", scan_date=date(2026, 8, 2))
    submit_feedback(session, prediction_a, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_AGREE, submitted_at=AS_OF)
    submit_feedback(session, prediction_b, user_id="user-2", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)

    assert len(get_feedback_for_prediction(session, prediction_a.id)) == 1
    assert len(get_feedback_for_user(session, "user-1")) == 1
    assert len(get_feedback_by_category(session, CATEGORY_TARGET)) == 2
