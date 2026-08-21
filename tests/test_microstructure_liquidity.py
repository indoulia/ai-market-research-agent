from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery_segmentation import BUCKET_UNCLASSIFIED
from app.microstructure_liquidity import (
    DIMENSION_CIRCUIT_EVENT,
    DIMENSION_GAP_BUCKET,
    DIMENSION_LIQUIDITY_BUCKET,
    GAP_BUCKET_LARGE,
    GAP_BUCKET_SMALL,
    MICROSTRUCTURE_VERSION,
    MicrostructureSnapshotImmutableError,
    assess_liquidity_regime,
    compute_average_daily_turnover,
    compute_gap_observation,
    compute_liquidity_segment_performance,
    get_microstructure_snapshot,
    record_microstructure_snapshot,
)
from app.models import (
    DailyCandidateScan,
    MarketPrice,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
    Stock,
)

BASE_TIME = datetime(2027, 1, 30, tzinfo=timezone.utc)
_counter = iter(range(1000000))


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


def _make_stock(session):
    n = next(_counter)
    stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
    session.add(stock)
    session.commit()
    return stock


def _add_bar(session, stock_id, *, timestamp, open_, high, low, close, volume):
    session.add(MarketPrice(
        stock_id=stock_id, timestamp=timestamp, open=Decimal(str(open_)), high=Decimal(str(high)),
        low=Decimal(str(low)), close=Decimal(str(close)), volume=volume, source="TEST",
    ))
    session.commit()


