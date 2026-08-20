from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from app.recommendation_generator import generate_recommendation_for_candidate
from app.regime_aware_scoring import (
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    REGIME_SCORE_ADJUSTMENT_VERSION,
    VERDICT_IMPROVED,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NO_ADJUSTMENT_ELIGIBLE,
    VERDICT_OVERCONFIDENT,
    VERDICT_WELL_CALIBRATED,
    analyze_regime_performance,
    apply_regime_score_adjustment,
    build_regime_score_adjustment_candidate,
    evaluate_regime_score_adjustment_out_of_sample,
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


def _make_scan(session, scan_date, eligible_count):
    scan = DailyCandidateScan(
        scan_date=scan_date, universe_version="DCS-001", eligible_count=eligible_count, excluded_count=0
    )
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, as_of, win: bool,
                     sma20_distance=Decimal("0.03"), atr_percent=Decimal("0.035")):
    """A BULLISH-breadth scan: every candidate has a positive sma20_distance,
    so every scan built by `_seed_regime_population` classifies as
    `BULLISH_HIGH_VOL` deterministically (atr_percent=0.035 is both >= M1.26's
    HIGH_VOLATILITY_ATR_THRESHOLD of 0.03 and the value that yields
    horizon_days=1)."""
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=sma20_distance,
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=atr_percent,  # horizon=1
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
    evaluate_recommendation(session, prediction)
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


def _seed_regime_population(session, *, scan_date, as_of, prefix, win_count=None):
    """Every candidate qualifies with the same fixed inputs, so
    `Prediction.opportunity_score` is identical for every row -- but the
    outcome win-rate is deliberately much lower than the score implies,
    producing a real, stable, OVERCONFIDENT miscalibration for this regime."""
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    if win_count is None:
        win_count = total // 8  # far fewer wins than the score implies
    scan = _make_scan(session, scan_date, eligible_count=total)
    for i in range(total):
        _make_evaluated(session, scan, f"{prefix}{i}", as_of=as_of, win=(i < win_count))
    return scan


def test_every_evaluated_prediction_gets_a_point_in_time_regime(session):
    _seed_regime_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")

    performance = analyze_regime_performance(session, TRAIN_WINDOW)

    assert len(performance) == 1
    assert performance[0].regime == "BULLISH_HIGH_VOL"
    assert performance[0].sample_count == 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON


def test_insufficient_sample_regime_is_not_eligible(session):
    scan = _make_scan(session, TRAIN_DATE, eligible_count=1)
    _make_evaluated(session, scan, "ONLY1", as_of=TRAIN_AS_OF, win=True)

    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)

    assert candidate.performance[0].verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert candidate.regime_offsets == {}


def test_stable_miscalibration_produces_an_eligible_offset(session):
    _seed_regime_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")

    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)

    assert candidate.performance[0].verdict == VERDICT_OVERCONFIDENT
    assert "BULLISH_HIGH_VOL" in candidate.regime_offsets
    assert candidate.regime_offsets["BULLISH_HIGH_VOL"] > 0
    assert candidate.version == REGIME_SCORE_ADJUSTMENT_VERSION


def test_well_calibrated_regime_gets_no_offset(session):
    # win rate matches the score's implied probability closely
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed_regime_population(
        session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T",
        win_count=int(Decimal(total) * candidate_score_normalized()),
    )

    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)

    assert candidate.performance[0].verdict == VERDICT_WELL_CALIBRATED
    assert candidate.regime_offsets == {}


def candidate_score_normalized():
    # matches the fixed opportunity_score produced by `_make_evaluated`'s
    # constant inputs -- computed once so the well-calibrated fixture's win
    # rate lines up with the actual score rather than a guess.
    from app.scoring import compute_positive_opportunity_score, ScoringInputs

    result = compute_positive_opportunity_score(ScoringInputs(
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.10"),
    ))
    return (result.total_score / Decimal("100")).quantize(Decimal("0.0001"))


def test_unadjusted_score_returned_for_a_regime_without_an_eligible_offset(session):
    scan = _make_scan(session, TRAIN_DATE, eligible_count=1)
    prediction = _make_evaluated(session, scan, "ONLY1", as_of=TRAIN_AS_OF, win=True)
    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)

    adjusted = apply_regime_score_adjustment(candidate, prediction, "BULLISH_HIGH_VOL")

    assert adjusted == prediction.opportunity_score


def test_out_of_sample_evaluation_with_no_eligible_regimes_is_explicit(session):
    scan = _make_scan(session, TRAIN_DATE, eligible_count=1)
    _make_evaluated(session, scan, "ONLY1", as_of=TRAIN_AS_OF, win=True)
    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)

    result = evaluate_regime_score_adjustment_out_of_sample(session, candidate, EVAL_WINDOW)

    assert result.verdict == VERDICT_NO_ADJUSTMENT_ELIGIBLE
    assert result.baseline_mean_absolute_error is None


def test_out_of_sample_evaluation_rejects_overlapping_windows(session):
    _seed_regime_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)
    overlapping = EvaluationWindow(
        label="eval", start=TRAIN_WINDOW.end - timedelta(days=1), end=TRAIN_WINDOW.end + timedelta(days=30)
    )

    with pytest.raises(OverlappingEvaluationWindowsError):
        evaluate_regime_score_adjustment_out_of_sample(session, candidate, overlapping)


def test_out_of_sample_evaluation_with_insufficient_eval_sample(session):
    _seed_regime_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)

    result = evaluate_regime_score_adjustment_out_of_sample(session, candidate, EVAL_WINDOW)

    assert result.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_candidate_that_generalizes_out_of_sample_beats_the_baseline(session):
    _seed_regime_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)

    # the identical regime/win-rate pattern persists out-of-sample
    _seed_regime_population(session, scan_date=EVAL_DATE, as_of=EVAL_AS_OF, prefix="E")

    result = evaluate_regime_score_adjustment_out_of_sample(session, candidate, EVAL_WINDOW)

    assert result.evaluated_count == 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert result.baseline_mean_absolute_error is not None
    assert result.candidate_mean_absolute_error is not None
    assert result.verdict == VERDICT_IMPROVED


def test_original_score_and_regime_are_never_mutated(session):
    scan = _seed_regime_population(session, scan_date=TRAIN_DATE, as_of=TRAIN_AS_OF, prefix="T")
    before_scores = {p.id: p.opportunity_score for p in session.query(Prediction).all()}

    candidate = build_regime_score_adjustment_candidate(session, TRAIN_WINDOW)
    prediction = session.query(Prediction).first()
    apply_regime_score_adjustment(candidate, prediction, "BULLISH_HIGH_VOL")

    after_scores = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    assert before_scores == after_scores
