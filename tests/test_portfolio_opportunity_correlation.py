from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_quality import QUALITY_HIGH
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_SUFFICIENT
from app.execution_cost_model import assess_execution_cost
from app.models import (
    DailyCandidateScan,
    EvidenceQualityDecision,
    MarketPrice,
    Prediction,
    PredictionOutcome,
    PredictionTrustScore,
    ScanCandidate,
    Stock,
    UserPreference,
)
from app.opportunity_ranking import rank_positive_opportunities
from app.out_of_sample_validation import EvaluationWindow
from app.portfolio_opportunity_correlation import (
    REASON_HIGH_CORRELATION,
    REASON_NOT_PREFERRED_SECTOR,
    REASON_SECTOR_CONCENTRATION,
    VERDICT_INSUFFICIENT_SAMPLE,
    apply_portfolio_adjustment,
    assess_portfolio_correlation,
    get_utility_history,
    measure_portfolio_selection_effectiveness,
)
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
_scan_counter = iter(range(1000000))


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
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _add_price_series(session, stock_id, closes, *, end=AS_OF):
    n = len(closes)
    for offset, close in enumerate(closes):
        ts = end - timedelta(days=(n - offset))
        close = Decimal(str(close))
        session.add(MarketPrice(
            stock_id=stock_id, timestamp=ts,
            open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
            volume=1000, source="test",
        ))
    session.flush()


def _make_qualified_prediction(session, scan, symbol, *, sector=None, closes=None):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector)
    session.add(stock)
    session.flush()
    if closes is not None:
        _add_price_series(session, stock.id, closes)
    else:
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
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id), stock


def _gate_pass(session, prediction):
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=STATE_SUFFICIENT, available_category_count=2, stale_category_count=0,
        unavailable_category_count=3, categories_considered=["TECHNICAL_VOLUME", "NEWS"], leaked_categories=[],
        reasons=[], confidence_adjustment_ceiling=prediction.confidence, blocks_publication=False,
        evaluated_at=AS_OF, gate_rule_version=EVIDENCE_QUALITY_GATE_VERSION,
    ))
    session.add(PredictionTrustScore(
        prediction_id=prediction.id, overall_trust_score=Decimal("0.9"), trust_quality=QUALITY_HIGH,
        calibration_component=None, historical_accuracy_component=None, recent_performance_component=None,
        horizon_reliability_component=None, regime_reliability_component=None, evidence_quality_component=None,
        available_component_count=1, reasons=[], computed_at=AS_OF, trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    ))
    session.commit()
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)


def test_high_price_correlation_and_same_sector_flags_near_duplicate(session):
    scan = _make_scan(session)
    trend = [100 + i * 0.5 for i in range(70)]
    prediction_a, stock_a = _make_qualified_prediction(session, scan, "AAA", sector="IT", closes=trend)
    prediction_b, stock_b = _make_qualified_prediction(session, scan, "BBB", sector="IT", closes=trend)
    _gate_pass(session, prediction_a)
    _gate_pass(session, prediction_b)
    rank_positive_opportunities(session, [prediction_a.id, prediction_b.id], evaluated_at=AS_OF)

    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)

    assert report.candidate_count == 2
    assert report.sector_concentration == {"IT": 2}
    assert len(report.high_correlation_pairs) == 1
    assert set(report.near_duplicate_stock_ids) == {stock_a.id, stock_b.id}


def test_different_sectors_uncorrelated_series_no_flags(session):
    scan = _make_scan(session)
    trend_up = [100 + i * 0.5 for i in range(70)]
    oscillating = [100 if i % 2 == 0 else 102 for i in range(70)]
    prediction_a, _stock_a = _make_qualified_prediction(session, scan, "AAA", sector="IT", closes=trend_up)
    prediction_b, _stock_b = _make_qualified_prediction(session, scan, "BBB", sector="PHARMA", closes=oscillating)
    _gate_pass(session, prediction_a)
    _gate_pass(session, prediction_b)
    rank_positive_opportunities(session, [prediction_a.id, prediction_b.id], evaluated_at=AS_OF)

    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)

    assert report.high_correlation_pairs == []
    assert report.near_duplicate_stock_ids == []


def test_correlation_report_is_idempotent(session):
    scan = _make_scan(session)
    prediction_a, _stock_a = _make_qualified_prediction(session, scan, "AAA", sector="IT")
    _gate_pass(session, prediction_a)
    rank_positive_opportunities(session, [prediction_a.id], evaluated_at=AS_OF)

    first = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)
    second = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)

    assert first.id == second.id


