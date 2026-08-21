from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.assumption_decay_tracker import (
    DECAY_RULE_VERSION,
    VERDICT_MATERIAL_DECAY,
    VERDICT_NO_DECAY,
    VERDICT_PARTIAL_DECAY,
    assess_assumption_decay,
    get_assumption_decay_history,
)
from app.db import Base
from app.evidence_snapshot import (
    EVIDENCE_CATEGORY_EVENT,
    EVIDENCE_CATEGORY_FUNDAMENTAL,
    EVIDENCE_CATEGORY_MARKET_SECTOR,
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME,
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
)
from app.models import Prediction, RecommendationEvidenceItem, Stock

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)


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


def _make_prediction(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=5,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.commit()
    return prediction


def _add_item(session, prediction, *, category, evidence_timestamp, status=STATUS_AVAILABLE):
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category=category, status=status, source="test",
        reference=None, evidence_timestamp=evidence_timestamp, is_stale=False, snapshot_rule_version="EVS-001",
        captured_at=AS_OF,
    ))
    session.commit()


def test_no_decay_when_everything_fresh(session):
    prediction = _make_prediction(session)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=AS_OF - timedelta(hours=2))
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_NEWS, evidence_timestamp=AS_OF - timedelta(hours=1))

    assessment = assess_assumption_decay(session, prediction, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_NO_DECAY
    assert assessment.decayed_categories == []
    assert assessment.invalidation_recommended is False
    assert assessment.decay_rule_version == DECAY_RULE_VERSION


def test_partial_decay_when_minority_decayed(session):
    prediction = _make_prediction(session)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=AS_OF - timedelta(hours=2))
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_FUNDAMENTAL, evidence_timestamp=AS_OF - timedelta(days=1))
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_NEWS, evidence_timestamp=AS_OF - timedelta(hours=12))  # decayed, > 6h

    assessment = assess_assumption_decay(session, prediction, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_PARTIAL_DECAY
    assert assessment.decayed_categories == [EVIDENCE_CATEGORY_NEWS]
    assert assessment.decay_ratio == Decimal("0.333333")


def test_material_decay_when_majority_decayed(session):
    prediction = _make_prediction(session)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=AS_OF - timedelta(days=3))  # decayed, > 1 day
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_NEWS, evidence_timestamp=AS_OF - timedelta(hours=12))  # decayed, > 6h
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_EVENT, evidence_timestamp=AS_OF - timedelta(hours=1))  # fresh

    assessment = assess_assumption_decay(session, prediction, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_MATERIAL_DECAY
    assert assessment.invalidation_recommended is True
    assert set(assessment.decayed_categories) == {EVIDENCE_CATEGORY_TECHNICAL_VOLUME, EVIDENCE_CATEGORY_NEWS}


def test_market_sector_excluded_from_tracking(session):
    prediction = _make_prediction(session)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_MARKET_SECTOR, evidence_timestamp=AS_OF - timedelta(days=1000))
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=AS_OF - timedelta(hours=1))

    assessment = assess_assumption_decay(session, prediction, evaluated_at=AS_OF)

    assert EVIDENCE_CATEGORY_MARKET_SECTOR not in assessment.tracked_categories
    assert assessment.tracked_categories == [EVIDENCE_CATEGORY_TECHNICAL_VOLUME]
    assert assessment.verdict == VERDICT_NO_DECAY


def test_unavailable_status_excluded_from_tracking(session):
    prediction = _make_prediction(session)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_NEWS, evidence_timestamp=AS_OF - timedelta(days=10), status=STATUS_UNAVAILABLE)

    assessment = assess_assumption_decay(session, prediction, evaluated_at=AS_OF)

    assert assessment.tracked_categories == []
    assert assessment.verdict == VERDICT_NO_DECAY
    assert assessment.decay_ratio is None


def test_idempotent(session):
    prediction = _make_prediction(session)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=AS_OF - timedelta(hours=1))

    first = assess_assumption_decay(session, prediction, evaluated_at=AS_OF)
    second = assess_assumption_decay(session, prediction, evaluated_at=AS_OF)

    assert first.id == second.id
    assert len(get_assumption_decay_history(session, prediction.id)) == 1
