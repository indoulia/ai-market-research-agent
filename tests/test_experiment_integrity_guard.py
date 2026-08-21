from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.experiment_integrity_guard import (
    EXPERIMENT_INTEGRITY_VERSION,
    HoldoutAlreadyConsumedError,
    HoldoutRedefinitionError,
    UnknownHoldoutWindowError,
    VERDICT_NOT_SIGNIFICANT_AFTER_CORRECTION,
    VERDICT_SIGNIFICANT_AFTER_CORRECTION,
    count_trials_for_model_version,
    evaluate_multiplicity_adjusted_significance,
    get_confirmation_history,
    get_multiplicity_guard_history,
    record_holdout_usage,
    register_holdout_window,
    require_independent_confirmation,
)
from app.models import Experiment, ExperimentArm, Prediction, PredictionOutcome, Stock
from app.out_of_sample_validation import (
    EvaluationWindow,
    OverlappingEvaluationWindowsError,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_VALIDATED,
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


def _make_experiment_arm(session, *, model_version=MODEL_VERSION, arm_name=None):
    n = next(_counter)
    experiment = Experiment(name=f"exp-{n}", hypothesis="h", experiment_version="EXP-001")
    session.add(experiment)
    session.flush()
    arm = ExperimentArm(
        experiment_id=experiment.id, arm_name=arm_name or f"arm-{n}", model_version=model_version,
        window_label=f"window-{n}", window_start=None, window_end=None, horizon_days_filter=None,
    )
    session.add(arm)
    session.commit()
    return arm


def _add_outcomes(session, *, model_version, window: EvaluationWindow, count, outcome):
    mid = window.start + (window.end - window.start) / 2
    for _ in range(count):
        n = next(_counter)
        stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
        session.add(stock)
        session.flush()
        prediction = Prediction(
            stock_id=stock.id, as_of_timestamp=mid, entry_price=Decimal("100"), horizon_days=1,
            target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
            confidence=Decimal("0.8"), model_version=model_version, feature_version="FV-001",
            consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
            opportunity_score=Decimal("60.00"),
        )
        session.add(prediction)
        session.flush()
        session.add(PredictionOutcome(
            prediction_id=prediction.id, evaluation_date=mid, highest_price=Decimal("110"), lowest_price=Decimal("99"),
            closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
            actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
            stop_hit=(outcome == "FAILURE"), outcome=outcome,
        ))
    session.commit()


def test_register_holdout_window_idempotent_and_rejects_redefinition(session):
    window = EvaluationWindow(label="final-holdout", start=BASE_TIME, end=BASE_TIME + timedelta(days=90))

    first = register_holdout_window(session, label="final-holdout", window=window, registered_at=BASE_TIME)
    second = register_holdout_window(session, label="final-holdout", window=window, registered_at=BASE_TIME)
    assert first.id == second.id
    assert first.registry_version == EXPERIMENT_INTEGRITY_VERSION

    different = EvaluationWindow(label="final-holdout", start=BASE_TIME, end=BASE_TIME + timedelta(days=91))
    with pytest.raises(HoldoutRedefinitionError):
        register_holdout_window(session, label="final-holdout", window=different, registered_at=BASE_TIME)


def test_record_holdout_usage_raises_for_unknown_holdout(session):
    arm = _make_experiment_arm(session)

    with pytest.raises(UnknownHoldoutWindowError):
        record_holdout_usage(session, holdout_label="no-such-holdout", experiment_arm_id=arm.id, used_at=BASE_TIME)


def test_record_holdout_usage_raises_on_second_use(session):
    window = EvaluationWindow(label="final-holdout", start=BASE_TIME, end=BASE_TIME + timedelta(days=90))
    register_holdout_window(session, label="final-holdout", window=window, registered_at=BASE_TIME)
    arm_1 = _make_experiment_arm(session)
    arm_2 = _make_experiment_arm(session)

    record_holdout_usage(session, holdout_label="final-holdout", experiment_arm_id=arm_1.id, used_at=BASE_TIME)

    with pytest.raises(HoldoutAlreadyConsumedError):
        record_holdout_usage(session, holdout_label="final-holdout", experiment_arm_id=arm_2.id, used_at=BASE_TIME)


def test_count_trials_for_model_version(session):
    _make_experiment_arm(session, model_version=MODEL_VERSION)
    _make_experiment_arm(session, model_version=MODEL_VERSION)
    _make_experiment_arm(session, model_version="other-model")

    assert count_trials_for_model_version(session, MODEL_VERSION) == 2
    assert count_trials_for_model_version(session, "other-model") == 1
    assert count_trials_for_model_version(session, "never-tried") == 0


def test_small_delta_significant_with_few_trials(session):
    _make_experiment_arm(session, model_version=MODEL_VERSION)

    decision = evaluate_multiplicity_adjusted_significance(
        session, model_version=MODEL_VERSION, observed_success_rate_delta=Decimal("0.12"), evaluated_at=BASE_TIME,
    )

    assert decision.trial_count == 1
    assert decision.verdict == VERDICT_SIGNIFICANT_AFTER_CORRECTION
    assert decision.adjusted_margin == decision.weakness_margin


def test_same_delta_not_significant_with_many_trials(session):
    for _ in range(5):
        _make_experiment_arm(session, model_version=MODEL_VERSION)

    decision = evaluate_multiplicity_adjusted_significance(
        session, model_version=MODEL_VERSION, observed_success_rate_delta=Decimal("0.12"), evaluated_at=BASE_TIME,
    )

    assert decision.trial_count == 5
    assert decision.verdict == VERDICT_NOT_SIGNIFICANT_AFTER_CORRECTION
    assert decision.adjusted_margin == decision.weakness_margin * 5


def test_multiplicity_guard_idempotent(session):
    _make_experiment_arm(session, model_version=MODEL_VERSION)

    first = evaluate_multiplicity_adjusted_significance(
        session, model_version=MODEL_VERSION, observed_success_rate_delta=Decimal("0.12"), evaluated_at=BASE_TIME,
    )
    _make_experiment_arm(session, model_version=MODEL_VERSION)  # more trials registered afterwards
    second = evaluate_multiplicity_adjusted_significance(
        session, model_version=MODEL_VERSION, observed_success_rate_delta=Decimal("0.99"), evaluated_at=BASE_TIME,
    )

    assert first.id == second.id
    assert len(get_multiplicity_guard_history(session, MODEL_VERSION)) == 1


def test_independent_confirmation_both_validated(session):
    baseline = EvaluationWindow(label="baseline", start=BASE_TIME, end=BASE_TIME + timedelta(days=30))
    first = EvaluationWindow(label="first", start=BASE_TIME + timedelta(days=31), end=BASE_TIME + timedelta(days=60))
    confirmation = EvaluationWindow(label="confirmation", start=BASE_TIME + timedelta(days=61), end=BASE_TIME + timedelta(days=90))

    _add_outcomes(session, model_version=MODEL_VERSION, window=baseline, count=10, outcome="FAILURE")
    _add_outcomes(session, model_version=MODEL_VERSION, window=baseline, count=10, outcome="SUCCESS")
    _add_outcomes(session, model_version=MODEL_VERSION, window=first, count=20, outcome="SUCCESS")
    _add_outcomes(session, model_version=MODEL_VERSION, window=confirmation, count=20, outcome="SUCCESS")

    decision = require_independent_confirmation(
        session, model_version=MODEL_VERSION, baseline_window=baseline, first_window=first,
        confirmation_window=confirmation, confirmed_at=BASE_TIME,
    )

    assert decision.first_window_verdict == VERDICT_VALIDATED
    assert decision.confirmation_window_verdict == VERDICT_VALIDATED
    assert decision.both_validated is True
    assert decision.confirmation_rule_version == EXPERIMENT_INTEGRITY_VERSION


def test_independent_confirmation_fails_when_confirmation_window_insufficient(session):
    baseline = EvaluationWindow(label="baseline", start=BASE_TIME, end=BASE_TIME + timedelta(days=30))
    first = EvaluationWindow(label="first", start=BASE_TIME + timedelta(days=31), end=BASE_TIME + timedelta(days=60))
    confirmation = EvaluationWindow(label="confirmation", start=BASE_TIME + timedelta(days=61), end=BASE_TIME + timedelta(days=90))

    _add_outcomes(session, model_version=MODEL_VERSION, window=baseline, count=10, outcome="FAILURE")
    _add_outcomes(session, model_version=MODEL_VERSION, window=baseline, count=10, outcome="SUCCESS")
    _add_outcomes(session, model_version=MODEL_VERSION, window=first, count=20, outcome="SUCCESS")
    _add_outcomes(session, model_version=MODEL_VERSION, window=confirmation, count=5, outcome="SUCCESS")

    decision = require_independent_confirmation(
        session, model_version=MODEL_VERSION, baseline_window=baseline, first_window=first,
        confirmation_window=confirmation, confirmed_at=BASE_TIME,
    )

    assert decision.first_window_verdict == VERDICT_VALIDATED
    assert decision.confirmation_window_verdict == VERDICT_INSUFFICIENT_EVIDENCE
    assert decision.both_validated is False


def test_independent_confirmation_overlapping_windows_raise(session):
    baseline = EvaluationWindow(label="baseline", start=BASE_TIME, end=BASE_TIME + timedelta(days=30))
    first = EvaluationWindow(label="first", start=BASE_TIME + timedelta(days=10), end=BASE_TIME + timedelta(days=60))
    confirmation = EvaluationWindow(label="confirmation", start=BASE_TIME + timedelta(days=61), end=BASE_TIME + timedelta(days=90))

    with pytest.raises(OverlappingEvaluationWindowsError):
        require_independent_confirmation(
            session, model_version=MODEL_VERSION, baseline_window=baseline, first_window=first,
            confirmation_window=confirmation, confirmed_at=BASE_TIME,
        )


def test_independent_confirmation_idempotent(session):
    baseline = EvaluationWindow(label="baseline", start=BASE_TIME, end=BASE_TIME + timedelta(days=30))
    first = EvaluationWindow(label="first", start=BASE_TIME + timedelta(days=31), end=BASE_TIME + timedelta(days=60))
    confirmation = EvaluationWindow(label="confirmation", start=BASE_TIME + timedelta(days=61), end=BASE_TIME + timedelta(days=90))

    _add_outcomes(session, model_version=MODEL_VERSION, window=baseline, count=20, outcome="SUCCESS")
    _add_outcomes(session, model_version=MODEL_VERSION, window=first, count=20, outcome="SUCCESS")
    _add_outcomes(session, model_version=MODEL_VERSION, window=confirmation, count=20, outcome="SUCCESS")

    first_call = require_independent_confirmation(
        session, model_version=MODEL_VERSION, baseline_window=baseline, first_window=first,
        confirmation_window=confirmation, confirmed_at=BASE_TIME,
    )
    second_call = require_independent_confirmation(
        session, model_version=MODEL_VERSION, baseline_window=baseline, first_window=first,
        confirmation_window=confirmation, confirmed_at=BASE_TIME,
    )

    assert first_call.id == second_call.id
    assert len(get_confirmation_history(session, MODEL_VERSION)) == 1