def test_sector_concentration_applies_penalty_without_touching_raw_ranking(session):
    scan = _make_scan(session)
    trend_a = [100 + i * 0.5 for i in range(70)]
    trend_b = [150 - i * 0.2 for i in range(70)]
    trend_c = [80 + (i % 5) for i in range(70)]
    predictions = []
    for symbol, sector, trend in [("AAA", "IT", trend_a), ("BBB", "IT", trend_b), ("CCC", "AUTO", trend_c)]:
        prediction, _stock = _make_qualified_prediction(session, scan, symbol, sector=sector, closes=trend)
        _gate_pass(session, prediction)
        predictions.append(prediction)
    rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=AS_OF)
    raw_scores_before = {
        p.id: rank.composite_score
        for p, rank in zip(predictions, rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=AS_OF))
    }

    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)
    assessments = apply_portfolio_adjustment(session, scan.id, evaluated_at=AS_OF, correlation_report=report)

    by_prediction = {a.prediction_id: a for a in assessments}
    it_assessments = [a for a in assessments if a.sector == "IT"]
    assert len(it_assessments) == 2
    assert all(REASON_SECTOR_CONCENTRATION in a.penalty_reasons for a in it_assessments)
    for a in it_assessments:
        assert a.adjusted_utility < a.base_utility

    # Raw M1.87 ranking untouched.
    final_scores = {
        p.id: rank.composite_score
        for p, rank in zip(predictions, rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=AS_OF))
    }
    assert final_scores == raw_scores_before


def test_utility_assessment_is_idempotent(session):
    scan = _make_scan(session)
    prediction, _stock = _make_qualified_prediction(session, scan, "AAA", sector="IT")
    _gate_pass(session, prediction)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)
    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)

    first = apply_portfolio_adjustment(session, scan.id, evaluated_at=AS_OF, correlation_report=report)
    second = apply_portfolio_adjustment(session, scan.id, evaluated_at=AS_OF, correlation_report=report)

    assert [a.id for a in first] == [a.id for a in second]
    assert len(get_utility_history(session, prediction.id)) == 1


def test_user_preference_excludes_non_preferred_sector_without_affecting_global_ranking(session):
    scan = _make_scan(session)
    prediction, _stock = _make_qualified_prediction(session, scan, "AAA", sector="PHARMA")
    _gate_pass(session, prediction)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)
    original_ranking = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)[0]

    session.add(UserPreference(
        user_id="user-1", horizon_band="SHORT", custom_horizon_days=None, risk_preference="MODERATE",
        min_confidence_threshold=Decimal("0.5"), preferred_sectors=["IT", "AUTO"], preferred_market_cap_buckets=None,
        effective_at=AS_OF, preference_rule_version="UP-001",
    ))
    session.commit()

    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)
    assessments = apply_portfolio_adjustment(session, scan.id, evaluated_at=AS_OF, correlation_report=report, user_id="user-1")

    assessment = assessments[0]
    assert assessment.included is False
    assert REASON_NOT_PREFERRED_SECTOR in assessment.penalty_reasons
    # Global ranking (no user scoping) is unaffected.
    assert original_ranking.included is True
    assert original_ranking.composite_score is not None


def test_base_utility_falls_back_to_raw_composite_score_without_cost_assessment(session):
    scan = _make_scan(session)
    prediction, _stock = _make_qualified_prediction(session, scan, "AAA", sector="IT")
    _gate_pass(session, prediction)
    ranking = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)[0]

    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)
    assessments = apply_portfolio_adjustment(session, scan.id, evaluated_at=AS_OF, correlation_report=report)

    assert assessments[0].base_utility == ranking.composite_score


def test_base_utility_scales_down_by_execution_cost_efficiency_when_available(session):
    scan = _make_scan(session)
    prediction, _stock = _make_qualified_prediction(session, scan, "AAA", sector="IT")
    _gate_pass(session, prediction)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)

    outcome = PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("106"), lowest_price=Decimal("99"),
        closing_price=Decimal("105"), maximum_return=Decimal("0.06"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.05"), prediction_error=Decimal("0"), target_hit=True, stop_hit=False,
        outcome="SUCCESS", label_methodology_version=None,
    )
    session.add(outcome)
    session.commit()
    assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)
    assessments = apply_portfolio_adjustment(session, scan.id, evaluated_at=AS_OF, correlation_report=report)

    ranking = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)[0]
    assert assessments[0].base_utility <= ranking.composite_score


def test_selection_effectiveness_insufficient_sample_when_below_minimum(session):
    scan = _make_scan(session)
    prediction, _stock = _make_qualified_prediction(session, scan, "AAA", sector="IT")
    _gate_pass(session, prediction)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)
    report = assess_portfolio_correlation(session, scan.id, evaluated_at=AS_OF)
    apply_portfolio_adjustment(session, scan.id, evaluated_at=AS_OF, correlation_report=report)

    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=365))
    result = measure_portfolio_selection_effectiveness(session, window=window, top_k=5, computed_at=AS_OF)

    assert result.verdict == VERDICT_INSUFFICIENT_SAMPLE
