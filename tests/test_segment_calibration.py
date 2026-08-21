from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.calibration import INSUFFICIENT_SAMPLE, OVERCONFIDENT, UNDERCONFIDENT, WELL_CALIBRATED
from app.db import Base
from app.models import DailyCandidateScan, Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate, Stock
from app.segment_calibration import (
    SEGMENT_CALIBRATION_VERSION,
    SEGMENT_GLOBAL,
    SEGMENT_SECTOR,
    SEGMENT_STOCK,
    assess_segment_calibration,
    get_segment_calibration_history,
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


def _make_evaluated_prediction(
    session, *, sector="TECH", market_cap=Decimal("5000000000"), outcome, predicted_probability=Decimal("0.5"),
    horizon_days=1, sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.10"), stock=None, link_setup=True,
):
    n = next(_counter)
    scan_date = date(2027, 1, 1) + timedelta(days=n)
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    if stock is None:
        stock = Stock(symbol=f"S{n}", exchange="NSE", sector=sector, market_cap=market_cap, is_active=True)
        session.add(stock)
        session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=predicted_probability, confidence=Decimal("0.8"),
        sma20_distance=sma20_distance if link_setup else None, volume_ratio_20d=volume_ratio_20d if link_setup else None,
        atr_percent=Decimal("0.03"), data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=horizon_days,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=predicted_probability,
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
    return prediction, stock


def test_resolves_to_stock_level_when_stock_has_enough_samples(session):
    target, stock = _make_evaluated_prediction(session, outcome="SUCCESS", predicted_probability=Decimal("0.5"))
    for _ in range(29):
        _make_evaluated_prediction(session, outcome="SUCCESS", predicted_probability=Decimal("0.5"), stock=stock)

    assessment = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    assert assessment.resolved_segment_level == SEGMENT_STOCK
    assert assessment.resolved_sample_count == 30
    assert assessment.calibration_rule_version == SEGMENT_CALIBRATION_VERSION


def test_falls_back_to_sector_when_stock_sparse(session):
    target, stock = _make_evaluated_prediction(
        session, sector="PHARMA", outcome="SUCCESS", predicted_probability=Decimal("0.5"),
        sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.10"),
    )
    # 29 more distinct stocks, same sector, but a different SETUP bucket
    # (WEAK/LOW instead of MODERATE/NORMAL) -- stock- and setup-level
    # samples stay at 1 for the target's own segment; only sector accumulates.
    for _ in range(29):
        _make_evaluated_prediction(
            session, sector="PHARMA", outcome="SUCCESS", predicted_probability=Decimal("0.5"),
            sma20_distance=Decimal("0.01"), volume_ratio_20d=Decimal("0.50"),
        )

    assessment = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    assert assessment.resolved_segment_level == SEGMENT_SECTOR
    assert assessment.resolved_segment_key == "PHARMA"
    assert assessment.resolved_sample_count == 30


def test_falls_back_to_global_when_nothing_sufficient(session):
    target, _stock = _make_evaluated_prediction(session, sector="UNIQUE_SECTOR_A", outcome="SUCCESS")
    # Fewer than 30 total evaluated predictions anywhere -> even GLOBAL is insufficient.
    for _ in range(10):
        _make_evaluated_prediction(session, sector="UNIQUE_SECTOR_B", outcome="SUCCESS")

    assessment = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    assert assessment.resolved_segment_level == SEGMENT_GLOBAL
    assert assessment.verdict == INSUFFICIENT_SAMPLE
    assert assessment.predicted_mean is None


def test_well_calibrated_verdict(session):
    target, stock = _make_evaluated_prediction(session, outcome="SUCCESS", predicted_probability=Decimal("0.5"))
    for i in range(14):
        _make_evaluated_prediction(session, outcome="SUCCESS", predicted_probability=Decimal("0.5"), stock=stock)
    for i in range(15):
        _make_evaluated_prediction(session, outcome="FAILURE", predicted_probability=Decimal("0.5"), stock=stock)

    assessment = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    assert assessment.resolved_segment_level == SEGMENT_STOCK
    assert assessment.verdict == WELL_CALIBRATED


def test_underconfident_verdict_when_observed_exceeds_predicted(session):
    target, stock = _make_evaluated_prediction(session, outcome="SUCCESS", predicted_probability=Decimal("0.3"))
    for _ in range(29):
        _make_evaluated_prediction(session, outcome="SUCCESS", predicted_probability=Decimal("0.3"), stock=stock)

    assessment = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    # predicted_mean=0.3, observed_rate=1.0 -> error=+0.7 -> UNDERCONFIDENT
    assert assessment.verdict == UNDERCONFIDENT


def test_overconfident_verdict_when_observed_below_predicted(session):
    target, stock = _make_evaluated_prediction(session, outcome="FAILURE", predicted_probability=Decimal("0.9"))
    for _ in range(29):
        _make_evaluated_prediction(session, outcome="FAILURE", predicted_probability=Decimal("0.9"), stock=stock)

    assessment = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    assert assessment.verdict == OVERCONFIDENT


def test_setup_skipped_when_target_has_no_scan_candidate_data(session):
    target, stock = _make_evaluated_prediction(session, outcome="SUCCESS", link_setup=False)
    for _ in range(29):
        _make_evaluated_prediction(session, outcome="SUCCESS", stock=stock)

    assessment = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    setup_entry = next(e for e in assessment.fallback_chain if e["level"] == "SETUP")
    assert setup_entry["skipped"] is True
    assert setup_entry["key"] is None


def test_idempotent(session):
    target, stock = _make_evaluated_prediction(session, outcome="SUCCESS")
    for _ in range(29):
        _make_evaluated_prediction(session, outcome="SUCCESS", stock=stock)

    first = assess_segment_calibration(session, target, evaluated_at=AS_OF)
    second = assess_segment_calibration(session, target, evaluated_at=AS_OF)

    assert first.id == second.id
    assert len(get_segment_calibration_history(session, target.id)) == 1
