from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.continuous_self_learning_loop import (
    CYCLE_RULE_VERSION,
    OUTCOME_RAN,
    OUTCOME_SKIPPED,
    SKIP_REASON_INSUFFICIENT_NEW_EVIDENCE,
    get_self_learning_cycle_history,
    run_self_learning_cycle,
)
from app.candidate_model_comparison import production_model
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation

STARTED_AT = datetime(2026, 8, 21, tzinfo=timezone.utc)
DATASET_VERSION = "CSL-TEST-001"


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


def _make_scan(session, scan_date):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, as_of, win: bool):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
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
        atr_percent=Decimal("0.035"),
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()

    discovery = record_discovery(
        session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="test", discovered_at=as_of
    )
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=as_of + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=as_of)
    return outcome


def _run(session, *, min_new_outcomes=3, trigger_discovery=None):
    return run_self_learning_cycle(
        session,
        dataset_version=DATASET_VERSION,
        candidate_model=production_model,
        candidate_model_name="candidate",
        approver="SYSTEM",
        started_at=STARTED_AT,
        min_new_outcomes=min_new_outcomes,
        trigger_discovery=trigger_discovery,
    )


def test_empty_history_is_skipped_with_explicit_reason(session):
    cycle = _run(session)

    assert cycle.outcome == OUTCOME_SKIPPED
    assert cycle.skip_reason == SKIP_REASON_INSUFFICIENT_NEW_EVIDENCE
    assert cycle.new_outcomes_count == 0
    assert cycle.watermark_outcome_id == 0
    assert cycle.dataset_version is None
    assert cycle.model_promotion_decision_id is None
    assert cycle.discovery_triggered is False
    assert cycle.cycle_rule_version == CYCLE_RULE_VERSION


def test_enough_new_outcomes_runs_the_full_pipeline(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(5):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True)

    cycle = _run(session)

    assert cycle.outcome == OUTCOME_RAN
    assert cycle.new_outcomes_count == 5
    assert cycle.watermark_outcome_id == 5
    assert cycle.dataset_version == DATASET_VERSION
    assert cycle.comparison_version is not None
    assert cycle.model_promotion_decision_id is not None


def test_discovery_is_not_triggered_when_cycle_is_skipped(session):
    calls = []
    cycle = _run(session, trigger_discovery=lambda: calls.append(1))

    assert cycle.outcome == OUTCOME_SKIPPED
    assert calls == []


def test_discovery_is_triggered_after_a_cycle_runs(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(5):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True)
    calls = []

    cycle = _run(session, trigger_discovery=lambda: calls.append(1))

    assert cycle.outcome == OUTCOME_RAN
    assert cycle.discovery_triggered is True
    assert calls == [1]


def test_rerunning_immediately_with_no_new_outcomes_is_skipped(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(5):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True)

    first = _run(session)
    second = _run(session)

    assert first.outcome == OUTCOME_RAN
    assert second.outcome == OUTCOME_SKIPPED
    assert second.new_outcomes_count == 0
    assert second.watermark_outcome_id == first.watermark_outcome_id


def test_watermark_advances_incrementally_across_cycles(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(5):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True)
    first = _run(session)
    assert first.outcome == OUTCOME_RAN

    for i in range(5, 8):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=False)
    second = _run(session)

    assert second.outcome == OUTCOME_RAN
    assert second.new_outcomes_count == 3
    assert second.watermark_outcome_id == first.watermark_outcome_id + 3


def test_learning_cycle_never_writes_to_predictions(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(5):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True)
    before = {p.id: (p.entry_price, p.target_return, p.opportunity_score) for p in session.query(Prediction).all()}

    _run(session)

    after = {p.id: (p.entry_price, p.target_return, p.opportunity_score) for p in session.query(Prediction).all()}
    assert before == after


def test_get_self_learning_cycle_history_reports_the_full_sequence(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(5):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True)
    _run(session)  # RAN
    _run(session)  # SKIPPED (no new outcomes)

    history = get_self_learning_cycle_history(session)

    assert [c.outcome for c in history] == [OUTCOME_RAN, OUTCOME_SKIPPED]
