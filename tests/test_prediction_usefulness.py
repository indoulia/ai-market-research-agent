from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.prediction_usefulness import (
    DIRECTIONALLY_CORRECT_NOT_USEFUL,
    NOT_USEFUL,
    REPORT_VERDICT_INSUFFICIENT_SAMPLE,
    REPORT_VERDICT_MEASURED,
    USEFUL,
    USEFULNESS_RULE_VERSION,
    PredictionUsefulnessAssessmentImmutableError,
    assess_prediction_usefulness,
    compute_horizon_usefulness_report,
    get_usefulness_assessment,
    get_usefulness_report_history,
)
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 5, 1, tzinfo=timezone.utc)
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
    scan_date = date(2027, 5, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_prediction(session, symbol, *, atr_percent=Decimal("0.035")):
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
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
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
    return session.get(Prediction, generation.prediction_id)


def _add_price(session, prediction, day, *, open_, high, low, close):
    session.add(MarketPrice(
        stock_id=prediction.stock_id, timestamp=AS_OF + timedelta(days=day),
        open=open_, high=high, low=low, close=close, volume=1000, source="test",
    ))
    session.flush()


def test_no_outcome_yields_no_assessment(session):
    prediction = _make_prediction(session, "A1")

    assert assess_prediction_usefulness(session, prediction, assessed_at=AS_OF) is None


def test_zero_drawdown_success_is_useful(session):
    prediction = _make_prediction(session, "B1")  # horizon 1
    _add_price(session, prediction, 1, open_=Decimal("106"), high=Decimal("107"), low=Decimal("100"), close=Decimal("106"))
    evaluate_recommendation(session, prediction)

    assessment = assess_prediction_usefulness(session, prediction, assessed_at=AS_OF)

    assert assessment.directional_outcome == "SUCCESS"
    assert assessment.risk_adjusted_ratio is None
    assert assessment.usefulness_verdict == USEFUL
    assert assessment.usefulness_rule_version == USEFULNESS_RULE_VERSION


def test_failure_is_not_useful(session):
    prediction = _make_prediction(session, "C1")  # horizon 1
    _add_price(session, prediction, 1, open_=Decimal("95"), high=Decimal("96"), low=Decimal("94"), close=Decimal("95"))
    evaluate_recommendation(session, prediction)

    assessment = assess_prediction_usefulness(session, prediction, assessed_at=AS_OF)

    assert assessment.directional_outcome == "FAILURE"
    assert assessment.usefulness_verdict == NOT_USEFUL


def test_success_with_severe_later_excursion_is_not_useful(session):
    prediction = _make_prediction(session, "D1", atr_percent=Decimal("0.02"))  # horizon 3
    _add_price(session, prediction, 1, open_=Decimal("106"), high=Decimal("107"), low=Decimal("99"), close=Decimal("106"))
    _add_price(session, prediction, 2, open_=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"))
    _add_price(session, prediction, 3, open_=Decimal("88"), high=Decimal("90"), low=Decimal("85"), close=Decimal("88"))
    evaluate_recommendation(session, prediction)

    assessment = assess_prediction_usefulness(session, prediction, assessed_at=AS_OF)

    assert assessment.directional_outcome == "SUCCESS"
    assert abs(assessment.risk_adjusted_ratio - (Decimal("0.05") / Decimal("0.15"))) < Decimal("0.000001")
    assert assessment.usefulness_verdict == DIRECTIONALLY_CORRECT_NOT_USEFUL


def test_assessment_is_idempotent(session):
    prediction = _make_prediction(session, "E1")
    _add_price(session, prediction, 1, open_=Decimal("106"), high=Decimal("107"), low=Decimal("105"), close=Decimal("106"))
    evaluate_recommendation(session, prediction)

    first = assess_prediction_usefulness(session, prediction, assessed_at=AS_OF)
    second = assess_prediction_usefulness(session, prediction, assessed_at=AS_OF + timedelta(days=1))

    assert first.id == second.id
    assert get_usefulness_assessment(session, prediction.id).id == first.id


def test_assessment_is_immutable(session):
    prediction = _make_prediction(session, "F1")
    _add_price(session, prediction, 1, open_=Decimal("106"), high=Decimal("107"), low=Decimal("105"), close=Decimal("106"))
    evaluate_recommendation(session, prediction)
    assessment = assess_prediction_usefulness(session, prediction, assessed_at=AS_OF)

    assessment.usefulness_verdict = NOT_USEFUL
    with pytest.raises(PredictionUsefulnessAssessmentImmutableError):
        session.commit()
    session.rollback()


def test_report_insufficient_sample(session):
    prediction = _make_prediction(session, "G1")
    _add_price(session, prediction, 1, open_=Decimal("106"), high=Decimal("107"), low=Decimal("105"), close=Decimal("106"))
    evaluate_recommendation(session, prediction)

    report = compute_horizon_usefulness_report(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)

    assert report.verdict == REPORT_VERDICT_INSUFFICIENT_SAMPLE
    assert report.avg_risk_adjusted_ratio is None
    assert report.useful_rate is None


def test_report_measures_useful_rate_correctly(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON
    useful_count = 15
    for i in range(total):
        prediction = _make_prediction(session, f"H{i}")
        if i < useful_count:
            _add_price(session, prediction, 1, open_=Decimal("106"), high=Decimal("107"), low=Decimal("100"), close=Decimal("106"))
        else:
            _add_price(session, prediction, 1, open_=Decimal("95"), high=Decimal("96"), low=Decimal("94"), close=Decimal("95"))
        evaluate_recommendation(session, prediction)

    report = compute_horizon_usefulness_report(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)

    assert report.verdict == REPORT_VERDICT_MEASURED
    assert report.sample_count == total
    assert report.useful_rate == Decimal(useful_count) / Decimal(total)

    history = get_usefulness_report_history(session, model_version=MODEL_VERSION, horizon_days=1)
    assert history[-1].id == report.id


def test_never_writes_to_predictions(session):
    prediction = _make_prediction(session, "I1")
    _add_price(session, prediction, 1, open_=Decimal("106"), high=Decimal("107"), low=Decimal("105"), close=Decimal("106"))
    evaluate_recommendation(session, prediction)
    before = (prediction.confidence, prediction.opportunity_score)

    assess_prediction_usefulness(session, prediction, assessed_at=AS_OF)
    compute_horizon_usefulness_report(session, model_version=MODEL_VERSION, horizon_days=1, computed_at=AS_OF)

    after = (prediction.confidence, prediction.opportunity_score)
    assert before == after
