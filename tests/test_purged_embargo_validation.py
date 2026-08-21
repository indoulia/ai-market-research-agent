from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.experiment_integrity_guard import register_holdout_window
from app.leakage_survivorship_guard import WORKFLOW_TRAINING, run_bias_guard_check
from app.models import HoldoutWindowRegistry, Prediction, PredictionOutcome, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.purged_embargo_validation import (
    AmbiguousValidationWindowError,
    DEFAULT_EMBARGO_DAYS,
    HoldoutContaminationError,
    POLICY_FAIL_EMPTY_TRAINING_SET,
    POLICY_FAIL_NO_FOLDS,
    POLICY_VERDICT_FAIL,
    POLICY_VERDICT_PASS,
    PURGED_EMBARGO_VERSION,
    REASON_BIAS_GUARD_BLOCKED,
    REASON_HOLDOUT_WINDOW_PROTECTED,
    REASON_LABEL_WINDOW_OVERLAPS_VALIDATION,
    REASON_MISSING_OUTCOME,
    REASON_WITHIN_EMBARGO_PERIOD,
    compute_purged_training_set,
    evaluate_temporal_validation_policy,
    generate_walk_forward_folds,
    get_label_windows,
    get_policy_decision_history,
    get_validation_folds,
    record_validation_fold,
)

MODEL_VERSION = "test-model-1"
BASE_TIME = datetime(2027, 1, 1, tzinfo=timezone.utc)
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


def _make_prediction(session, *, as_of, outcome_at=None, model_version=MODEL_VERSION):
    n = next(_counter)
    stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=as_of, entry_price=Decimal("100"), horizon_days=5,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=model_version, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.flush()
    if outcome_at is not None:
        session.add(PredictionOutcome(
            prediction_id=prediction.id, evaluation_date=outcome_at, highest_price=Decimal("110"),
            lowest_price=Decimal("99"), closing_price=Decimal("108"), maximum_return=Decimal("0.10"),
            maximum_drawdown=Decimal("-0.01"), actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"),
            target_hit=True, stop_hit=False, outcome="SUCCESS",
        ))
    session.commit()
    return prediction.id


def _window(label, start, end):
    return EvaluationWindow(label=label, start=start, end=end)


def test_get_label_windows_none_outcome_when_unresolved(session):
    resolved_id = _make_prediction(session, as_of=BASE_TIME, outcome_at=BASE_TIME + timedelta(days=5))
    unresolved_id = _make_prediction(session, as_of=BASE_TIME, outcome_at=None)

    windows = {w.prediction_id: w for w in get_label_windows(session, [resolved_id, unresolved_id])}

    assert windows[resolved_id].outcome_timestamp == (BASE_TIME + timedelta(days=5)).replace(tzinfo=None)
    assert windows[unresolved_id].outcome_timestamp is None


def test_generate_walk_forward_folds_rolling_window():
    folds = generate_walk_forward_folds(
        universe_start=BASE_TIME, universe_end=BASE_TIME + timedelta(days=100),
        train_span_days=30, validation_span_days=10, step_days=10, expanding=False,
    )

    assert len(folds) >= 2
    assert folds[0].train_window.start == BASE_TIME
    assert folds[0].train_window.end == BASE_TIME + timedelta(days=30)
    assert folds[1].train_window.start == BASE_TIME + timedelta(days=10)
    train_span_0 = folds[0].train_window.end - folds[0].train_window.start
    train_span_1 = folds[1].train_window.end - folds[1].train_window.start
    assert train_span_0 == train_span_1 == timedelta(days=30)
    for fold in folds:
        assert fold.validation_window.start == fold.train_window.end


def test_generate_walk_forward_folds_expanding_window():
    folds = generate_walk_forward_folds(
        universe_start=BASE_TIME, universe_end=BASE_TIME + timedelta(days=100),
        train_span_days=30, validation_span_days=10, step_days=10, expanding=True,
    )

    assert len(folds) >= 2
    assert folds[0].train_window.start == folds[1].train_window.start == BASE_TIME
    assert folds[1].train_window.end > folds[0].train_window.end


@pytest.mark.parametrize("kwargs", [
    dict(train_span_days=0, validation_span_days=10, step_days=10),
    dict(train_span_days=30, validation_span_days=0, step_days=10),
    dict(train_span_days=30, validation_span_days=10, step_days=0),
])
def test_generate_walk_forward_folds_rejects_non_positive_spans(kwargs):
    with pytest.raises(AmbiguousValidationWindowError):
        generate_walk_forward_folds(universe_start=BASE_TIME, universe_end=BASE_TIME + timedelta(days=100), **kwargs)


def test_generate_walk_forward_folds_rejects_end_before_start():
    with pytest.raises(AmbiguousValidationWindowError):
        generate_walk_forward_folds(
            universe_start=BASE_TIME, universe_end=BASE_TIME - timedelta(days=1),
            train_span_days=30, validation_span_days=10, step_days=10,
        )


