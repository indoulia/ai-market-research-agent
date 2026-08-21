from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_quality import QUALITY_HIGH
from app.cross_sectional_ranking import (
    EFFECTIVENESS_RULE_VERSION,
    VERDICT_ALTERNATIVE_BETTER,
    VERDICT_COMPOSITE_BETTER,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NO_SIGNIFICANT_DIFFERENCE,
    measure_ranking_effectiveness,
    rank_scan_candidates,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_SUFFICIENT
from app.models import (
    DailyCandidateScan,
    EvidenceQualityDecision,
    MarketPrice,
    Prediction,
    PredictionOutcome,
    PositiveOpportunityRanking,
    PredictionTrustScore,
    RecommendationGeneration,
    RecommendationSelection,
    ScanCandidate,
    Stock,
)
from app.out_of_sample_validation import EvaluationWindow
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
WINDOW = EvaluationWindow(label="window", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=365))
_scan_counter = iter(range(1000000))
_stock_counter = iter(range(1000000))


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


def _make_qualified_prediction(session, scan, symbol):
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


def test_rank_scan_candidates_only_includes_qualified_candidates_of_that_scan(session):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=2, excluded_count=0)
    session.add(scan)
    session.flush()

    prediction_a = _make_qualified_prediction(session, scan, "AAA")
    prediction_b = _make_qualified_prediction(session, scan, "BBB")
    _gate_pass(session, prediction_a)
    _gate_pass(session, prediction_b)

    other_scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    other_scan = DailyCandidateScan(scan_date=other_scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(other_scan)
    session.flush()
    unrelated = _make_qualified_prediction(session, other_scan, "CCC")
    _gate_pass(session, unrelated)

    rows = rank_scan_candidates(session, scan.id, evaluated_at=AS_OF)

    assert {r.prediction_id for r in rows} == {prediction_a.id, prediction_b.id}
    assert all(r.included for r in rows)


def _make_composite_sample(session, *, count, outcome):
    for i in range(count):
        symbol = f"CS{next(_stock_counter)}"
        stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
        session.add(stock)
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
        session.add(PredictionOutcome(
            prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
            closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
            actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
            stop_hit=(outcome == "FAILURE"), outcome=outcome,
        ))
        session.add(PositiveOpportunityRanking(
            prediction_id=prediction.id, stock_id=stock.id, horizon_days=1, composite_score=Decimal("0.8"),
            expected_return_component=Decimal("0.05"), probability_component=Decimal("0.7"),
            trust_component=Decimal("0.9"), reward_risk_component=None, evidence_quality_component=Decimal("1"),
            stability_component=None, rank_position=1, included=True, exclusion_reason=None,
            evaluated_at=AS_OF, ranking_rule_version="OPR-001",
        ))
    session.commit()


def _make_alternative_sample(session, *, count, outcome):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=count, excluded_count=0)
    session.add(scan)
    session.flush()
    for i in range(count):
        symbol = f"AS{next(_stock_counter)}"
        stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
        session.add(stock)
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
        session.add(PredictionOutcome(
            prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
            closing_price=Decimal("108"), maximum_return=Decimal("0.08"), maximum_drawdown=Decimal("-0.01"),
            actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
            stop_hit=(outcome == "FAILURE"), outcome=outcome,
        ))
        candidate = ScanCandidate(
            scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
            predicted_probability=Decimal("0.7"), confidence=Decimal("0.8"), sma20_distance=Decimal("0.03"),
            volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
            model_version=MODEL_VERSION, feature_version="FV-001",
        )
        session.add(candidate)
        session.flush()
        generation = RecommendationGeneration(
            scan_candidate_id=candidate.id, outcome="QUALIFIED", consensus_contract_version="CC-001",
            failed_criteria=None, prediction_id=prediction.id,
        )
        session.add(generation)
        session.flush()
        session.add(RecommendationSelection(
            scan_id=scan.id, recommendation_generation_id=generation.id, rank=1, selected=True,
            selection_reason="SELECTED", selection_rule_version="RSL-001",
        ))
    session.commit()


def test_insufficient_sample_when_below_minimum(session):
    _make_composite_sample(session, count=5, outcome="SUCCESS")
    _make_alternative_sample(session, count=5, outcome="FAILURE")

    report = measure_ranking_effectiveness(session, window=WINDOW, top_k=1, computed_at=AS_OF)

    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert report.success_rate_delta is None
    assert report.effectiveness_rule_version == EFFECTIVENESS_RULE_VERSION


def test_composite_better_when_it_outperforms(session):
    _make_composite_sample(session, count=20, outcome="SUCCESS")
    _make_alternative_sample(session, count=20, outcome="FAILURE")

    report = measure_ranking_effectiveness(session, window=WINDOW, top_k=1, computed_at=AS_OF)

    assert report.verdict == VERDICT_COMPOSITE_BETTER
    assert report.composite_success_rate == Decimal("1")
    assert report.alternative_success_rate == Decimal("0")
    assert report.success_rate_delta == Decimal("1")


def test_alternative_better_when_composite_underperforms(session):
    _make_composite_sample(session, count=20, outcome="FAILURE")
    _make_alternative_sample(session, count=20, outcome="SUCCESS")

    report = measure_ranking_effectiveness(session, window=WINDOW, top_k=1, computed_at=AS_OF)

    assert report.verdict == VERDICT_ALTERNATIVE_BETTER


def test_no_significant_difference_when_rates_are_close(session):
    _make_composite_sample(session, count=10, outcome="SUCCESS")
    _make_composite_sample(session, count=10, outcome="FAILURE")
    _make_alternative_sample(session, count=10, outcome="SUCCESS")
    _make_alternative_sample(session, count=10, outcome="FAILURE")

    report = measure_ranking_effectiveness(session, window=WINDOW, top_k=1, computed_at=AS_OF)

    assert report.verdict == VERDICT_NO_SIGNIFICANT_DIFFERENCE
    assert report.composite_success_rate == Decimal("0.5")
    assert report.alternative_success_rate == Decimal("0.5")


def test_rank_position_beyond_top_k_excluded_from_composite_sample(session):
    _make_composite_sample(session, count=20, outcome="SUCCESS")
    _make_alternative_sample(session, count=20, outcome="SUCCESS")
    # Every composite row was created with rank_position=1; top_k=0 excludes all of them.
    report = measure_ranking_effectiveness(session, window=WINDOW, top_k=0, computed_at=AS_OF)

    assert report.composite_sample_count == 0
    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE
