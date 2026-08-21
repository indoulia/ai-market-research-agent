from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.feedback_experiment_pipeline import (
    FEEDBACK_EXPERIMENT_PIPELINE_VERSION,
    InsufficientFeedbackEvidenceError,
    create_experiment_from_feedback_signal,
    get_experiment_link_for_pattern,
    identify_recurring_feedback_patterns,
)
from app.feedback_learning_signals import compute_feedback_learning_signals
from app.models import DailyCandidateScan, MarketPrice, Prediction, PredictionOutcome, RecommendationFeedback, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation
from app.recommendation_experiments import Experiment, ExperimentArm, compare_experiment
from app.recommendation_feedback import CATEGORY_TARGET, REASON_AGREE, REASON_TOO_HIGH, submit_feedback
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
BASELINE_WINDOW = EvaluationWindow(label="baseline", start=datetime(2026, 1, 1, tzinfo=timezone.utc), end=datetime(2026, 1, 31, tzinfo=timezone.utc))
CANDIDATE_WINDOW = EvaluationWindow(label="candidate", start=datetime(2026, 6, 1, tzinfo=timezone.utc), end=datetime(2026, 6, 30, tzinfo=timezone.utc))


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
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, as_of, win: bool):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
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
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=as_of)
    return prediction


def _seed_recurring_pattern(session, *, scan_date, as_of, total, users_per_prediction):
    """Seeds `total` failing predictions, each given TOO_HIGH feedback from
    `users_per_prediction` distinct users, plus `total` succeeding
    predictions given AGREE feedback -- establishing a clear baseline
    success rate the TOO_HIGH group falls well below."""
    scan = _make_scan(session, scan_date)
    for i in range(total):
        prediction = _make_evaluated(session, scan, f"F{i}", as_of=as_of, win=False)
        for u in range(users_per_prediction):
            submit_feedback(session, prediction, user_id=f"fail-user-{i}-{u}", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=as_of)
    for i in range(total):
        prediction = _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True)
        submit_feedback(session, prediction, user_id=f"success-user-{i}", category=CATEGORY_TARGET, reason_code=REASON_AGREE, submitted_at=as_of)


def _too_high_signal(session):
    report = compute_feedback_learning_signals(session)
    matches = [s for s in report.signals if s.category == CATEGORY_TARGET and s.reason_code == REASON_TOO_HIGH]
    assert len(matches) == 1
    return matches[0]


def test_single_user_pattern_is_not_recurring(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed_recurring_pattern(session, scan_date=date(2026, 9, 1), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc), total=total, users_per_prediction=1)

    signal = _too_high_signal(session)
    assert signal.repeated_prediction_count == 0

    assert identify_recurring_feedback_patterns(session) == ()
    with pytest.raises(InsufficientFeedbackEvidenceError):
        create_experiment_from_feedback_signal(
            session, signal, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW, candidate_window=CANDIDATE_WINDOW
        )


def test_recurring_pattern_is_identified_and_creates_experiment(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed_recurring_pattern(session, scan_date=date(2026, 9, 1), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc), total=total, users_per_prediction=2)

    identified = identify_recurring_feedback_patterns(session)
    assert len(identified) == 1
    signal = identified[0]
    assert signal.category == CATEGORY_TARGET
    assert signal.reason_code == REASON_TOO_HIGH
    assert signal.repeated_prediction_count == total

    link = create_experiment_from_feedback_signal(
        session, signal, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW, candidate_window=CANDIDATE_WINDOW
    )

    assert link.feedback_category == CATEGORY_TARGET
    assert link.feedback_reason_code == REASON_TOO_HIGH
    assert link.pipeline_version == FEEDBACK_EXPERIMENT_PIPELINE_VERSION

    experiment = session.get(Experiment, link.experiment_id)
    assert CATEGORY_TARGET in experiment.hypothesis
    assert REASON_TOO_HIGH in experiment.hypothesis

    arms = session.query(ExperimentArm).filter_by(experiment_id=experiment.id).order_by(ExperimentArm.id.asc()).all()
    assert [a.arm_name for a in arms] == ["baseline", "candidate"]
    assert all(a.model_version == MODEL_VERSION for a in arms)


def test_pipeline_is_idempotent_across_runs(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed_recurring_pattern(session, scan_date=date(2026, 9, 1), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc), total=total, users_per_prediction=2)
    signal = _too_high_signal(session)

    first = create_experiment_from_feedback_signal(
        session, signal, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW, candidate_window=CANDIDATE_WINDOW
    )
    second = create_experiment_from_feedback_signal(
        session, signal, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW, candidate_window=CANDIDATE_WINDOW
    )

    assert first.id == second.id
    assert first.experiment_id == second.experiment_id
    assert session.query(Experiment).count() == 1
    assert session.query(ExperimentArm).count() == 2


def test_experiment_uses_m1_68_comparison_framework(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed_recurring_pattern(session, scan_date=date(2026, 9, 1), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc), total=total, users_per_prediction=2)
    signal = _too_high_signal(session)

    link = create_experiment_from_feedback_signal(
        session, signal, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW, candidate_window=CANDIDATE_WINDOW
    )

    report = compare_experiment(session, link.experiment_id, computed_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    assert {entry.arm_name for entry in report.arms} == {"baseline", "candidate"}


def test_lookup_by_pattern_returns_existing_link(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed_recurring_pattern(session, scan_date=date(2026, 9, 1), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc), total=total, users_per_prediction=2)
    signal = _too_high_signal(session)
    created = create_experiment_from_feedback_signal(
        session, signal, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW, candidate_window=CANDIDATE_WINDOW
    )

    found = get_experiment_link_for_pattern(session, feedback_category=CATEGORY_TARGET, feedback_reason_code=REASON_TOO_HIGH)
    assert found is not None
    assert found.id == created.id
    assert get_experiment_link_for_pattern(session, feedback_category=CATEGORY_TARGET, feedback_reason_code=REASON_AGREE) is None


def test_pipeline_never_writes_to_predictions_or_feedback(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed_recurring_pattern(session, scan_date=date(2026, 9, 1), as_of=datetime(2026, 9, 1, tzinfo=timezone.utc), total=total, users_per_prediction=2)
    signal = _too_high_signal(session)

    before_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    before_outcomes = {o.id: o.outcome for o in session.query(PredictionOutcome).all()}
    before_feedback_count = session.query(RecommendationFeedback).count()

    create_experiment_from_feedback_signal(
        session, signal, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW, candidate_window=CANDIDATE_WINDOW
    )

    after_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    after_outcomes = {o.id: o.outcome for o in session.query(PredictionOutcome).all()}
    after_feedback_count = session.query(RecommendationFeedback).count()

    assert before_predictions == after_predictions
    assert before_outcomes == after_outcomes
    assert before_feedback_count == after_feedback_count
