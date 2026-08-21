from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.abstention_quality import (
    ABSTENTION_QUALITY_VERSION,
    SEGMENT_REGIME,
    evaluate_segment_abstention_quality,
    get_abstention_quality_report_history,
)
from app.db import Base
from app.models import DailyCandidateScan, Prediction, PredictionOutcome, RecommendationGeneration, RecommendationSelection, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.segment_calibration import GLOBAL_KEY, SEGMENT_GLOBAL, SEGMENT_SECTOR
from app.trust_report import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK

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


def _make_row(session, *, outcome, selected, sector="TECH", horizon_days=1, as_of=AS_OF, actual_return=None):
    n = next(_counter)
    scan_date = date(2027, 1, 1) + timedelta(days=n)
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=f"S{n}", exchange="NSE", sector=sector, is_active=True)
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
        stock_id=stock.id, as_of_timestamp=as_of, entry_price=Decimal("100"), horizon_days=horizon_days,
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
    ret = actual_return if actual_return is not None else (Decimal("0.05") if outcome == "SUCCESS" else Decimal("-0.03"))
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=as_of, highest_price=Decimal("110"), lowest_price=Decimal("95"),
        closing_price=Decimal("105"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.05"),
        actual_return=ret, prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
        stop_hit=(outcome == "FAILURE"), outcome=outcome,
    ))
    session.add(RecommendationSelection(
        scan_id=scan.id, recommendation_generation_id=generation.id, rank=(1 if selected else None),
        selected=selected, selection_reason=("SELECTED" if selected else "BELOW_MIN_SCORE"), selection_rule_version="RSL-001",
    ))
    session.commit()
    return prediction


def _make_group(session, *, sector, published_success, published_failure, suppressed_success, suppressed_failure):
    for _ in range(published_success):
        _make_row(session, outcome="SUCCESS", selected=True, sector=sector)
    for _ in range(published_failure):
        _make_row(session, outcome="FAILURE", selected=True, sector=sector)
    for _ in range(suppressed_success):
        _make_row(session, outcome="SUCCESS", selected=False, sector=sector)
    for _ in range(suppressed_failure):
        _make_row(session, outcome="FAILURE", selected=False, sector=sector)


def _entry(report, level, key):
    return next((e for e in report.segment_breakdown if e["segment_level"] == level and e["segment_key"] == key), None)


def test_sector_segment_ok_when_published_clearly_outperforms(session):
    _make_group(session, sector="TECH", published_success=15, published_failure=5, suppressed_success=10, suppressed_failure=10)

    report = evaluate_segment_abstention_quality(session, window=EvaluationWindow(label="all", start=None, end=None), computed_at=AS_OF)

    entry = _entry(report, SEGMENT_SECTOR, "TECH")
    assert entry is not None
    assert entry["published_sample_count"] == 20
    assert entry["suppressed_sample_count"] == 20
    assert entry["verdict"] == VERDICT_OK
    assert Decimal(entry["success_rate_delta"]) == Decimal("0.25")
    assert report.report_rule_version == ABSTENTION_QUALITY_VERSION


def test_segment_insufficient_sample_below_threshold(session):
    _make_group(session, sector="SMALLCAP", published_success=3, published_failure=2, suppressed_success=2, suppressed_failure=3)

    report = evaluate_segment_abstention_quality(session, window=EvaluationWindow(label="all", start=None, end=None), computed_at=AS_OF)

    entry = _entry(report, SEGMENT_SECTOR, "SMALLCAP")
    assert entry is not None
    assert entry["verdict"] == VERDICT_INSUFFICIENT_SAMPLE
    assert entry["success_rate_delta"] is None


def test_global_segment_aggregates_across_sectors(session):
    _make_group(session, sector="TECH", published_success=15, published_failure=5, suppressed_success=10, suppressed_failure=10)
    _make_group(session, sector="FIN", published_success=15, published_failure=5, suppressed_success=10, suppressed_failure=10)

    report = evaluate_segment_abstention_quality(session, window=EvaluationWindow(label="all", start=None, end=None), computed_at=AS_OF)

    entry = _entry(report, SEGMENT_GLOBAL, GLOBAL_KEY)
    assert entry is not None
    assert entry["published_sample_count"] == 40
    assert entry["suppressed_sample_count"] == 40
    assert report.sample_count == 80


def test_opportunity_cost_and_avoided_loss_totals(session):
    _make_row(session, outcome="SUCCESS", selected=False, sector="TECH", actual_return=Decimal("0.08"))
    _make_row(session, outcome="FAILURE", selected=False, sector="TECH", actual_return=Decimal("-0.04"))
    for _ in range(19):
        _make_row(session, outcome="SUCCESS", selected=False, sector="TECH")
    for _ in range(20):
        _make_row(session, outcome="SUCCESS", selected=True, sector="TECH")

    report = evaluate_segment_abstention_quality(session, window=EvaluationWindow(label="all", start=None, end=None), computed_at=AS_OF)

    entry = _entry(report, SEGMENT_SECTOR, "TECH")
    assert Decimal(entry["opportunity_cost_total"]) >= Decimal("0.08")
    assert Decimal(entry["avoided_loss_total"]) == Decimal("0.04")
    assert Decimal(entry["published_loss_total"]) == Decimal("0")


def test_published_loss_total_reflects_harmful_publication(session):
    for _ in range(15):
        _make_row(session, outcome="SUCCESS", selected=True, sector="TECH")
    for _ in range(5):
        _make_row(session, outcome="FAILURE", selected=True, sector="TECH", actual_return=Decimal("-0.03"))
    for _ in range(20):
        _make_row(session, outcome="SUCCESS", selected=False, sector="TECH")

    report = evaluate_segment_abstention_quality(session, window=EvaluationWindow(label="all", start=None, end=None), computed_at=AS_OF)

    entry = _entry(report, SEGMENT_SECTOR, "TECH")
    assert Decimal(entry["published_loss_total"]) == Decimal("0.15")


def test_regime_segment_is_populated(session):
    _make_group(session, sector="TECH", published_success=15, published_failure=5, suppressed_success=10, suppressed_failure=10)

    report = evaluate_segment_abstention_quality(session, window=EvaluationWindow(label="all", start=None, end=None), computed_at=AS_OF)

    regime_entries = [e for e in report.segment_breakdown if e["segment_level"] == SEGMENT_REGIME]
    assert regime_entries
    assert regime_entries[0]["published_sample_count"] + regime_entries[0]["suppressed_sample_count"] == 40


def test_window_excludes_predictions_outside_range(session):
    _make_group(session, sector="TECH", published_success=15, published_failure=5, suppressed_success=10, suppressed_failure=10)
    for _ in range(20):
        _make_row(session, outcome="SUCCESS", selected=True, sector="TECH", as_of=AS_OF + timedelta(days=365))

    report = evaluate_segment_abstention_quality(
        session, window=EvaluationWindow(label="narrow", start=AS_OF, end=AS_OF + timedelta(days=30)), computed_at=AS_OF
    )

    entry = _entry(report, SEGMENT_SECTOR, "TECH")
    assert entry["published_sample_count"] == 20


def test_report_history_accumulates(session):
    _make_group(session, sector="TECH", published_success=15, published_failure=5, suppressed_success=10, suppressed_failure=10)
    window = EvaluationWindow(label="all", start=None, end=None)

    first = evaluate_segment_abstention_quality(session, window=window, computed_at=AS_OF)
    second = evaluate_segment_abstention_quality(session, window=window, computed_at=AS_OF + timedelta(days=1))

    history = get_abstention_quality_report_history(session)
    assert [h.id for h in history] == [first.id, second.id]