def test_compute_purged_training_set_rejects_unbounded_windows(session):
    bounded = _window("v", BASE_TIME, BASE_TIME + timedelta(days=10))
    unbounded = _window("t", None, None)
    with pytest.raises(AmbiguousValidationWindowError):
        compute_purged_training_set(session, train_window=unbounded, validation_window=bounded)
    with pytest.raises(AmbiguousValidationWindowError):
        compute_purged_training_set(session, train_window=bounded, validation_window=unbounded)


def test_compute_purged_training_set_excludes_missing_outcome(session):
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    unresolved_id = _make_prediction(session, as_of=BASE_TIME + timedelta(days=5), outcome_at=None)

    result = compute_purged_training_set(session, train_window=train, validation_window=validation)

    assert result.eligible_training_prediction_ids == ()
    assert result.excluded[0].prediction_id == unresolved_id
    assert result.excluded[0].reason == REASON_MISSING_OUTCOME


def test_compute_purged_training_set_excludes_overlapping_label_window(session):
    # adversarial: information timestamp is safely inside the training
    # window, but the label's outcome (horizon resolution) leaks into the
    # validation window -- this is exactly the overlapping-horizon leakage
    # purged/embargoed CV exists to catch.
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    leaking_id = _make_prediction(
        session, as_of=BASE_TIME + timedelta(days=28), outcome_at=BASE_TIME + timedelta(days=33),
    )

    result = compute_purged_training_set(session, train_window=train, validation_window=validation, embargo_days=0)

    assert result.eligible_training_prediction_ids == ()
    assert result.excluded[0].prediction_id == leaking_id
    assert result.excluded[0].reason == REASON_LABEL_WINDOW_OVERLAPS_VALIDATION


def test_compute_purged_training_set_excludes_within_embargo_period(session):
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    # fully resolved before validation starts, but inside the embargo buffer
    embargoed_id = _make_prediction(
        session, as_of=BASE_TIME + timedelta(days=27), outcome_at=BASE_TIME + timedelta(days=29),
    )

    result = compute_purged_training_set(session, train_window=train, validation_window=validation, embargo_days=DEFAULT_EMBARGO_DAYS)

    assert result.eligible_training_prediction_ids == ()
    assert result.excluded[0].prediction_id == embargoed_id
    assert result.excluded[0].reason == REASON_WITHIN_EMBARGO_PERIOD


def test_compute_purged_training_set_keeps_safely_disjoint_predictions(session):
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    safe_id = _make_prediction(
        session, as_of=BASE_TIME + timedelta(days=1), outcome_at=BASE_TIME + timedelta(days=3),
    )

    result = compute_purged_training_set(session, train_window=train, validation_window=validation, embargo_days=DEFAULT_EMBARGO_DAYS)

    assert result.eligible_training_prediction_ids == (safe_id,)
    assert result.excluded == ()


def test_compute_purged_training_set_excludes_bias_guard_blocked_predictions(session):
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    blocked_id = _make_prediction(
        session, as_of=BASE_TIME + timedelta(days=1), outcome_at=BASE_TIME + timedelta(days=3),
    )
    prediction = session.get(Prediction, blocked_id)
    run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=BASE_TIME)

    result = compute_purged_training_set(session, train_window=train, validation_window=validation)

    assert result.eligible_training_prediction_ids == ()
    assert result.excluded[0].prediction_id == blocked_id
    assert result.excluded[0].reason == REASON_BIAS_GUARD_BLOCKED


def test_compute_purged_training_set_excludes_holdout_protected_training_rows(session):
    holdout_window = _window("final-holdout", BASE_TIME + timedelta(days=5), BASE_TIME + timedelta(days=10))
    register_holdout_window(session, label="final-holdout", window=holdout_window, registered_at=BASE_TIME)

    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    protected_id = _make_prediction(
        session, as_of=BASE_TIME + timedelta(days=6), outcome_at=BASE_TIME + timedelta(days=8),
    )

    result = compute_purged_training_set(session, train_window=train, validation_window=validation, embargo_days=0)

    assert result.eligible_training_prediction_ids == ()
    assert result.excluded[0].prediction_id == protected_id
    assert result.excluded[0].reason == REASON_HOLDOUT_WINDOW_PROTECTED


def test_compute_purged_training_set_raises_on_unsanctioned_holdout_validation_overlap(session):
    holdout_window = _window("final-holdout", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    register_holdout_window(session, label="final-holdout", window=holdout_window, registered_at=BASE_TIME)

    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))

    with pytest.raises(HoldoutContaminationError):
        compute_purged_training_set(session, train_window=train, validation_window=validation)