def _make_prediction(session, stock_id, *, as_of):
    prediction = Prediction(
        stock_id=stock_id, as_of_timestamp=as_of, entry_price=Decimal("100"), horizon_days=5,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version="MV-1", feature_version="FV-1",
        consensus_contract_version="CC-1", horizon_selection_version="HS-1", scoring_contract_version="SC-1",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.commit()
    return prediction


def _add_scan_candidate(session, stock_id, *, created_at, volume_ratio_20d):
    n = next(_counter)
    scan = DailyCandidateScan(scan_date=created_at.date(), universe_version=f"UV-{n}", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    candidate = ScanCandidate(scan_id=scan.id, stock_id=stock_id, eligible=True, volume_ratio_20d=volume_ratio_20d)
    session.add(candidate)
    session.commit()
    candidate.created_at = created_at
    session.commit()
    return candidate


def _link_prediction_to_candidate(session, prediction_id, candidate_id):
    session.add(RecommendationGeneration(
        scan_candidate_id=candidate_id, outcome="QUALIFIED", consensus_contract_version="CC-1",
        prediction_id=prediction_id,
    ))
    session.commit()


def test_compute_average_daily_turnover_uses_bars_strictly_before_as_of(session):
    stock = _make_stock(session)
    for day in range(1, 4):
        _add_bar(session, stock.id, timestamp=BASE_TIME - timedelta(days=day), open_=100, high=101, low=99, close=100, volume=1000)
    # a bar exactly at as_of must not be included
    _add_bar(session, stock.id, timestamp=BASE_TIME, open_=100, high=200, low=100, close=200, volume=999999)

    turnover = compute_average_daily_turnover(session, stock.id, as_of=BASE_TIME, lookback_days=20)
    assert turnover == Decimal("100000")


def test_compute_average_daily_turnover_none_when_no_history(session):
    stock = _make_stock(session)
    assert compute_average_daily_turnover(session, stock.id, as_of=BASE_TIME) is None


def test_compute_gap_observation_large_gap_and_circuit_event(session):
    stock = _make_stock(session)
    _add_bar(session, stock.id, timestamp=BASE_TIME - timedelta(days=1), open_=100, high=101, low=99, close=100, volume=1000)
    _add_bar(session, stock.id, timestamp=BASE_TIME, open_=112, high=115, low=111, close=113, volume=1000)

    gap = compute_gap_observation(session, stock.id, as_of=BASE_TIME)
    assert gap.gap_percent == Decimal("0.12")
    assert gap.gap_bucket == GAP_BUCKET_LARGE
    assert gap.probable_circuit_band_event is True  # 13% day move >= 10% threshold


def test_compute_gap_observation_small_gap_no_circuit_event(session):
    stock = _make_stock(session)
    _add_bar(session, stock.id, timestamp=BASE_TIME - timedelta(days=1), open_=100, high=101, low=99, close=100, volume=1000)
    _add_bar(session, stock.id, timestamp=BASE_TIME, open_=100.5, high=101, low=100, close=101, volume=1000)

    gap = compute_gap_observation(session, stock.id, as_of=BASE_TIME)
    assert gap.gap_bucket == GAP_BUCKET_SMALL
    assert gap.probable_circuit_band_event is False


def test_compute_gap_observation_unclassified_with_insufficient_history(session):
    stock = _make_stock(session)
    _add_bar(session, stock.id, timestamp=BASE_TIME, open_=100, high=101, low=99, close=100, volume=1000)

    gap = compute_gap_observation(session, stock.id, as_of=BASE_TIME)
    assert gap.gap_percent is None
    assert gap.gap_bucket == BUCKET_UNCLASSIFIED
    assert gap.probable_circuit_band_event is False


def test_assess_liquidity_regime_detects_change(session):
    stock = _make_stock(session)
    _add_scan_candidate(session, stock.id, created_at=BASE_TIME - timedelta(days=10), volume_ratio_20d=Decimal("2.0"))  # HIGH
    _add_scan_candidate(session, stock.id, created_at=BASE_TIME, volume_ratio_20d=Decimal("0.3"))  # LOW

    regime = assess_liquidity_regime(session, stock.id, as_of=BASE_TIME)
    assert regime.liquidity_bucket == "LOW"
    assert regime.previous_liquidity_bucket == "HIGH"
    assert regime.regime_changed is True


def test_assess_liquidity_regime_no_change_without_prior_candidate(session):
    stock = _make_stock(session)
    _add_scan_candidate(session, stock.id, created_at=BASE_TIME, volume_ratio_20d=Decimal("1.0"))

    regime = assess_liquidity_regime(session, stock.id, as_of=BASE_TIME)
    assert regime.previous_liquidity_bucket is None
    assert regime.regime_changed is False


def test_record_microstructure_snapshot_idempotent(session):
    stock = _make_stock(session)
    _add_bar(session, stock.id, timestamp=BASE_TIME - timedelta(days=1), open_=100, high=101, low=99, close=100, volume=1000)
    _add_bar(session, stock.id, timestamp=BASE_TIME, open_=101, high=102, low=100, close=101, volume=1000)
    prediction = _make_prediction(session, stock.id, as_of=BASE_TIME)

    first = record_microstructure_snapshot(session, prediction, recorded_at=BASE_TIME)
    second = record_microstructure_snapshot(session, prediction, recorded_at=BASE_TIME)

    assert first.id == second.id
    assert first.snapshot_version == MICROSTRUCTURE_VERSION
    assert get_microstructure_snapshot(session, prediction.id).id == first.id


def test_microstructure_snapshot_is_immutable(session):
    stock = _make_stock(session)
    prediction = _make_prediction(session, stock.id, as_of=BASE_TIME)
    snapshot = record_microstructure_snapshot(session, prediction, recorded_at=BASE_TIME)

    snapshot.gap_bucket = "TAMPERED"
    with pytest.raises(MicrostructureSnapshotImmutableError):
        session.commit()
    session.rollback()


def test_compute_liquidity_segment_performance_segments_by_multiple_dimensions(session):
    stock = _make_stock(session)
    _add_bar(session, stock.id, timestamp=BASE_TIME - timedelta(days=1), open_=100, high=101, low=99, close=100, volume=1000)
    _add_bar(session, stock.id, timestamp=BASE_TIME, open_=100, high=101, low=99, close=100, volume=1000)

    for outcome in ("SUCCESS", "SUCCESS", "FAILURE"):
        prediction = _make_prediction(session, stock.id, as_of=BASE_TIME)
        session.add(PredictionOutcome(
            prediction_id=prediction.id, evaluation_date=BASE_TIME, highest_price=Decimal("105"),
            lowest_price=Decimal("98"), closing_price=Decimal("103"), maximum_return=Decimal("0.05"),
            maximum_drawdown=Decimal("-0.02"), actual_return=Decimal("0.03"), prediction_error=Decimal("0.01"),
            target_hit=(outcome == "SUCCESS"), stop_hit=(outcome == "FAILURE"), outcome=outcome,
        ))
        session.commit()
        record_microstructure_snapshot(session, prediction, recorded_at=BASE_TIME)

    report = compute_liquidity_segment_performance(session)
    assert report.evaluated_count == 3
    dimensions = {m.dimension for m in report.metrics}
    assert dimensions == {DIMENSION_LIQUIDITY_BUCKET, DIMENSION_GAP_BUCKET, DIMENSION_CIRCUIT_EVENT}
    liquidity_metric = next(m for m in report.metrics if m.dimension == DIMENSION_LIQUIDITY_BUCKET)
    assert liquidity_metric.evaluated_count == 3
    assert liquidity_metric.success_count == 2


def test_compute_liquidity_segment_performance_empty(session):
    report = compute_liquidity_segment_performance(session)
    assert report.evaluated_count == 0
    assert report.metrics == ()
