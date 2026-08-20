from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.discovery_segmentation import record_segment_for_discovery
from app.historical_learning_dataset import (
    DATASET_CONSTRUCTION_VERSION,
    REASON_INSUFFICIENT_DATA_OUTCOME,
    REASON_NOT_YET_COMPLETED,
    REASON_OUTCOME_NOT_YET_MEASURED,
    HistoricalLearningRecordImmutableError,
    build_learning_dataset,
    build_learning_record,
    get_learning_dataset,
)
from app.market_regime import classify_market_regime
from app.models import DailyCandidateScan, MarketPrice, Prediction, PredictionOutcome, ScanCandidate, Stock
from app.outcome_measurement import OUTCOME_INSUFFICIENT_DATA, OUTCOME_SUCCESS, measure_outcome
from app.outcomes import evaluate_recommendation

AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)


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


def _make_scan(session):
    scan = DailyCandidateScan(scan_date=date(2026, 8, 21), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_qualified(session, scan, symbol, *, sector="Energy", market_cap=Decimal("30000")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector, market_cap=market_cap)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"),  # horizon=1
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(
        session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="test", discovered_at=AS_OF
    )
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    record_segment_for_discovery(session, discovery, stock, candidate)
    prediction = session.get(Prediction, generation.prediction_id)
    return stock, prediction


def test_incomplete_recommendation_is_excluded_not_completed(session):
    scan = _make_scan(session)
    _stock, prediction = _make_qualified(session, scan, "RELIANCE")

    record = build_learning_record(session, prediction)

    assert record.included is False
    assert record.exclusion_reason == REASON_NOT_YET_COMPLETED
    assert record.dataset_version == DATASET_CONSTRUCTION_VERSION


def test_completed_but_unmeasured_outcome_is_excluded_pending_measurement(session):
    scan = _make_scan(session)
    stock, prediction = _make_qualified(session, scan, "RELIANCE")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("106"),
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)
    # M1.38's measure_outcome deliberately not called yet

    record = build_learning_record(session, prediction)

    assert record.included is False
    assert record.exclusion_reason == REASON_OUTCOME_NOT_YET_MEASURED


def test_insufficient_data_outcome_is_excluded_with_classification_preserved(session):
    scan = _make_scan(session)
    stock, prediction = _make_qualified(session, scan, "RELIANCE")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("0"), high=Decimal("-5"), low=Decimal("999"), close=Decimal("100"),
        volume=0, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=AS_OF)

    record = build_learning_record(session, prediction)

    assert record.included is False
    assert record.exclusion_reason == REASON_INSUFFICIENT_DATA_OUTCOME
    assert record.outcome_classification == OUTCOME_INSUFFICIENT_DATA


def test_fully_completed_record_is_included_with_full_context(session):
    scan = _make_scan(session)
    stock, prediction = _make_qualified(session, scan, "RELIANCE", sector="Energy", market_cap=Decimal("30000"))
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("107"), low=Decimal("99"), close=Decimal("106"),
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=AS_OF)
    classify_market_regime(session, scan.id)

    record = build_learning_record(session, prediction)

    assert record.included is True
    assert record.exclusion_reason is None
    assert record.outcome_classification == OUTCOME_SUCCESS
    assert record.information_cutoff.replace(tzinfo=None) == AS_OF.replace(tzinfo=None)
    assert record.predicted_probability == Decimal("0.72")
    assert record.opportunity_score is not None
    assert record.sma20_distance == Decimal("0.03")
    assert record.horizon_days == 1
    assert record.sector == "Energy"
    assert record.market_cap_bucket == "LARGE_CAP"
    assert record.discovery_source == SOURCE_CHATGPT
    assert record.market_regime is not None


def test_building_the_same_version_twice_is_idempotent(session):
    scan = _make_scan(session)
    _stock, prediction = _make_qualified(session, scan, "RELIANCE")

    first = build_learning_record(session, prediction)
    second = build_learning_record(session, prediction)

    assert first.id == second.id
    assert session.query(Prediction).count() == 1


def test_different_dataset_versions_produce_separate_rows(session):
    scan = _make_scan(session)
    _stock, prediction = _make_qualified(session, scan, "RELIANCE")

    v1 = build_learning_record(session, prediction, dataset_version="HOL-001")
    v2 = build_learning_record(session, prediction, dataset_version="HOL-002")

    assert v1.id != v2.id
    assert v1.dataset_version != v2.dataset_version


def test_build_learning_dataset_covers_every_prediction(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "AAA")
    _make_qualified(session, scan, "BBB")

    records = build_learning_dataset(session)

    assert len(records) == 2
    retrieved = get_learning_dataset(session, DATASET_CONSTRUCTION_VERSION)
    assert len(retrieved) == 2


def test_learning_record_is_immutable_after_creation(session):
    scan = _make_scan(session)
    _stock, prediction = _make_qualified(session, scan, "RELIANCE")
    record = build_learning_record(session, prediction)

    record.included = True
    with pytest.raises(HistoricalLearningRecordImmutableError, match="included"):
        session.flush()
    session.rollback()
