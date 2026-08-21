from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.horizon_regime_trust import (
    HORIZON_REGIME_TRUST_VERSION,
    SEGMENT_COMBINED,
    SEGMENT_HORIZON,
    SEGMENT_REGIME,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_SUFFICIENT,
    HorizonRegimeTrustImmutableError,
    MissingSegmentDimensionError,
    compute_horizon_regime_trust,
    get_latest_trust,
    get_trust_history,
)
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2026, 12, 1, tzinfo=timezone.utc)
_scan_counter = iter(range(100000))


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
    scan_date = date(2026, 12, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, win: bool, sma20_distance=Decimal("0.03"), atr_percent=Decimal("0.035")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=sma20_distance,
        volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)

    for day in range(1, prediction.horizon_days):
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=AS_OF + timedelta(days=day),
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
            volume=1000, source="test",
        ))
    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=prediction.horizon_days),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)
    return prediction


def test_missing_both_dimensions_raises(session):
    with pytest.raises(MissingSegmentDimensionError):
        compute_horizon_regime_trust(session, model_version=MODEL_VERSION, computed_at=AS_OF)


def test_horizon_segment_insufficient_sample(session):
    scan = _make_scan(session)
    for i in range(5):
        _make_evaluated(session, scan, f"A{i}", win=True)

    trust = compute_horizon_regime_trust(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)

    assert trust.segment_type == SEGMENT_HORIZON
    assert trust.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert trust.success_rate is None
    assert trust.is_low_trust is False
    assert trust.trust_rule_version == HORIZON_REGIME_TRUST_VERSION


def test_horizon_segment_sufficient_sample_has_correct_stats(session):
    scan = _make_scan(session)
    total, win_count = 24, 18
    for i in range(total):
        _make_evaluated(session, scan, f"B{i}", win=(i < win_count))

    trust = compute_horizon_regime_trust(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)

    assert trust.verdict == VERDICT_SUFFICIENT
    assert trust.sample_count == total
    assert trust.success_rate == Decimal("0.75")
    assert trust.is_low_trust is False
    expected_se = Decimal(str((0.75 * 0.25 / 24) ** 0.5))
    assert abs(trust.success_rate_standard_error - expected_se) < Decimal("0.0001")


def test_regime_segment_flags_low_trust(session):
    scan = _make_scan(session)
    total, win_count = 24, 6  # success_rate = 0.25, below the low-trust threshold
    for i in range(total):
        _make_evaluated(session, scan, f"C{i}", win=(i < win_count))

    trust = compute_horizon_regime_trust(session, model_version=MODEL_VERSION, regime="BULLISH_HIGH_VOL", computed_at=AS_OF)

    assert trust.segment_type == SEGMENT_REGIME
    assert trust.verdict == VERDICT_SUFFICIENT
    assert trust.success_rate == Decimal("0.25")
    assert trust.is_low_trust is True


def test_combined_segment_insufficient_sample(session):
    scan = _make_scan(session)
    for i in range(5):
        _make_evaluated(session, scan, f"D{i}", win=True)

    trust = compute_horizon_regime_trust(
        session, model_version=MODEL_VERSION, horizon_days=1, regime="BULLISH_HIGH_VOL", computed_at=AS_OF
    )

    assert trust.segment_type == SEGMENT_COMBINED
    assert trust.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_combined_segment_sufficient_sample(session):
    scan = _make_scan(session)
    total, win_count = MIN_SAMPLE_SIZE_FOR_COMPARISON, MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        _make_evaluated(session, scan, f"E{i}", win=True)

    trust = compute_horizon_regime_trust(
        session, model_version=MODEL_VERSION, horizon_days=1, regime="BULLISH_HIGH_VOL", computed_at=AS_OF
    )

    assert trust.verdict == VERDICT_SUFFICIENT
    assert trust.success_rate == Decimal("1")
    assert trust.sample_count == total


def test_a_different_regime_is_isolated(session):
    # This platform only ever generates a real Prediction for a positive
    # (upward-trending) candidate, so a BEARISH regime can never have real
    # evaluated evidence here -- the same honest constraint as day-2
    # horizons. Isolation is instead proven across two regimes that *can*
    # both occur for positive candidates: differing volatility bands.
    high_vol_scan = _make_scan(session)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, high_vol_scan, f"F{i}", win=True, atr_percent=Decimal("0.035"))
    low_vol_scan = _make_scan(session)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, low_vol_scan, f"G{i}", win=False, atr_percent=Decimal("0.02"))

    high_vol_trust = compute_horizon_regime_trust(session, model_version=MODEL_VERSION, regime="BULLISH_HIGH_VOL", computed_at=AS_OF)
    low_vol_trust = compute_horizon_regime_trust(session, model_version=MODEL_VERSION, regime="BULLISH_LOW_VOL", computed_at=AS_OF)

    assert high_vol_trust.success_rate == Decimal("1")
    assert low_vol_trust.success_rate == Decimal("0")


def test_history_and_latest(session):
    scan = _make_scan(session)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, scan, f"H{i}", win=True)

    first = compute_horizon_regime_trust(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)
    second = compute_horizon_regime_trust(
        session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF + timedelta(days=1)
    )

    history = get_trust_history(session, model_version=MODEL_VERSION, segment_type=SEGMENT_HORIZON, horizon_days=1)
    latest = get_latest_trust(session, model_version=MODEL_VERSION, segment_type=SEGMENT_HORIZON, horizon_days=1)

    assert [t.id for t in history] == [first.id, second.id]
    assert latest.id == second.id


def test_trust_is_immutable(session):
    scan = _make_scan(session)
    for i in range(5):
        _make_evaluated(session, scan, f"I{i}", win=True)
    trust = compute_horizon_regime_trust(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)

    trust.is_low_trust = True
    with pytest.raises(HorizonRegimeTrustImmutableError):
        session.commit()
    session.rollback()


def test_never_writes_to_prediction(session):
    scan = _make_scan(session)
    predictions = [_make_evaluated(session, scan, f"J{i}", win=True) for i in range(5)]
    before = [(p.confidence, p.opportunity_score) for p in predictions]

    compute_horizon_regime_trust(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)

    after = [(p.confidence, p.opportunity_score) for p in predictions]
    assert before == after
