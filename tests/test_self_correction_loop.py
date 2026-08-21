from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Prediction, PredictionAttributionSnapshot, PredictionUsefulnessAssessment, Stock
from app.out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from app.prediction_attribution import DIMENSION_HORIZON, DIMENSION_REGIME
from app.prediction_usefulness import NOT_USEFUL, USEFUL
from app.self_correction_loop import (
    CATEGORY_FACTOR_FAILURE_PATTERN,
    CATEGORY_LOW_HORIZON_USEFULNESS,
    EFFECT_RESTORE,
    EFFECT_RESTRICT,
    HYPOTHESIS_RULE_VERSION,
    VALIDATION_PENDING,
    VALIDATION_REJECTED,
    VALIDATION_VALIDATED,
    LearningHypothesisImmutableError,
    generate_learning_hypotheses,
    get_hypothesis_history,
    get_latest_eligibility_effect,
)

MODEL_VERSION = "test-model-1"
BASE_TIME = datetime(2027, 1, 1, tzinfo=timezone.utc)
BASELINE_WINDOW = EvaluationWindow(label="baseline", start=BASE_TIME, end=BASE_TIME + timedelta(days=30))
MONITORING_WINDOW = EvaluationWindow(
    label="monitoring", start=BASE_TIME + timedelta(days=31), end=BASE_TIME + timedelta(days=60)
)
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


@pytest.fixture
def stock(session):
    s = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(s)
    session.flush()
    return s


def _make_prediction(session, stock, *, horizon_days=1):
    n = next(_counter)
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=BASE_TIME, entry_price=Decimal("100"), horizon_days=horizon_days,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00") + Decimal(n % 10),
    )
    session.add(prediction)
    session.flush()
    return prediction


def _add_attribution_snapshots(session, stock, *, count, window, horizon_days=1, regime="BEARISH_LOW_VOL", outcome="FAILURE"):
    mid = window.start + (window.end - window.start) / 2
    for _ in range(count):
        prediction = _make_prediction(session, stock, horizon_days=horizon_days)
        session.add(PredictionAttributionSnapshot(
            prediction_id=prediction.id, model_version=MODEL_VERSION, horizon_days=horizon_days, regime=regime,
            sma20_distance_bucket="MODERATE", volume_ratio_bucket="NORMAL", evidence_categories_available=[],
            outcome=outcome, snapshotted_at=mid, attribution_rule_version="ATB-001",
        ))
    session.commit()


def _add_usefulness_assessments(session, stock, *, count, window, horizon_days=5, verdict=NOT_USEFUL):
    mid = window.start + (window.end - window.start) / 2
    for _ in range(count):
        prediction = _make_prediction(session, stock, horizon_days=horizon_days)
        session.add(PredictionUsefulnessAssessment(
            prediction_id=prediction.id, directional_outcome="SUCCESS", risk_adjusted_ratio=Decimal("0.5"),
            usefulness_verdict=verdict, assessed_at=mid, usefulness_rule_version="PUM-001",
        ))
    session.commit()


def test_no_hypothesis_when_baseline_segment_is_not_weak(session, stock):
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="NEUTRAL", outcome="SUCCESS")

    rows = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    assert rows == ()


