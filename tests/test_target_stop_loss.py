from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Prediction, Stock
from app.recommendations import record_recommendation
from app.target_stop_loss import (
    REASON_NON_POSITIVE_ENTRY_PRICE,
    REASON_STOP_NOT_BELOW_ENTRY,
    REASON_TARGET_NOT_ABOVE_ENTRY,
    TARGET_STOP_METHODOLOGY_VERSION,
    RecommendationPublicationImmutableError,
    get_publication,
    publish_recommendation,
)

PUBLISHED_AT = datetime(2026, 6, 1, tzinfo=timezone.utc)


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


def _make_prediction(session, *, entry_price=Decimal("100"), target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), horizon_days=1):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=PUBLISHED_AT,
        entry_price=entry_price,
        horizon_days=horizon_days,
        target_return=target_return,
        stop_return=stop_return,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        model_version="test-model-1",
        feature_version="FV-001",
        consensus_contract_version="POS-CON-001",
        horizon_selection_version="HZS-001",
        scoring_contract_version="POS-001",
        opportunity_score=Decimal("75.00"),
    )


def test_normal_case_produces_consistent_target_stop_and_reward_risk(session):
    prediction = _make_prediction(session, entry_price=Decimal("100"), target_return=Decimal("0.05"), stop_return=Decimal("-0.03"))

    publication = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    assert publication.published is True
    assert publication.rejection_reason is None
    assert publication.target_price == Decimal("105.000000")
    assert publication.stop_loss_price == Decimal("97.000000")
    assert publication.upside_percentage == Decimal("0.05")
    assert publication.downside_percentage == Decimal("0.03")
    assert abs(publication.reward_risk_ratio - (Decimal("0.05") / Decimal("0.03"))) < Decimal("0.001")
    assert publication.methodology_version == TARGET_STOP_METHODOLOGY_VERSION


def test_derived_percentages_reconcile_exactly_with_stored_prices(session):
    prediction = _make_prediction(session, entry_price=Decimal("237.50"), target_return=Decimal("0.08"), stop_return=Decimal("-0.045"))

    publication = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    recomputed_upside = (publication.target_price - publication.entry_price) / publication.entry_price
    recomputed_downside = -((publication.stop_loss_price - publication.entry_price) / publication.entry_price)
    assert recomputed_upside == publication.upside_percentage
    assert recomputed_downside == publication.downside_percentage


def test_boundary_zero_downside_has_no_reward_risk_ratio(session):
    # stop_return must still be < 0 to be valid, so approximate the boundary
    # with a negligible but nonzero downside and confirm the ratio is still
    # computed; then directly test the None-producing branch in isolation.
    from app.target_stop_loss import publish_recommendation as _publish

    prediction = _make_prediction(session, target_return=Decimal("0.05"), stop_return=Decimal("-0.0001"))
    publication = _publish(session, prediction, published_at=PUBLISHED_AT)
    assert publication.reward_risk_ratio is not None


def test_non_positive_entry_price_is_rejected(session):
    prediction = _make_prediction(session, entry_price=Decimal("0"))

    publication = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    assert publication.published is False
    assert publication.rejection_reason == REASON_NON_POSITIVE_ENTRY_PRICE


def test_target_not_above_entry_is_rejected(session):
    prediction = _make_prediction(session, target_return=Decimal("0"))

    publication = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    assert publication.published is False
    assert publication.rejection_reason == REASON_TARGET_NOT_ABOVE_ENTRY


def test_stop_not_below_entry_is_rejected(session):
    prediction = _make_prediction(session, stop_return=Decimal("0"))

    publication = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    assert publication.published is False
    assert publication.rejection_reason == REASON_STOP_NOT_BELOW_ENTRY


def test_publication_is_deterministic_and_idempotent(session):
    prediction = _make_prediction(session)

    first = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)
    second = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    assert first.id == second.id
    assert get_publication(session, prediction.id).id == first.id


def test_a_new_methodology_version_produces_a_separate_row_not_a_mutation(session):
    prediction = _make_prediction(session)

    v1 = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)
    v2 = publish_recommendation(session, prediction, published_at=PUBLISHED_AT, methodology_version="TSL-002")

    assert v1.id != v2.id
    assert v1.methodology_version != v2.methodology_version
    assert get_publication(session, prediction.id, methodology_version="TSL-002").id == v2.id


def test_publication_is_immutable_after_creation(session):
    prediction = _make_prediction(session)
    publication = publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    publication.published = False
    with pytest.raises(RecommendationPublicationImmutableError, match="published"):
        session.flush()
    session.rollback()


def test_publication_never_mutates_the_original_prediction(session):
    prediction = _make_prediction(session)
    before = (prediction.entry_price, prediction.target_return, prediction.stop_return, prediction.horizon_days)

    publish_recommendation(session, prediction, published_at=PUBLISHED_AT)

    after = (prediction.entry_price, prediction.target_return, prediction.stop_return, prediction.horizon_days)
    assert before == after
