from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.daily_prediction_snapshot import (
    DEFAULT_SNAPSHOT_RETENTION_WINDOW,
    SNAPSHOT_RULE_VERSION,
    DailyPredictionSnapshotImmutableError,
    capture_daily_prediction_snapshot,
    get_canonical_snapshot,
    get_snapshot_history,
    is_within_active_retention_window,
    reconstruct_snapshot_bundle,
)
from app.db import Base
from app.decision_trace import capture_decision_trace
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.prediction_trust_score import compute_prediction_trust_score

AS_OF = datetime(2026, 11, 1, tzinfo=timezone.utc)
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


def _make_prediction(session, symbol="AAA"):
    scan_date = date(2026, 11, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
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
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, generation


def test_capture_links_trace_and_trust_score(session):
    prediction, generation = _make_prediction(session)
    trace = capture_decision_trace(session, generation, traced_at=AS_OF)
    score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)

    snapshot = capture_daily_prediction_snapshot(session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF)

    assert snapshot.recommendation_decision_trace_id == trace.id
    assert snapshot.prediction_trust_score_id == score.id
    assert snapshot.is_canonical is True
    assert snapshot.snapshot_rule_version == SNAPSHOT_RULE_VERSION


def test_capture_without_trace_or_trust_score_is_honest(session):
    prediction, _generation = _make_prediction(session)

    snapshot = capture_daily_prediction_snapshot(session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF)

    assert snapshot.recommendation_decision_trace_id is None
    assert snapshot.prediction_trust_score_id is None


def test_canonical_snapshot_is_idempotent_per_day(session):
    prediction, _generation = _make_prediction(session)

    first = capture_daily_prediction_snapshot(session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF)
    second = capture_daily_prediction_snapshot(
        session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF + timedelta(hours=2)
    )

    assert first.id == second.id
    assert len(get_snapshot_history(session, prediction.id)) == 1


def test_intraday_snapshots_are_freely_appended(session):
    prediction, _generation = _make_prediction(session)

    capture_daily_prediction_snapshot(
        session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF, is_canonical=False
    )
    capture_daily_prediction_snapshot(
        session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF + timedelta(hours=3), is_canonical=False
    )
    canonical = capture_daily_prediction_snapshot(
        session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF + timedelta(hours=6)
    )

    history = get_snapshot_history(session, prediction.id)
    assert len(history) == 3
    assert sum(1 for s in history if s.is_canonical) == 1
    assert get_canonical_snapshot(session, prediction.id, date(2026, 11, 1)).id == canonical.id


def test_trust_score_attachment_is_point_in_time_safe(session):
    prediction, _generation = _make_prediction(session)
    early_score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)
    late_score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF + timedelta(days=5))

    snapshot = capture_daily_prediction_snapshot(
        session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF + timedelta(hours=1)
    )

    assert snapshot.prediction_trust_score_id == early_score.id
    assert snapshot.prediction_trust_score_id != late_score.id


def test_snapshot_is_immutable(session):
    prediction, _generation = _make_prediction(session)
    snapshot = capture_daily_prediction_snapshot(session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF)

    snapshot.is_canonical = False
    with pytest.raises(DailyPredictionSnapshotImmutableError):
        session.commit()
    session.rollback()


def test_reconstruct_snapshot_bundle_returns_linked_objects(session):
    prediction, generation = _make_prediction(session)
    trace = capture_decision_trace(session, generation, traced_at=AS_OF)
    score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)
    snapshot = capture_daily_prediction_snapshot(session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF)

    bundle = reconstruct_snapshot_bundle(session, snapshot)

    assert bundle.decision_trace.id == trace.id
    assert bundle.trust_score.id == score.id
    assert bundle.snapshot.id == snapshot.id


def test_retention_window_classification(session):
    prediction, _generation = _make_prediction(session)
    snapshot = capture_daily_prediction_snapshot(session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF)

    assert is_within_active_retention_window(snapshot, as_of=AS_OF + timedelta(days=1)) is True
    assert is_within_active_retention_window(snapshot, as_of=AS_OF + DEFAULT_SNAPSHOT_RETENTION_WINDOW + timedelta(days=1)) is False


def test_never_writes_to_prediction_or_trace(session):
    prediction, generation = _make_prediction(session)
    trace = capture_decision_trace(session, generation, traced_at=AS_OF)
    before_prediction = (prediction.confidence, prediction.opportunity_score)
    before_trace = (trace.qualification_outcome, trace.target_price)

    capture_daily_prediction_snapshot(session, prediction, snapshot_date=date(2026, 11, 1), snapshotted_at=AS_OF)

    after_prediction = (prediction.confidence, prediction.opportunity_score)
    after_trace = (trace.qualification_outcome, trace.target_price)
    assert before_prediction == after_prediction
    assert before_trace == after_trace