def test_factor_failure_pattern_validated_when_it_replicates(session, stock):
    # Baseline: BEARISH segment all-FAILURE, BULLISH segment all-SUCCESS -> BEARISH is weak vs overall.
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")
    # Monitoring: BEARISH segment still all-FAILURE -> pattern replicates.
    _add_attribution_snapshots(session, stock, count=20, window=MONITORING_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=MONITORING_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")

    rows = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    bearish = next(r for r in rows if r.hypothesis_category == CATEGORY_FACTOR_FAILURE_PATTERN and r.dimension == DIMENSION_REGIME and r.factor_value == "BEARISH_LOW_VOL")
    assert bearish.validation_status == VALIDATION_VALIDATED
    assert bearish.eligibility_effect == EFFECT_RESTRICT
    assert bearish.baseline_rate == Decimal("0")
    assert bearish.monitoring_rate == Decimal("0")
    assert bearish.hypothesis_rule_version == HYPOTHESIS_RULE_VERSION
    bullish_rows = [r for r in rows if r.factor_value == "BULLISH_HIGH_VOL" and r.dimension == DIMENSION_REGIME]
    assert bullish_rows == []  # never weak in baseline -> no hypothesis generated at all


def test_factor_failure_pattern_rejected_when_it_recovers(session, stock):
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")
    # Monitoring: BEARISH segment has recovered to all-SUCCESS, same as the rest -> no longer weak.
    _add_attribution_snapshots(session, stock, count=20, window=MONITORING_WINDOW, regime="BEARISH_LOW_VOL", outcome="SUCCESS")
    _add_attribution_snapshots(session, stock, count=20, window=MONITORING_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")

    rows = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    bearish = next(r for r in rows if r.factor_value == "BEARISH_LOW_VOL" and r.dimension == DIMENSION_REGIME)
    assert bearish.validation_status == VALIDATION_REJECTED
    assert bearish.eligibility_effect == EFFECT_RESTORE


def test_factor_failure_pattern_pending_when_monitoring_evidence_insufficient(session, stock):
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")
    # Monitoring: too few BEARISH samples to judge (below MIN_SAMPLE_SIZE_FOR_COMPARISON=20).
    _add_attribution_snapshots(session, stock, count=5, window=MONITORING_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")

    rows = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    bearish = next(r for r in rows if r.factor_value == "BEARISH_LOW_VOL" and r.dimension == DIMENSION_REGIME)
    assert bearish.validation_status == VALIDATION_PENDING
    assert bearish.eligibility_effect == EFFECT_RESTORE
    assert bearish.monitoring_rate is None


def test_low_horizon_usefulness_validated_when_it_replicates(session, stock):
    _add_usefulness_assessments(session, stock, count=20, window=BASELINE_WINDOW, horizon_days=5, verdict=NOT_USEFUL)
    _add_usefulness_assessments(session, stock, count=20, window=BASELINE_WINDOW, horizon_days=1, verdict=USEFUL)
    _add_usefulness_assessments(session, stock, count=20, window=MONITORING_WINDOW, horizon_days=5, verdict=NOT_USEFUL)
    _add_usefulness_assessments(session, stock, count=20, window=MONITORING_WINDOW, horizon_days=1, verdict=USEFUL)

    rows = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    horizon5 = next(r for r in rows if r.hypothesis_category == CATEGORY_LOW_HORIZON_USEFULNESS and r.factor_value == "5")
    assert horizon5.dimension == DIMENSION_HORIZON
    assert horizon5.validation_status == VALIDATION_VALIDATED
    assert horizon5.eligibility_effect == EFFECT_RESTRICT
    assert not any(r.factor_value == "1" and r.hypothesis_category == CATEGORY_LOW_HORIZON_USEFULNESS for r in rows)


def test_overlapping_windows_raise(session, stock):
    overlapping = EvaluationWindow(label="overlap", start=BASE_TIME + timedelta(days=10), end=BASE_TIME + timedelta(days=40))

    with pytest.raises(OverlappingEvaluationWindowsError):
        generate_learning_hypotheses(
            session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
            monitoring_window=overlapping, generated_at=BASE_TIME,
        )


def test_idempotent_by_model_version_and_generated_at(session, stock):
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")

    first = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )
    second = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    assert [r.id for r in first] == [r.id for r in second]


def test_hypothesis_row_is_immutable(session, stock):
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")
    rows = generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    rows[0].validation_status = VALIDATION_REJECTED
    with pytest.raises(LearningHypothesisImmutableError):
        session.commit()
    session.rollback()


def test_get_latest_eligibility_effect_reflects_most_recent_run(session, stock):
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")
    _add_attribution_snapshots(session, stock, count=20, window=MONITORING_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=MONITORING_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")

    generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )
    assert get_latest_eligibility_effect(
        session, model_version=MODEL_VERSION, dimension=DIMENSION_REGIME, factor_value="BEARISH_LOW_VOL",
    ) == EFFECT_RESTRICT

    later_window = EvaluationWindow(label="later", start=BASE_TIME + timedelta(days=61), end=BASE_TIME + timedelta(days=90))
    _add_attribution_snapshots(session, stock, count=20, window=later_window, regime="BEARISH_LOW_VOL", outcome="SUCCESS")
    _add_attribution_snapshots(session, stock, count=20, window=later_window, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")
    generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=MONITORING_WINDOW,
        monitoring_window=later_window, generated_at=BASE_TIME + timedelta(days=61),
    )

    assert get_latest_eligibility_effect(
        session, model_version=MODEL_VERSION, dimension=DIMENSION_REGIME, factor_value="BEARISH_LOW_VOL",
    ) == EFFECT_RESTORE


def test_get_hypothesis_history_returns_all_rows_for_model_version(session, stock):
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BEARISH_LOW_VOL", outcome="FAILURE")
    _add_attribution_snapshots(session, stock, count=20, window=BASELINE_WINDOW, regime="BULLISH_HIGH_VOL", outcome="SUCCESS")
    generate_learning_hypotheses(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, generated_at=BASE_TIME,
    )

    history = get_hypothesis_history(session, model_version=MODEL_VERSION)

    assert len(history) == 1
    assert history[0].model_version == MODEL_VERSION
