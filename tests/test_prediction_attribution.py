from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.decision_trace import capture_decision_trace
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_snapshot import capture_evidence_snapshot
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.prediction_attribution import (
    ASSOCIATION_FAILURE,
    ASSOCIATION_SUCCESS,
    ATTRIBUTION_RULE_VERSION,
    BUCKET_STRONG,
    BUCKET_WEAK,
    DIMENSION_EVIDENCE_AVAILABLE,
    DIMENSION_REGIME,
    DIMENSION_SMA20_DISTANCE,
    REPORT_VERDICT_INSUFFICIENT_SAMPLE,
    REPORT_VERDICT_MEASURED,
    VOLUME_BUCKET_HIGH,
    capture_attribution_snapshot,
    compute_factor_association_report,
    get_attribution_snapshot,
)
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 4, 1, tzinfo=timezone.utc)
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
    scan_date = date(2027, 4, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_prediction(session, symbol, *, win, sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.10")):
    scan = _make_scan(session)
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
        volume_ratio_20d=volume_ratio_20d, atr_percent=Decimal("0.035"), data_quality_passed=True,
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
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)
    capture_decision_trace(session, generation, traced_at=AS_OF)
    return prediction, generation


def test_snapshot_requires_outcome_and_trace(session):
    scan = _make_scan(session)
    stock = Stock(symbol="NOEVAL", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
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

    assert capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF) is None


def test_snapshot_captures_correct_buckets_and_evidence(session):
    prediction, _generation = _make_prediction(
        session, "AAA", win=True, sma20_distance=Decimal("0.07"), volume_ratio_20d=Decimal("2.5")
    )

    snapshot = capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF)

    assert snapshot.sma20_distance_bucket == BUCKET_STRONG
    assert snapshot.volume_ratio_bucket == VOLUME_BUCKET_HIGH
    assert snapshot.outcome == "SUCCESS"
    assert "TECHNICAL_VOLUME" in snapshot.evidence_categories_available
    assert snapshot.attribution_rule_version == ATTRIBUTION_RULE_VERSION
    assert snapshot.regime is not None


def test_snapshot_is_idempotent(session):
    prediction, _generation = _make_prediction(session, "BBB", win=True)

    first = capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF)
    second = capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF + timedelta(days=1))

    assert first.id == second.id
    assert get_attribution_snapshot(session, prediction.id).id == first.id


def test_association_report_insufficient_sample(session):
    prediction, _generation = _make_prediction(session, "CCC", win=True)
    capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF)

    report = compute_factor_association_report(session, scope_label="all-time", computed_at=AS_OF)

    assert report.verdict == REPORT_VERDICT_INSUFFICIENT_SAMPLE
    assert report.baseline_success_rate is None
    assert report.factor_associations == []


def test_association_report_measures_real_association(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        prediction, _g = _make_prediction(session, f"S{i}", win=True, sma20_distance=Decimal("0.07"))
        capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF)
    for i in range(total):
        prediction, _g = _make_prediction(session, f"F{i}", win=False, sma20_distance=Decimal("0.01"))
        capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF)

    report = compute_factor_association_report(session, scope_label="all-time", computed_at=AS_OF)

    assert report.verdict == REPORT_VERDICT_MEASURED
    assert report.sample_count == total * 2
    assert report.baseline_success_rate == Decimal("0.5")

    by_key = {(a["dimension"], a["value"]): a for a in report.factor_associations}
    strong = by_key[(DIMENSION_SMA20_DISTANCE, BUCKET_STRONG)]
    weak = by_key[(DIMENSION_SMA20_DISTANCE, BUCKET_WEAK)]
    assert strong["success_rate"] == "1"
    assert strong["association"] == ASSOCIATION_SUCCESS
    assert weak["success_rate"] == "0"
    assert weak["association"] == ASSOCIATION_FAILURE

    evidence_entries = [a for a in report.factor_associations if a["dimension"] == DIMENSION_EVIDENCE_AVAILABLE]
    assert len(evidence_entries) > 0
    regime_entries = [a for a in report.factor_associations if a["dimension"] == DIMENSION_REGIME]
    assert len(regime_entries) > 0


def test_never_writes_to_predictions_or_traces(session):
    prediction, generation = _make_prediction(session, "DDD", win=True)
    before = (prediction.confidence, prediction.opportunity_score)

    capture_attribution_snapshot(session, prediction, snapshotted_at=AS_OF)
    compute_factor_association_report(session, scope_label="all-time", computed_at=AS_OF)

    after = (prediction.confidence, prediction.opportunity_score)
    assert before == after
