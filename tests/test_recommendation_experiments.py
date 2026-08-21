from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, PredictionOutcome, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.outcomes import evaluate_recommendation
from app.recommendation_experiments import (
    EXPERIMENT_FRAMEWORK_VERSION,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_READY,
    DuplicateExperimentArmNameError,
    DuplicateExperimentNameError,
    ExperimentArmImmutableError,
    ExperimentImmutableError,
    add_experiment_arm,
    compare_experiment,
    create_experiment,
    get_arm_results,
    run_experiment_arm,
)
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
WINDOW = EvaluationWindow(label="full-history", start=None, end=None)
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


def _make_scan(session, scan_date):
    scan_date = scan_date + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, as_of, win: bool, model_version=MODEL_VERSION):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=model_version, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
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
    evaluate_recommendation(session, prediction)
    return prediction


def _seed(session, *, scan_date, as_of, win_count, total, prefix, model_version=MODEL_VERSION):
    scan = _make_scan(session, scan_date)
    for i in range(total):
        _make_evaluated(session, scan, f"{prefix}{i}", as_of=as_of, win=(i < win_count), model_version=model_version)


def _new_experiment(session, name="exp-1"):
    return create_experiment(session, name=name, hypothesis="candidate model beats baseline")


def test_insufficient_sample_produces_no_unsafe_conclusion(session):
    experiment = _new_experiment(session)
    arm = add_experiment_arm(session, experiment_id=experiment.id, arm_name="empty", model_version=MODEL_VERSION, window=WINDOW)

    result = run_experiment_arm(session, arm.id, computed_at=datetime(2026, 7, 1, tzinfo=timezone.utc))

    assert result.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert result.sample_count == 0
    assert result.accuracy is None
    assert result.avg_return is None
    assert result.avg_drawdown is None
    assert result.calibration_error is None
    assert result.consistency_stdev is None
    assert result.framework_version == EXPERIMENT_FRAMEWORK_VERSION


def test_ready_verdict_with_correctly_computed_metrics(session):
    total = 40
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=24, total=total, prefix="A")

    experiment = _new_experiment(session)
    arm = add_experiment_arm(session, experiment_id=experiment.id, arm_name="candidate", model_version=MODEL_VERSION, window=WINDOW)
    result = run_experiment_arm(session, arm.id, computed_at=datetime(2026, 7, 1, tzinfo=timezone.utc))

    assert result.verdict == VERDICT_READY
    assert result.sample_count == total
    assert result.accuracy == Decimal("0.6")
    assert result.avg_return == pytest.approx(Decimal("0.018"))
    assert result.avg_drawdown == pytest.approx(Decimal("0.006"))
    assert result.calibration_error == pytest.approx(Decimal("0.456"))
    assert float(result.consistency_stdev) == pytest.approx(0.039192, abs=1e-4)
    assert result.arm_config_snapshot["model_version"] == MODEL_VERSION


def test_rerunning_an_arm_is_reproducible(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=total // 2, total=total, prefix="A")

    experiment = _new_experiment(session)
    arm = add_experiment_arm(session, experiment_id=experiment.id, arm_name="candidate", model_version=MODEL_VERSION, window=WINDOW)

    first = run_experiment_arm(session, arm.id, computed_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    second = run_experiment_arm(session, arm.id, computed_at=datetime(2026, 7, 2, tzinfo=timezone.utc))

    assert first.id != second.id
    assert first.accuracy == second.accuracy
    assert first.avg_return == second.avg_return
    assert first.avg_drawdown == second.avg_drawdown
    assert first.calibration_error == second.calibration_error
    assert first.consistency_stdev == second.consistency_stdev
    assert first.arm_config_snapshot == second.arm_config_snapshot
    assert len(get_arm_results(session, arm.id)) == 2


def test_duplicate_experiment_name_is_rejected(session):
    _new_experiment(session, name="dup")
    with pytest.raises(DuplicateExperimentNameError):
        _new_experiment(session, name="dup")


def test_duplicate_arm_name_is_rejected(session):
    experiment = _new_experiment(session)
    add_experiment_arm(session, experiment_id=experiment.id, arm_name="candidate", model_version=MODEL_VERSION, window=WINDOW)
    with pytest.raises(DuplicateExperimentArmNameError):
        add_experiment_arm(session, experiment_id=experiment.id, arm_name="candidate", model_version="other-model", window=WINDOW)


def test_experiment_config_is_immutable(session):
    experiment = _new_experiment(session)
    experiment.hypothesis = "changed after the fact"
    with pytest.raises(ExperimentImmutableError):
        session.commit()
    session.rollback()


def test_experiment_arm_config_is_immutable(session):
    experiment = _new_experiment(session)
    arm = add_experiment_arm(session, experiment_id=experiment.id, arm_name="candidate", model_version=MODEL_VERSION, window=WINDOW)
    arm.model_version = "swapped-model"
    with pytest.raises(ExperimentArmImmutableError):
        session.commit()
    session.rollback()


def test_compare_experiment_picks_best_ready_arm_by_accuracy(session):
    total = 40
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=30, total=total, prefix="A", model_version="strong-model")
    _seed(session, scan_date=date(2026, 3, 10), as_of=datetime(2026, 3, 10, tzinfo=timezone.utc), win_count=10, total=total, prefix="B", model_version="weak-model")

    experiment = _new_experiment(session)
    add_experiment_arm(session, experiment_id=experiment.id, arm_name="strong", model_version="strong-model", window=WINDOW)
    add_experiment_arm(session, experiment_id=experiment.id, arm_name="weak", model_version="weak-model", window=WINDOW)
    add_experiment_arm(session, experiment_id=experiment.id, arm_name="no-data", model_version="nonexistent-model", window=WINDOW)

    report = compare_experiment(session, experiment.id, computed_at=datetime(2026, 7, 1, tzinfo=timezone.utc))

    assert report.best_arm_name == "strong"
    assert len(report.arms) == 3
    by_name = {entry.arm_name: entry.result for entry in report.arms}
    assert by_name["no-data"].verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_running_experiments_never_writes_to_production_predictions(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=total, total=total, prefix="A")
    before_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    before_outcomes = {o.id: o.outcome for o in session.query(PredictionOutcome).all()}

    experiment = _new_experiment(session)
    arm = add_experiment_arm(session, experiment_id=experiment.id, arm_name="candidate", model_version=MODEL_VERSION, window=WINDOW)
    run_experiment_arm(session, arm.id, computed_at=datetime(2026, 7, 1, tzinfo=timezone.utc))

    after_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    after_outcomes = {o.id: o.outcome for o in session.query(PredictionOutcome).all()}
    assert before_predictions == after_predictions
    assert before_outcomes == after_outcomes
