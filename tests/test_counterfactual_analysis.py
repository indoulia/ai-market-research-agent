from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.counterfactual_analysis import (
    COUNTERFACTUAL_ANALYSIS_VERSION,
    backfill_counterfactual_outcomes,
    compare_published_vs_suppressed,
    get_counterfactual_report_history,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import (
    DailyCandidateScan,
    MarketPrice,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    RecommendationSelection,
    ScanCandidate,
    Stock,
)
from app.out_of_sample_validation import EvaluationWindow
from app.trust_report import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
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


def _make_qualified_prediction(session, *, symbol=None, selected=None):
    n = next(_counter)
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1) + timedelta(days=n), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol or f"S{n}", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"),
        close=Decimal("100"), volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.1"), atr_percent=Decimal("0.02"),
        data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)

    if selected is not None:
        session.add(RecommendationSelection(
            scan_id=scan.id, recommendation_generation_id=generation.id, rank=(1 if selected else None),
            selected=selected, selection_reason=("SELECTED" if selected else "BELOW_MIN_SCORE"), selection_rule_version="RSL-001",
        ))
        session.commit()

    return scan, prediction, generation


def test_backfill_evaluates_unselected_qualified_prediction(session):
    scan, prediction, generation = _make_qualified_prediction(session, selected=False)
    for day in range(1, prediction.horizon_days + 1):
        session.add(MarketPrice(
            stock_id=prediction.stock_id, timestamp=AS_OF + timedelta(days=day), open=Decimal("100"), high=Decimal("106"),
            low=Decimal("99"), close=Decimal("105"), volume=1000, source="test",
        ))
    session.commit()

    outcomes = backfill_counterfactual_outcomes(session, scan.id)

    assert len(outcomes) == 1
    assert outcomes[0].outcome == "SUCCESS"
    stored = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id))
    assert stored is not None


def test_backfill_skips_when_insufficient_market_data(session):
    scan, prediction, generation = _make_qualified_prediction(session, selected=False)
    # No future MarketPrice row added -- horizon hasn't elapsed yet.

    outcomes = backfill_counterfactual_outcomes(session, scan.id)

    assert outcomes == ()


def test_backfill_skips_already_evaluated(session):
    scan, prediction, generation = _make_qualified_prediction(session, selected=False)
    for day in range(1, prediction.horizon_days + 1):
        session.add(MarketPrice(
            stock_id=prediction.stock_id, timestamp=AS_OF + timedelta(days=day), open=Decimal("100"), high=Decimal("106"),
            low=Decimal("99"), close=Decimal("105"), volume=1000, source="test",
        ))
    session.commit()

    first = backfill_counterfactual_outcomes(session, scan.id)
    second = backfill_counterfactual_outcomes(session, scan.id)

    assert len(first) == 1
    assert second == ()


def test_compare_insufficient_sample(session):
    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))

    report = compare_published_vs_suppressed(session, window=window, computed_at=AS_OF)

    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert report.opportunity_cost_total == Decimal("0")
    assert report.report_rule_version == COUNTERFACTUAL_ANALYSIS_VERSION


def _add_outcome_row(session, *, selected, outcome, actual_return):
    n = next(_counter)
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1) + timedelta(days=n), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=f"O{n}", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.1"), atr_percent=Decimal("0.02"),
        data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.flush()
    generation = RecommendationGeneration(
        scan_candidate_id=candidate.id, outcome="QUALIFIED", consensus_contract_version="CC-001",
        failed_criteria=None, prediction_id=prediction.id,
    )
    session.add(generation)
    session.flush()
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("95"),
        closing_price=Decimal("105"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.05"),
        actual_return=actual_return, prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
        stop_hit=(outcome == "FAILURE"), outcome=outcome,
    ))
    session.add(RecommendationSelection(
        scan_id=scan.id, recommendation_generation_id=generation.id, rank=(1 if selected else None),
        selected=selected, selection_reason=("SELECTED" if selected else "BELOW_MIN_SCORE"), selection_rule_version="RSL-001",
    ))
    session.commit()


def test_compare_computes_opportunity_cost_and_avoided_loss(session):
    for _ in range(20):
        _add_outcome_row(session, selected=True, outcome="SUCCESS", actual_return=Decimal("0.05"))
    for _ in range(10):
        _add_outcome_row(session, selected=False, outcome="SUCCESS", actual_return=Decimal("0.05"))
    for _ in range(10):
        _add_outcome_row(session, selected=False, outcome="FAILURE", actual_return=Decimal("-0.03"))

    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))
    report = compare_published_vs_suppressed(session, window=window, computed_at=AS_OF)

    assert report.published_sample_count == 20
    assert report.suppressed_sample_count == 20
    assert report.opportunity_cost_total == Decimal("0.50")  # 10 * 0.05
    assert report.avoided_loss_total == Decimal("0.30")  # 10 * 0.03
    assert report.verdict == VERDICT_OK  # published 100% vs suppressed 50% -- published clearly ahead


def test_compare_weak_when_suppressed_outperforms(session):
    for _ in range(20):
        _add_outcome_row(session, selected=True, outcome="FAILURE", actual_return=Decimal("-0.03"))
    for _ in range(20):
        _add_outcome_row(session, selected=False, outcome="SUCCESS", actual_return=Decimal("0.05"))

    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))
    report = compare_published_vs_suppressed(session, window=window, computed_at=AS_OF)

    assert report.verdict == VERDICT_WEAK


def test_report_history_accumulates(session):
    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))

    compare_published_vs_suppressed(session, window=window, computed_at=AS_OF)
    compare_published_vs_suppressed(session, window=window, computed_at=AS_OF + timedelta(days=1))

    assert len(get_counterfactual_report_history(session)) == 2
