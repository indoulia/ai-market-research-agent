from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.horizon_regime_trust import HORIZON_REGIME_TRUST_VERSION, SEGMENT_COMBINED, VERDICT_SUFFICIENT
from app.models import (
    DailyCandidateScan,
    HorizonRegimeTrust,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
    Stock,
)
from app.stock_behavior_learning import (
    LEVEL_GLOBAL,
    LEVEL_GLOBAL_HORIZON_REGIME,
    LEVEL_STOCK_HORIZON,
    LEVEL_STOCK_HORIZON_REGIME,
    STOCK_BEHAVIOR_VERSION,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_MEASURED,
    assess_stock_behavior,
    get_stock_behavior_history,
)

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


def _make_evaluated_prediction(session, *, stock, horizon_days, outcome, bullish=True):
    n = next(_counter)
    scan_date = date(2027, 1, 1) + timedelta(days=n)
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), sma20_distance=Decimal("0.05") if bullish else Decimal("-0.05"),
        volume_ratio_20d=Decimal("1.1"), atr_percent=Decimal("0.01"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=horizon_days,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.flush()
    session.add(RecommendationGeneration(
        scan_candidate_id=candidate.id, outcome="QUALIFIED", consensus_contract_version="CC-001",
        failed_criteria=None, prediction_id=prediction.id,
    ))
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
        closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
        stop_hit=(outcome == "FAILURE"), outcome=outcome,
    ))
    session.commit()
    return prediction


@pytest.fixture
def stock(session):
    s = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(s)
    session.commit()
    return s


def test_resolves_stock_horizon_regime_when_sufficient(session, stock):
    for _ in range(20):
        _make_evaluated_prediction(session, stock=stock, horizon_days=5, outcome="SUCCESS", bullish=True)

    assessment = assess_stock_behavior(
        session, stock_id=stock.id, model_version=MODEL_VERSION, horizon_days=5, regime="BULLISH_LOW_VOL", evaluated_at=AS_OF,
    )

    assert assessment.resolved_level == LEVEL_STOCK_HORIZON_REGIME
    assert assessment.resolved_sample_count == 20
    assert assessment.observed_success_rate == Decimal("1")
    assert assessment.verdict == VERDICT_MEASURED
    assert assessment.behavior_rule_version == STOCK_BEHAVIOR_VERSION


def test_falls_back_to_stock_horizon_when_regime_sparse(session, stock):
    for _ in range(10):
        _make_evaluated_prediction(session, stock=stock, horizon_days=5, outcome="SUCCESS", bullish=True)
    for _ in range(10):
        _make_evaluated_prediction(session, stock=stock, horizon_days=5, outcome="FAILURE", bullish=False)

    assessment = assess_stock_behavior(
        session, stock_id=stock.id, model_version=MODEL_VERSION, horizon_days=5, regime="BULLISH_LOW_VOL", evaluated_at=AS_OF,
    )

    assert assessment.resolved_level == LEVEL_STOCK_HORIZON
    assert assessment.resolved_sample_count == 20


def test_falls_back_to_global_horizon_regime_via_m179(session, stock):
    session.add(HorizonRegimeTrust(
        model_version=MODEL_VERSION, segment_type=SEGMENT_COMBINED, horizon_days=5, regime="BULLISH_LOW_VOL",
        sample_count=25, success_rate=Decimal("0.6"), success_rate_standard_error=Decimal("0.05"),
        verdict=VERDICT_SUFFICIENT, is_low_trust=False, computed_at=AS_OF, trust_rule_version=HORIZON_REGIME_TRUST_VERSION,
    ))
    session.commit()

    assessment = assess_stock_behavior(
        session, stock_id=stock.id, model_version=MODEL_VERSION, horizon_days=5, regime="BULLISH_LOW_VOL", evaluated_at=AS_OF,
    )

    assert assessment.resolved_level == LEVEL_GLOBAL_HORIZON_REGIME
    assert assessment.resolved_sample_count == 25
    assert assessment.observed_success_rate == Decimal("0.6")


def test_falls_back_to_global_when_nothing_sufficient(session, stock):
    assessment = assess_stock_behavior(
        session, stock_id=stock.id, model_version=MODEL_VERSION, horizon_days=5, regime="BULLISH_LOW_VOL", evaluated_at=AS_OF,
    )

    assert assessment.resolved_level == LEVEL_GLOBAL
    assert assessment.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert assessment.observed_success_rate is None


def test_regime_none_skips_regime_specific_levels(session, stock):
    for _ in range(20):
        _make_evaluated_prediction(session, stock=stock, horizon_days=5, outcome="SUCCESS", bullish=True)

    assessment = assess_stock_behavior(
        session, stock_id=stock.id, model_version=MODEL_VERSION, horizon_days=5, regime=None, evaluated_at=AS_OF,
    )

    levels_considered = [entry["level"] for entry in assessment.fallback_chain]
    assert LEVEL_STOCK_HORIZON_REGIME not in levels_considered
    assert LEVEL_GLOBAL_HORIZON_REGIME not in levels_considered
    assert assessment.resolved_level == LEVEL_STOCK_HORIZON


def test_idempotent(session, stock):
    for _ in range(20):
        _make_evaluated_prediction(session, stock=stock, horizon_days=5, outcome="SUCCESS", bullish=True)

    first = assess_stock_behavior(
        session, stock_id=stock.id, model_version=MODEL_VERSION, horizon_days=5, regime="BULLISH_LOW_VOL", evaluated_at=AS_OF,
    )
    second = assess_stock_behavior(
        session, stock_id=stock.id, model_version=MODEL_VERSION, horizon_days=5, regime="BULLISH_LOW_VOL", evaluated_at=AS_OF,
    )

    assert first.id == second.id
    assert len(get_stock_behavior_history(session, stock.id)) == 1
