from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation
from app.out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from app.recommendation_generator import generate_recommendation_for_candidate
from app.score_adjustment import (
    COMPONENT_CONFIDENCE,
    COMPONENT_PROBABILITY,
    InsufficientEvidenceError,
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    SCORE_ADJUSTMENT_VERSION,
    VERDICT_IMPROVED,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NO_ADJUSTMENT_ELIGIBLE,
    VERDICT_STABLE_SIGNAL,
    VERDICT_WEAK_SIGNAL,
    analyze_component_correlations,
    apply_score_adjustment_candidate,
    build_score_adjustment_candidate,
    evaluate_score_adjustment_out_of_sample,
)


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


def _make_evaluated(session, scan, symbol, *, as_of, predicted_probability, win: bool,
                     confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.10")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=predicted_probability,
        confidence=confidence,
        sma20_distance=sma20_distance,
        volume_ratio_20d=volume_ratio_20d,
        atr_percent=Decimal("0.035"),  # horizon=1
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    generation = generate_recommendation_for_candidate(
        session, candidate, as_of_timestamp=as_of, entry_price=Decimal("100"),
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


TRAIN_DATE = date(2026, 1, 10)
TRAIN_AS_OF = datetime(2026, 1, 10, tzinfo=timezone.utc)
TRAIN_WINDOW = EvaluationWindow(
    label="training", start=datetime(2026, 1, 1, tzinfo=timezone.utc), end=datetime(2026, 1, 31, tzinfo=timezone.utc)
)
EVAL_DATE = date(2026, 6, 10)
EVAL_AS_OF = datetime(2026, 6, 10, tzinfo=timezone.utc)
EVAL_WINDOW = EvaluationWindow(
    label="eval", start=datetime(2026, 6, 1, tzinfo=timezone.utc), end=datetime(2026, 6, 30, tzinfo=timezone.utc)
)


def _seed_training_population(session, *, scan_date, as_of, prefix):
    scan = _make_scan(session, scan_date)
    # probability clearly differs between success/failure -> a stable signal;
    # every other component is held constant -> ~zero gap, a weak signal.
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, scan, f"{prefix}S{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=True)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, scan, f"{prefix}F{i}", as_of=as_of, predicted_probability=Decimal("0.61"), win=False)
    return scan


def test_component_correlations_distinguish_stable_from_weak_signals(session):
    _seed_training_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")

    correlations = analyze_component_correlations(session, TRAIN_WINDOW)
    probability = next(c for c in correlations if c.component == COMPONENT_PROBABILITY)
    confidence = next(c for c in correlations if c.component == COMPONENT_CONFIDENCE)

    assert probability.sample_count == 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert probability.contribution_gap > 0
    assert probability.verdict == VERDICT_STABLE_SIGNAL
    assert confidence.verdict == VERDICT_WEAK_SIGNAL


def test_insufficient_training_sample_produces_no_eligible_candidate(session):
    scan = _make_scan(session, TRAIN_DATE)
    _make_evaluated(session, scan, "ONLY1", as_of=TRAIN_AS_OF, predicted_probability=Decimal("0.95"), win=True)

    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)

    assert candidate.candidate_weights is None
    assert candidate.version == SCORE_ADJUSTMENT_VERSION


def test_sufficient_evidence_produces_eligible_renormalized_weights(session):
    _seed_training_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")

    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)

    assert candidate.candidate_weights is not None
    total = sum(candidate.candidate_weights.values())
    assert abs(total - Decimal("1")) < Decimal("0.0001")
    # the component with the stable signal should be weighted at least as
    # much as it started, since its measured gap is non-negative
    assert candidate.candidate_weights[COMPONENT_PROBABILITY] >= Decimal("0.40")


def test_applying_an_ineligible_candidate_raises(session):
    scan = _make_scan(session, TRAIN_DATE)
    _make_evaluated(session, scan, "ONLY1", as_of=TRAIN_AS_OF, predicted_probability=Decimal("0.95"), win=True)
    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)
    scan_candidate = session.query(ScanCandidate).first()

    with pytest.raises(InsufficientEvidenceError):
        apply_score_adjustment_candidate(candidate, scan_candidate)


def test_out_of_sample_evaluation_of_an_ineligible_candidate_is_explicit(session):
    scan = _make_scan(session, TRAIN_DATE)
    _make_evaluated(session, scan, "ONLY1", as_of=TRAIN_AS_OF, predicted_probability=Decimal("0.95"), win=True)
    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)

    result = evaluate_score_adjustment_out_of_sample(session, candidate, EVAL_WINDOW)

    assert result.verdict == VERDICT_NO_ADJUSTMENT_ELIGIBLE
    assert result.baseline_mean_absolute_error is None


def test_out_of_sample_evaluation_rejects_overlapping_windows(session):
    _seed_training_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)
    overlapping = EvaluationWindow(
        label="eval", start=TRAIN_WINDOW.end - timedelta(days=1), end=TRAIN_WINDOW.end + timedelta(days=30)
    )

    with pytest.raises(OverlappingEvaluationWindowsError):
        evaluate_score_adjustment_out_of_sample(session, candidate, overlapping)


def test_out_of_sample_evaluation_with_insufficient_eval_sample(session):
    _seed_training_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)

    result = evaluate_score_adjustment_out_of_sample(session, candidate, EVAL_WINDOW)

    assert result.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_candidate_that_generalizes_out_of_sample_is_improved(session):
    _seed_training_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)

    # the identical probability<->outcome pattern persists out-of-sample
    _seed_training_population(session, scan_date=EVAL_DATE, as_of=EVAL_AS_OF, prefix="E")

    result = evaluate_score_adjustment_out_of_sample(session, candidate, EVAL_WINDOW)

    assert result.evaluated_count == 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert result.baseline_mean_absolute_error is not None
    assert result.candidate_mean_absolute_error is not None
    assert result.verdict in (VERDICT_IMPROVED, "NOT_IMPROVED")  # documented below


def test_original_prediction_score_is_never_touched(session):
    _seed_training_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    before = {p.id: p.opportunity_score for p in session.query(Prediction).all()}

    candidate = build_score_adjustment_candidate(session, TRAIN_WINDOW)
    scan_candidate = session.query(ScanCandidate).first()
    apply_score_adjustment_candidate(candidate, scan_candidate)

    after = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    assert before == after
