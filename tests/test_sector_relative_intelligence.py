from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DailyCandidateScan, Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.sector_relative_intelligence import (
    SECTOR_RELATIVE_VERSION,
    VERDICT_INSUFFICIENT_PEER_GROUP,
    VERDICT_IN_LINE_WITH_PEERS,
    VERDICT_STRONGER_THAN_PEERS,
    VERDICT_WEAKER_THAN_PEERS,
    assess_sector_relative_strength,
    compare_sector_performance,
    get_sector_relative_history,
)
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


def _make_scan_with_target_and_peers(session, *, target_momentum, peer_momenta, target_sector="TECH", peer_sector=None):
    n = next(_counter)
    scan = DailyCandidateScan(scan_date=AS_OF.date() + timedelta(days=n), universe_version="DCS-001", eligible_count=1 + len(peer_momenta), excluded_count=0)
    session.add(scan)
    session.flush()

    target_stock = Stock(symbol=f"T{n}", exchange="NSE", sector=target_sector, is_active=True)
    session.add(target_stock)
    session.flush()
    target_candidate = ScanCandidate(
        scan_id=scan.id, stock_id=target_stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), sma20_distance=target_momentum, volume_ratio_20d=Decimal("1.1"),
        atr_percent=Decimal("0.02"), data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(target_candidate)
    session.flush()
    prediction = Prediction(
        stock_id=target_stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.flush()
    session.add(RecommendationGeneration(
        scan_candidate_id=target_candidate.id, outcome="QUALIFIED", consensus_contract_version="CC-001",
        failed_criteria=None, prediction_id=prediction.id,
    ))

    for momentum in peer_momenta:
        pn = next(_counter)
        peer_stock = Stock(symbol=f"P{pn}", exchange="NSE", sector=peer_sector or target_sector, is_active=True)
        session.add(peer_stock)
        session.flush()
        session.add(ScanCandidate(
            scan_id=scan.id, stock_id=peer_stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
            confidence=Decimal("0.8"), sma20_distance=momentum, volume_ratio_20d=Decimal("1.1"), atr_percent=Decimal("0.02"),
            data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
        ))
    session.commit()
    return prediction


def test_insufficient_peer_group_when_too_few_peers(session):
    prediction = _make_scan_with_target_and_peers(session, target_momentum=Decimal("0.05"), peer_momenta=[Decimal("0.01")])

    assessment = assess_sector_relative_strength(session, prediction, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_INSUFFICIENT_PEER_GROUP
    assert assessment.peer_group_size == 1
    assert assessment.assessment_rule_version == SECTOR_RELATIVE_VERSION


def test_stronger_than_peers(session):
    prediction = _make_scan_with_target_and_peers(
        session, target_momentum=Decimal("0.20"), peer_momenta=[Decimal("0.01"), Decimal("0.02"), Decimal("0.00"), Decimal("0.01")],
    )

    assessment = assess_sector_relative_strength(session, prediction, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_STRONGER_THAN_PEERS
    assert assessment.peer_group_size == 4


def test_weaker_than_peers(session):
    prediction = _make_scan_with_target_and_peers(
        session, target_momentum=Decimal("-0.20"), peer_momenta=[Decimal("0.01"), Decimal("0.02"), Decimal("0.00"), Decimal("0.01")],
    )

    assessment = assess_sector_relative_strength(session, prediction, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_WEAKER_THAN_PEERS


def test_in_line_with_peers(session):
    prediction = _make_scan_with_target_and_peers(
        session, target_momentum=Decimal("0.015"), peer_momenta=[Decimal("0.01"), Decimal("0.02"), Decimal("0.00"), Decimal("0.03")],
    )

    assessment = assess_sector_relative_strength(session, prediction, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_IN_LINE_WITH_PEERS


def test_peer_group_excludes_different_sector(session):
    prediction = _make_scan_with_target_and_peers(
        session, target_momentum=Decimal("0.05"), peer_momenta=[Decimal("0.01"), Decimal("0.02"), Decimal("0.00")],
        target_sector="TECH", peer_sector="PHARMA",
    )

    assessment = assess_sector_relative_strength(session, prediction, evaluated_at=AS_OF)

    assert assessment.peer_group_size == 0
    assert assessment.verdict == VERDICT_INSUFFICIENT_PEER_GROUP


def test_idempotent(session):
    prediction = _make_scan_with_target_and_peers(
        session, target_momentum=Decimal("0.20"), peer_momenta=[Decimal("0.01"), Decimal("0.02"), Decimal("0.00")],
    )

    first = assess_sector_relative_strength(session, prediction, evaluated_at=AS_OF)
    second = assess_sector_relative_strength(session, prediction, evaluated_at=AS_OF)

    assert first.id == second.id
    assert len(get_sector_relative_history(session, prediction.id)) == 1


def _add_outcome(session, stock_sector, outcome):
    n = next(_counter)
    stock = Stock(symbol=f"O{n}", exchange="NSE", sector=stock_sector, is_active=True)
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
    session.commit()


def test_compare_sector_performance_insufficient_sample(session):
    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))

    report = compare_sector_performance(session, sector="TECH", window=window, computed_at=AS_OF)

    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_compare_sector_performance_weak_when_below_baseline(session):
    for _ in range(20):
        _add_outcome(session, "TECH", "FAILURE")
    for _ in range(20):
        _add_outcome(session, "PHARMA", "SUCCESS")

    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))
    report = compare_sector_performance(session, sector="TECH", window=window, computed_at=AS_OF)

    assert report.verdict == VERDICT_WEAK
    assert report.sector_success_rate == Decimal("0")


def test_compare_sector_performance_ok_when_in_line(session):
    for _ in range(20):
        _add_outcome(session, "TECH", "SUCCESS")
    for _ in range(20):
        _add_outcome(session, "PHARMA", "SUCCESS")

    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))
    report = compare_sector_performance(session, sector="TECH", window=window, computed_at=AS_OF)

    assert report.verdict == VERDICT_OK
