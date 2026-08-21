from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.champion_challenger_shadow import (
    COMPARISON_RULE_VERSION,
    NoKnownGoodChampionError,
    REASON_ROLLBACK,
    SHADOW_RULE_VERSION,
    compare_shadow_challenger_performance,
    evaluate_shadow_promotion,
    execute_rollback,
    get_comparison_report_history,
    get_rollback_history,
    get_shadow_assessment_history,
    record_shadow_challenger_run,
)
from app.db import Base
from app.model_promotion import DECISION_PROMOTED, DECISION_REJECTED, REASON_INSUFFICIENT_EVIDENCE, REASON_REGRESSED, REASON_VALIDATED
from app.models import ModelPromotion, ModelRegressionCheck, Prediction, PredictionOutcome, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.recommendations import record_recommendation

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
_stock_counter = iter(range(1000000))


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


def _make_champion_prediction(session, *, model_version, as_of=AS_OF):
    stock = Stock(symbol=f"S{next(_stock_counter)}", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=as_of,
        entry_price=Decimal("100"),
        horizon_days=5,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"),
        model_version=model_version,
        feature_version="FV-001",
        consensus_contract_version="CC-001",
        horizon_selection_version="HS-001",
        scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )


def _add_outcome(session, prediction, *, outcome):
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("106"), lowest_price=Decimal("99"),
        closing_price=Decimal("105") if outcome == "SUCCESS" else Decimal("97"),
        maximum_return=Decimal("0.06"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.05") if outcome == "SUCCESS" else Decimal("-0.03"),
        prediction_error=Decimal("0"), target_hit=(outcome == "SUCCESS"), stop_hit=(outcome == "FAILURE"),
        outcome=outcome, label_methodology_version=None,
    ))
    session.commit()


def test_shadow_run_is_idempotent_and_never_touches_prediction_table(session):
    champion = _make_champion_prediction(session, model_version="champ-v1")
    original_probability = champion.predicted_probability

    first = record_shadow_challenger_run(
        session, champion, challenger_model_version="chal-v1",
        challenger_predicted_probability=Decimal("0.9"), recorded_at=AS_OF,
    )
    second = record_shadow_challenger_run(
        session, champion, challenger_model_version="chal-v1",
        challenger_predicted_probability=Decimal("0.1"), recorded_at=AS_OF,
    )

    assert first.id == second.id
    assert second.challenger_predicted_probability == Decimal("0.9")  # unchanged by the second call
    assert first.shadow_rule_version == SHADOW_RULE_VERSION
    session.refresh(champion)
    assert champion.predicted_probability == original_probability
    assert len(get_shadow_assessment_history(session, champion.id)) == 1


def _build_shared_sample(session, *, count, champion_model_version, challenger_model_version, champion_matches, challenger_matches):
    for i in range(count):
        outcome_str = "SUCCESS" if i < champion_matches else "FAILURE"
        champion = _make_champion_prediction(session, model_version=champion_model_version, as_of=AS_OF + timedelta(hours=i))
        _add_outcome(session, champion, outcome=outcome_str)
        challenger_probability = Decimal("0.9") if i < challenger_matches else Decimal("0.1")
        record_shadow_challenger_run(
            session, champion, challenger_model_version=challenger_model_version,
            challenger_predicted_probability=challenger_probability, recorded_at=AS_OF + timedelta(hours=i),
        )


def test_comparison_insufficient_evidence_below_minimum_sample(session):
    _build_shared_sample(session, count=5, champion_model_version="champ-v1", challenger_model_version="chal-v1", champion_matches=5, challenger_matches=5)
    window = EvaluationWindow(label="w", start=None, end=None)

    report = compare_shadow_challenger_performance(
        session, challenger_model_version="chal-v1", champion_model_version="champ-v1", window=window, computed_at=AS_OF,
    )

    assert report.verdict == REASON_INSUFFICIENT_EVIDENCE
    assert report.sample_count == 5


def test_comparison_validated_when_challenger_matches_champion(session):
    _build_shared_sample(session, count=20, champion_model_version="champ-v1", challenger_model_version="chal-v1", champion_matches=15, challenger_matches=15)
    window = EvaluationWindow(label="w", start=None, end=None)

    report = compare_shadow_challenger_performance(
        session, challenger_model_version="chal-v1", champion_model_version="champ-v1", window=window, computed_at=AS_OF,
    )

    assert report.verdict == REASON_VALIDATED
    assert report.sample_count == 20
    assert report.champion_success_rate == Decimal("0.75")
    assert report.comparison_rule_version == COMPARISON_RULE_VERSION
    assert len(report.by_horizon) == 1
    assert report.by_horizon[0]["horizon_days"] == 5


def test_comparison_regressed_when_challenger_much_worse(session):
    # Champion succeeds on all 20 (probability 0.7 -> correct implied call
    # when actual is SUCCESS); challenger's implied call is wrong on all 20.
    _build_shared_sample(session, count=20, champion_model_version="champ-v2", challenger_model_version="chal-v2", champion_matches=20, challenger_matches=0)
    window = EvaluationWindow(label="w", start=None, end=None)

    report = compare_shadow_challenger_performance(
        session, challenger_model_version="chal-v2", champion_model_version="champ-v2", window=window, computed_at=AS_OF,
    )

    assert report.verdict == REASON_REGRESSED
    assert report.success_rate_delta < 0


