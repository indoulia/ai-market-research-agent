from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, SOURCE_WATCHLIST, record_discovery, route_discovery_through_pipeline
from app.discovery_effectiveness import (
    DISCOVERY_EFFECTIVENESS_VERSION,
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OK,
    VERDICT_WEAK,
    compute_discovery_effectiveness_report,
)
from app.market_regime import classify_market_regime
from app.models import DailyCandidateScan, MarketPrice, ScanCandidate, Stock
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


def _make_candidate(session, scan, symbol, *, eligible=True, predicted_probability=Decimal("0.72"), atr_percent=Decimal("0.035")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=eligible,
        exclusion_reason=None if eligible else "missing_market_data",
        predicted_probability=predicted_probability,
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=atr_percent,
        data_quality_passed=eligible,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    return stock, candidate


def _discover(session, scan, stock, *, source):
    return record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=source, rationale="test", discovered_at=AS_OF)


def _route(session, discovery):
    return route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )


def _evaluate(session, stock_id, prediction, *, win: bool, horizon_days=1):
    filler = [100] * (horizon_days - 1)
    closes = filler + ([106] if win else [95])
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(MarketPrice(
            stock_id=stock_id, timestamp=AS_OF + timedelta(days=offset),
            open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
            volume=1000, source="test",
        ))
    session.flush()
    evaluate_recommendation(session, prediction)


def test_discovered_but_not_yet_routed_is_counted_but_not_qualified(session):
    scan = _make_scan(session)
    stock, _candidate = _make_candidate(session, scan, "PENDING")
    _discover(session, scan, stock, source=SOURCE_CHATGPT)

    report = compute_discovery_effectiveness_report(session)
    metric = next(m for m in report.by_source if m.source == SOURCE_CHATGPT)

    assert report.report_version == DISCOVERY_EFFECTIVENESS_VERSION
    assert metric.discovered_count == 1
    assert metric.routed_count == 0
    assert metric.qualified_count == 0


def test_rejection_and_failure_are_never_conflated(session):
    scan = _make_scan(session)
    rejected_stock, _ = _make_candidate(session, scan, "REJECTED", predicted_probability=Decimal("0.10"))
    _route(session, _discover(session, scan, rejected_stock, source=SOURCE_CHATGPT))

    failed_stock, _ = _make_candidate(session, scan, "FAILED")
    generation = _route(session, _discover(session, scan, failed_stock, source=SOURCE_CHATGPT))
    from app.models import Prediction

    prediction = session.get(Prediction, generation.prediction_id)
    _evaluate(session, failed_stock.id, prediction, win=False)

    report = compute_discovery_effectiveness_report(session)
    metric = next(m for m in report.by_source if m.source == SOURCE_CHATGPT)

    assert metric.rejected_count == 1
    assert metric.qualified_count == 1
    assert metric.failure_count == 1
    assert metric.evaluated_count == 1  # the rejected one never entered the evaluated population


def test_open_and_unevaluable_are_counted_separately_from_success_failure(session):
    scan = _make_scan(session)
    open_stock, _ = _make_candidate(session, scan, "OPENQ")
    generation = _route(session, _discover(session, scan, open_stock, source=SOURCE_CHATGPT))
    # no market data yet -> stays OPEN, no PredictionOutcome row at all

    unevaluable_stock, _ = _make_candidate(session, scan, "UNEVALQ")
    unevaluable_generation = _route(session, _discover(session, scan, unevaluable_stock, source=SOURCE_CHATGPT))
    from app.models import Prediction

    unevaluable_prediction = session.get(Prediction, unevaluable_generation.prediction_id)
    session.add(MarketPrice(
        stock_id=unevaluable_stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("0"), high=Decimal("-5"), low=Decimal("999"), close=Decimal("100"),
        volume=0, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, unevaluable_prediction)

    report = compute_discovery_effectiveness_report(session)
    metric = next(m for m in report.by_source if m.source == SOURCE_CHATGPT)

    assert metric.open_count == 1
    assert metric.unevaluable_count == 1
    assert metric.evaluated_count == 0


def test_high_and_low_performing_sources_are_distinguished(session):
    scan = _make_scan(session)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        stock, _ = _make_candidate(session, scan, f"GOOD{i}")
        generation = _route(session, _discover(session, scan, stock, source=SOURCE_CHATGPT))
        from app.models import Prediction
        prediction = session.get(Prediction, generation.prediction_id)
        _evaluate(session, stock.id, prediction, win=True)

    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        stock, _ = _make_candidate(session, scan, f"BAD{i}")
        generation = _route(session, _discover(session, scan, stock, source=SOURCE_WATCHLIST))
        from app.models import Prediction
        prediction = session.get(Prediction, generation.prediction_id)
        _evaluate(session, stock.id, prediction, win=False)

    report = compute_discovery_effectiveness_report(session)
    good = next(m for m in report.by_source if m.source == SOURCE_CHATGPT)
    bad = next(m for m in report.by_source if m.source == SOURCE_WATCHLIST)

    assert good.success_rate == Decimal("1")
    assert good.verdict == VERDICT_OK
    assert bad.success_rate == Decimal("0")
    assert bad.verdict == VERDICT_WEAK


def test_small_sample_source_is_insufficient_not_weak(session):
    scan = _make_scan(session)
    for i in range(3):
        stock, _ = _make_candidate(session, scan, f"S{i}")
        generation = _route(session, _discover(session, scan, stock, source=SOURCE_CHATGPT))
        from app.models import Prediction
        prediction = session.get(Prediction, generation.prediction_id)
        _evaluate(session, stock.id, prediction, win=False)

    report = compute_discovery_effectiveness_report(session)
    metric = next(m for m in report.by_source if m.source == SOURCE_CHATGPT)

    assert metric.evaluated_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert metric.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_by_source_and_regime_only_includes_classified_scans(session):
    scan = _make_scan(session)
    for i in range(6):
        _make_candidate(session, scan, f"UP{i}")
    stock, _ = _make_candidate(session, scan, "SUBJECT")
    generation = _route(session, _discover(session, scan, stock, source=SOURCE_CHATGPT))
    from app.models import Prediction
    prediction = session.get(Prediction, generation.prediction_id)
    _evaluate(session, stock.id, prediction, win=True)
    classify_market_regime(session, scan.id)

    report = compute_discovery_effectiveness_report(session)

    assert len(report.by_source_and_regime) == 1
    assert report.by_source_and_regime[0].source == SOURCE_CHATGPT
    assert report.by_source_and_regime[0].success_count == 1


def test_by_source_and_horizon_segments_correctly(session):
    scan = _make_scan(session)
    stock, _ = _make_candidate(session, scan, "H1STOCK", atr_percent=Decimal("0.035"))  # horizon=1
    generation = _route(session, _discover(session, scan, stock, source=SOURCE_CHATGPT))
    from app.models import Prediction
    prediction = session.get(Prediction, generation.prediction_id)
    assert prediction.horizon_days == 1
    _evaluate(session, stock.id, prediction, win=True, horizon_days=1)

    report = compute_discovery_effectiveness_report(session)
    metric = next(m for m in report.by_source_and_horizon if m.source == SOURCE_CHATGPT and m.horizon_days == 1)

    assert metric.evaluated_count == 1
    assert metric.success_rate == Decimal("1")