def test_compute_purged_training_set_allows_explicitly_sanctioned_holdout_validation(session):
    holdout_window = _window("final-holdout", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    register_holdout_window(session, label="final-holdout", window=holdout_window, registered_at=BASE_TIME)

    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    safe_id = _make_prediction(
        session, as_of=BASE_TIME + timedelta(days=1), outcome_at=BASE_TIME + timedelta(days=3),
    )

    result = compute_purged_training_set(
        session, train_window=train, validation_window=validation, embargo_days=0,
        holdout_sanctioned_label="final-holdout",
    )

    assert result.eligible_training_prediction_ids == (safe_id,)


def test_compute_purged_training_set_still_purges_training_rows_inside_sanctioned_holdout(session):
    # the sanction only permits USING the holdout window as this fold's
    # validation window -- it must never make holdout-period rows usable as
    # training data, sanctioned or not.
    holdout_window = _window("final-holdout", BASE_TIME + timedelta(days=5), BASE_TIME + timedelta(days=40))
    register_holdout_window(session, label="final-holdout", window=holdout_window, registered_at=BASE_TIME)

    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    inside_holdout_id = _make_prediction(
        session, as_of=BASE_TIME + timedelta(days=6), outcome_at=BASE_TIME + timedelta(days=8),
    )

    result = compute_purged_training_set(
        session, train_window=train, validation_window=validation, embargo_days=0,
        holdout_sanctioned_label="final-holdout",
    )

    assert result.eligible_training_prediction_ids == ()
    assert result.excluded[0].prediction_id == inside_holdout_id
    assert result.excluded[0].reason == REASON_HOLDOUT_WINDOW_PROTECTED


def test_record_validation_fold_idempotent_and_reconstructable(session):
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    safe_id = _make_prediction(session, as_of=BASE_TIME + timedelta(days=1), outcome_at=BASE_TIME + timedelta(days=3))
    result = compute_purged_training_set(session, train_window=train, validation_window=validation)

    first = record_validation_fold(session, model_version=MODEL_VERSION, fold_index=0, purge_result=result, computed_at=BASE_TIME)
    second = record_validation_fold(session, model_version=MODEL_VERSION, fold_index=0, purge_result=result, computed_at=BASE_TIME)

    assert first.id == second.id
    assert first.eligible_training_prediction_ids == [safe_id]
    assert first.framework_version == PURGED_EMBARGO_VERSION
    assert len(get_validation_folds(session, MODEL_VERSION)) == 1


def test_evaluate_temporal_validation_policy_fails_when_no_folds(session):
    decision = evaluate_temporal_validation_policy(session, model_version=MODEL_VERSION, folds=(), evaluated_at=BASE_TIME)

    assert decision.verdict == POLICY_VERDICT_FAIL
    assert POLICY_FAIL_NO_FOLDS in decision.fail_reasons


def test_evaluate_temporal_validation_policy_fails_when_a_fold_has_empty_training_set(session):
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    empty_result = compute_purged_training_set(session, train_window=train, validation_window=validation)
    fold = record_validation_fold(session, model_version=MODEL_VERSION, fold_index=0, purge_result=empty_result, computed_at=BASE_TIME)

    decision = evaluate_temporal_validation_policy(session, model_version=MODEL_VERSION, folds=(fold,), evaluated_at=BASE_TIME)

    assert decision.verdict == POLICY_VERDICT_FAIL
    assert any(reason.startswith(POLICY_FAIL_EMPTY_TRAINING_SET) for reason in decision.fail_reasons)


def test_evaluate_temporal_validation_policy_passes_when_folds_have_eligible_rows(session):
    train = _window("train", BASE_TIME, BASE_TIME + timedelta(days=30))
    validation = _window("validation", BASE_TIME + timedelta(days=30), BASE_TIME + timedelta(days=40))
    _make_prediction(session, as_of=BASE_TIME + timedelta(days=1), outcome_at=BASE_TIME + timedelta(days=3))
    result = compute_purged_training_set(session, train_window=train, validation_window=validation)
    fold = record_validation_fold(session, model_version=MODEL_VERSION, fold_index=0, purge_result=result, computed_at=BASE_TIME)

    decision = evaluate_temporal_validation_policy(session, model_version=MODEL_VERSION, folds=(fold,), evaluated_at=BASE_TIME)

    assert decision.verdict == POLICY_VERDICT_PASS
    assert decision.fail_reasons == []


def test_evaluate_temporal_validation_policy_idempotent(session):
    first = evaluate_temporal_validation_policy(session, model_version=MODEL_VERSION, folds=(), evaluated_at=BASE_TIME)
    second = evaluate_temporal_validation_policy(session, model_version=MODEL_VERSION, folds=(), evaluated_at=BASE_TIME)

    assert first.id == second.id
    assert len(get_policy_decision_history(session, MODEL_VERSION)) == 1