def test_evaluate_shadow_promotion_rejects_on_regressed_verdict(session):
    _build_shared_sample(session, count=20, champion_model_version="champ-v3", challenger_model_version="chal-v3", champion_matches=20, challenger_matches=0)
    window = EvaluationWindow(label="w", start=None, end=None)
    report = compare_shadow_challenger_performance(
        session, challenger_model_version="chal-v3", champion_model_version="champ-v3", window=window, computed_at=AS_OF,
    )

    promotion = evaluate_shadow_promotion(session, report, approver="qa-bot", decided_at=AS_OF)

    assert promotion.decision == DECISION_REJECTED
    assert promotion.decision_reason == REASON_REGRESSED
    assert promotion.candidate_model_version == "chal-v3"
    assert promotion.baseline_model_version == "champ-v3"


def test_evaluate_shadow_promotion_promotes_on_validated_verdict(session):
    _build_shared_sample(session, count=20, champion_model_version="champ-v4", challenger_model_version="chal-v4", champion_matches=15, challenger_matches=16)
    window = EvaluationWindow(label="w", start=None, end=None)
    report = compare_shadow_challenger_performance(
        session, challenger_model_version="chal-v4", champion_model_version="champ-v4", window=window, computed_at=AS_OF,
    )

    promotion = evaluate_shadow_promotion(session, report, approver="qa-bot", decided_at=AS_OF)

    assert promotion.decision == DECISION_PROMOTED
    assert promotion.decision_reason == REASON_VALIDATED
    assert len(get_comparison_report_history(session, "chal-v4")) == 1


def test_execute_rollback_restores_last_known_good_champion(session):
    session.add(ModelPromotion(
        candidate_model_version="v1", baseline_model_version=None, evidence_report_version="EV-1", success_rate_delta=None,
        decision=DECISION_PROMOTED, decision_reason=REASON_VALIDATED, decided_at=AS_OF, approver="human", promotion_rule_version="PROM-001",
    ))
    session.add(ModelPromotion(
        candidate_model_version="v2", baseline_model_version="v1", evidence_report_version="EV-2", success_rate_delta=Decimal("0.05"),
        decision=DECISION_PROMOTED, decision_reason=REASON_VALIDATED, decided_at=AS_OF + timedelta(days=1), approver="human", promotion_rule_version="PROM-001",
    ))
    session.commit()

    check = ModelRegressionCheck(
        model_version="v2", baseline_window_label="baseline", baseline_success_rate=Decimal("0.7"), baseline_sample_count=30,
        monitoring_window_label="monitoring", monitoring_success_rate=Decimal("0.5"), monitoring_sample_count=30,
        verdict="REGRESSED", segment_regressions=[], rollback_triggered=True, checked_at=AS_OF + timedelta(days=2),
        detection_rule_version="MRD-001",
    )
    session.add(check)
    session.commit()

    rollback = execute_rollback(session, regressed_model_version="v2", decided_at=AS_OF + timedelta(days=2), approver="qa-bot", triggering_check=check)

    assert rollback.rolled_back_model_version == "v2"
    assert rollback.restored_model_version == "v1"
    assert rollback.triggering_model_regression_check_id == check.id

    resulting_promotion = session.get(ModelPromotion, rollback.resulting_model_promotion_id)
    assert resulting_promotion.candidate_model_version == "v1"
    assert resulting_promotion.decision == DECISION_PROMOTED
    assert resulting_promotion.decision_reason == REASON_ROLLBACK


def test_execute_rollback_is_idempotent(session):
    session.add(ModelPromotion(
        candidate_model_version="v1", baseline_model_version=None, evidence_report_version="EV-1", success_rate_delta=None,
        decision=DECISION_PROMOTED, decision_reason=REASON_VALIDATED, decided_at=AS_OF, approver="human", promotion_rule_version="PROM-001",
    ))
    session.add(ModelPromotion(
        candidate_model_version="v2", baseline_model_version="v1", evidence_report_version="EV-2", success_rate_delta=Decimal("0.05"),
        decision=DECISION_PROMOTED, decision_reason=REASON_VALIDATED, decided_at=AS_OF + timedelta(days=1), approver="human", promotion_rule_version="PROM-001",
    ))
    session.commit()

    first = execute_rollback(session, regressed_model_version="v2", decided_at=AS_OF + timedelta(days=2), approver="qa-bot")
    second = execute_rollback(session, regressed_model_version="v2", decided_at=AS_OF + timedelta(days=3), approver="qa-bot-2")

    assert first.id == second.id
    assert len(get_rollback_history(session)) == 1
    promotion_count = session.scalar(select(ModelPromotion.id).where(ModelPromotion.decision_reason == REASON_ROLLBACK))
    assert promotion_count is not None


def test_execute_rollback_raises_without_a_known_good_predecessor(session):
    session.add(ModelPromotion(
        candidate_model_version="v1", baseline_model_version=None, evidence_report_version="EV-1", success_rate_delta=None,
        decision=DECISION_PROMOTED, decision_reason=REASON_VALIDATED, decided_at=AS_OF, approver="human", promotion_rule_version="PROM-001",
    ))
    session.commit()

    with pytest.raises(NoKnownGoodChampionError):
        execute_rollback(session, regressed_model_version="v1", decided_at=AS_OF + timedelta(days=1), approver="qa-bot")
