from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import evaluate_evidence_quality
from app.evidence_snapshot import capture_evidence_snapshot
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.recommendation_generator import generate_recommendation_for_candidate
from app.short_horizon_probability import (
    DOWNSIDE_PERCENTILE,
    PROBABILITY_PROFILE_VERSION,
    SUPPORTED_HORIZON_DAYS,
    VERDICT_CALIBRATED,
    VERDICT_INSUFFICIENT_SAMPLE,
    compute_horizon_probability_profile,
    get_latest_probability_profile,
    get_probability_profile_for_prediction,
    get_profile_history,
)
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
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
    scan_date = date(2026, 9, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _atr_for_horizon(horizon_days: int) -> Decimal:
    return {1: Decimal("0.035"), 3: Decimal("0.020"), 5: Decimal("0.010"), 7: Decimal("0.001")}[horizon_days]


def _make_evaluated(
    session, symbol, *, horizon_days, win: bool, as_of, gate_sufficient: bool | None, discover: bool = True
):
    scan = _make_scan(session)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=as_of,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=_atr_for_horizon(horizon_days), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()

    if discover:
        discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
        generation = route_discovery_through_pipeline(
            session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
            target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        )
    else:
        generation = generate_recommendation_for_candidate(
            session, candidate, as_of_timestamp=as_of, entry_price=Decimal("100"),
            target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        )
    prediction = session.get(Prediction, generation.prediction_id)
    assert prediction.horizon_days == horizon_days

    # Evidence is captured/gated at decision time -- before any future
    # price data exists -- matching real production ordering and
    # avoiding a false leakage positive from the next-day price bar
    # added below purely to let `evaluate_recommendation` resolve an
    # outcome.
    if gate_sufficient is not None:
        capture_evidence_snapshot(session, prediction, captured_at=as_of)
        decision = evaluate_evidence_quality(session, prediction, evaluated_at=as_of)
        if gate_sufficient:
            assert decision.state == "SUFFICIENT"
        else:
            assert decision.state != "SUFFICIENT"

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=as_of + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)

    return prediction


def test_day_two_is_always_insufficient_sample(session):
    assert 2 in SUPPORTED_HORIZON_DAYS

    profile = compute_horizon_probability_profile(
        session, model_version=MODEL_VERSION, horizon_days=2, computed_at=datetime(2026, 9, 1, tzinfo=timezone.utc)
    )

    assert profile.sample_count == 0
    assert profile.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert profile.positive_return_probability is None
    assert profile.profile_rule_version == PROBABILITY_PROFILE_VERSION


def test_below_minimum_sample_is_insufficient(session):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON - 1):
        _make_evaluated(session, f"A{i}", horizon_days=1, win=True, as_of=as_of, gate_sufficient=True)

    profile = compute_horizon_probability_profile(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=as_of)

    assert profile.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_calibrated_profile_has_correct_probabilities(session):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    total = 24
    win_count = 18
    for i in range(total):
        _make_evaluated(session, f"B{i}", horizon_days=1, win=(i < win_count), as_of=as_of, gate_sufficient=True)

    profile = compute_horizon_probability_profile(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=as_of)

    assert profile.verdict == VERDICT_CALIBRATED
    assert profile.sample_count == total
    assert profile.positive_return_probability == Decimal("0.75")
    assert profile.target_hit_probability == Decimal("0.75")
    assert profile.stop_hit_probability == Decimal("0.25")
    assert profile.expected_return == Decimal("0.03")
    assert profile.downside_p10_return == Decimal("-0.03")


def test_ungated_and_insufficiently_gated_predictions_are_excluded(session):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON + 5
    for i in range(total):
        _make_evaluated(session, f"C{i}", horizon_days=1, win=True, as_of=as_of, gate_sufficient=True)
    # never gated at all -- must not count
    _make_evaluated(session, "ungated", horizon_days=1, win=True, as_of=as_of, gate_sufficient=None)
    # gated but INSUFFICIENT (no discovery -> fewer available categories) -- must not count
    _make_evaluated(session, "insufficiently-gated", horizon_days=1, win=True, as_of=as_of, gate_sufficient=False, discover=False)

    profile = compute_horizon_probability_profile(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=as_of)

    assert profile.sample_count == total


def test_profile_history_and_latest(session):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    first = compute_horizon_probability_profile(session, model_version=MODEL_VERSION, horizon_days=3, computed_at=as_of)
    second = compute_horizon_probability_profile(
        session, model_version=MODEL_VERSION, horizon_days=3, computed_at=as_of + timedelta(days=1)
    )

    history = get_profile_history(session, model_version=MODEL_VERSION, horizon_days=3)
    latest = get_latest_probability_profile(session, model_version=MODEL_VERSION, horizon_days=3)

    assert [p.id for p in history] == [first.id, second.id]
    assert latest.id == second.id


def test_get_probability_profile_for_prediction_attaches_correct_cohort(session):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    prediction = _make_evaluated(session, "D1", horizon_days=5, win=True, as_of=as_of, gate_sufficient=True)
    profile = compute_horizon_probability_profile(session, model_version=MODEL_VERSION, horizon_days=5, computed_at=as_of)

    attached = get_probability_profile_for_prediction(session, prediction)

    assert attached.id == profile.id


def test_computation_never_writes_to_prediction(session):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    prediction = _make_evaluated(session, "E1", horizon_days=1, win=True, as_of=as_of, gate_sufficient=True)
    before = (prediction.confidence, prediction.opportunity_score)

    compute_horizon_probability_profile(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=as_of)

    after = (prediction.confidence, prediction.opportunity_score)
    assert before == after
