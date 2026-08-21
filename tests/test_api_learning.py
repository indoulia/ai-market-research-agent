"""Contract tests for GET /api/v1/learning/{summary,history,experiments}
(EPIC-M3.9)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.discovery_effectiveness import VERDICT_OK, VERDICT_WEAK
from app.model_promotion import DECISION_PROMOTED, DECISION_REJECTED
from app.models import (
    ChampionRollback,
    DailyCandidateScan,
    Experiment,
    ExperimentArm,
    ExperimentResult,
    FeedbackDrivenExperiment,
    LearningCycle,
    MarketPrice,
    ModelPromotion,
    Prediction,
    ScanCandidate,
    ShadowChallengerComparisonReport,
    Stock,
)
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation
from app.recommendation_feedback import CATEGORY_TARGET, REASON_AGREE, REASON_TOO_HIGH, submit_feedback
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

from api.deps import get_db
from app.main import app

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_summary_with_no_data_returns_safe_defaults(client):
    resp = client.get("/api/v1/learning/summary")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["currentModelVersion"] is None
    assert data["lastCycle"] is None
    assert data["promotionCounts"] == {"promoted": 0, "rejected": 0}
    assert data["rollbackCount"] == 0
    assert data["latestRollback"] is None
    assert data["experimentCounts"] == {"total": 0, "ready": 0, "insufficientSample": 0, "pending": 0}
    assert data["failurePatternCount"] == 0
    assert data["recentSignals"] == []
    assert data["championChallenger"] is None
    assert data["methodologyVersion"]


def test_history_with_no_data_returns_empty_list(client):
    resp = client.get("/api/v1/learning/history")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_experiments_with_no_data_returns_empty_list(client):
    resp = client.get("/api/v1/learning/experiments")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def _make_promotion(session, *, candidate, baseline, decision, reason, decided_at):
    promotion = ModelPromotion(
        candidate_model_version=candidate,
        baseline_model_version=baseline,
        evidence_report_version="TEST-001",
        success_rate_delta=Decimal("0.05"),
        decision=decision,
        decision_reason=reason,
        decided_at=decided_at,
        approver="test-approver",
        promotion_rule_version="PROM-001",
    )
    session.add(promotion)
    session.flush()
    return promotion


def test_summary_reflects_promotions_rollback_cycle_and_champion_challenger(session, client):
    promo1 = _make_promotion(
        session, candidate="model-v1", baseline=None, decision=DECISION_PROMOTED, reason="VALIDATED", decided_at=AS_OF
    )
    _make_promotion(
        session, candidate="model-v2", baseline="model-v1", decision=DECISION_REJECTED, reason="REGRESSED",
        decided_at=AS_OF + timedelta(days=1),
    )
    promo3 = _make_promotion(
        session, candidate="model-v1", baseline="model-v2", decision=DECISION_PROMOTED, reason="ROLLBACK",
        decided_at=AS_OF + timedelta(days=2),
    )
    session.add(
        ChampionRollback(
            rolled_back_model_version="model-v2",
            restored_model_version="model-v1",
            triggering_model_regression_check_id=None,
            resulting_model_promotion_id=promo3.id,
            decided_at=AS_OF + timedelta(days=2),
            approver="test-approver",
            rollback_rule_version="CRB-001",
        )
    )
    session.add(
        LearningCycle(
            started_at=AS_OF,
            new_outcomes_count=25,
            watermark_outcome_id=100,
            outcome="RAN",
            skip_reason=None,
            discovery_effectiveness_version="DE-001",
            calibration_candidate_version="CAL-001",
            candidate_model_evaluation_version="CME-001",
            model_promotion_id=promo1.id,
            cycle_rule_version="CLC-001",
        )
    )
    session.add(
        ShadowChallengerComparisonReport(
            challenger_model_version="model-v3",
            champion_model_version="model-v1",
            window_label="last-90d",
            sample_count=40,
            champion_success_rate=Decimal("0.55"),
            challenger_success_rate=Decimal("0.60"),
            success_rate_delta=Decimal("0.05"),
            champion_calibration_error=Decimal("0.10"),
            challenger_calibration_error=Decimal("0.08"),
            by_horizon=[],
            verdict="VALIDATED",
            computed_at=AS_OF + timedelta(days=3),
            comparison_rule_version="SCC-001",
        )
    )
    session.commit()

    resp = client.get("/api/v1/learning/summary")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["currentModelVersion"] == "model-v1"
    assert data["promotionCounts"] == {"promoted": 2, "rejected": 1}
    assert data["rollbackCount"] == 1
    assert data["latestRollback"]["rolledBackModelVersion"] == "model-v2"
    assert data["latestRollback"]["restoredModelVersion"] == "model-v1"
    assert data["lastCycle"]["outcome"] == "RAN"
    assert data["lastCycle"]["newOutcomesCount"] == 25
    assert data["championChallenger"]["challengerModelVersion"] == "model-v3"
    assert data["championChallenger"]["verdict"] == "VALIDATED"


def test_history_merges_all_event_types_sorted_desc_and_respects_limit(session, client):
    promo1 = _make_promotion(session, candidate="model-v1", baseline=None, decision=DECISION_PROMOTED, reason="VALIDATED", decided_at=AS_OF)
    _make_promotion(session, candidate="model-v2", baseline="model-v1", decision=DECISION_REJECTED, reason="REGRESSED", decided_at=AS_OF + timedelta(days=1))
    session.add(
        LearningCycle(
            started_at=AS_OF, new_outcomes_count=5, watermark_outcome_id=10, outcome="SKIPPED",
            skip_reason="INSUFFICIENT_NEW_EVIDENCE", discovery_effectiveness_version=None,
            calibration_candidate_version=None, candidate_model_evaluation_version=None,
            model_promotion_id=None, cycle_rule_version="CLC-001",
        )
    )
    session.add(
        ChampionRollback(
            rolled_back_model_version="model-v2", restored_model_version="model-v1",
            triggering_model_regression_check_id=None, resulting_model_promotion_id=promo1.id,
            decided_at=AS_OF + timedelta(days=2), approver="test-approver", rollback_rule_version="CRB-001",
        )
    )
    session.commit()

    resp = client.get("/api/v1/learning/history")
    assert resp.status_code == 200
    entries = resp.json()["data"]
    assert len(entries) == 4
    types = {e["type"] for e in entries}
    assert types == {"LEARNING_CYCLE", "PROMOTION", "REJECTION", "ROLLBACK"}
    # Sorted newest-first by createdAt (insertion order here, since all rows
    # share this test's ordering of session.add calls and default created_at).
    created_ats = [e["createdAt"] for e in entries]
    assert created_ats == sorted(created_ats, reverse=True)

    limited = client.get("/api/v1/learning/history", params={"limit": 2})
    assert len(limited.json()["data"]) == 2


def test_history_promotion_and_rejection_entries_carry_model_and_reason(session, client):
    _make_promotion(session, candidate="model-v1", baseline=None, decision=DECISION_PROMOTED, reason="VALIDATED", decided_at=AS_OF)
    _make_promotion(session, candidate="model-v2", baseline="model-v1", decision=DECISION_REJECTED, reason="REGRESSED", decided_at=AS_OF + timedelta(days=1))
    session.commit()

    entries = client.get("/api/v1/learning/history").json()["data"]
    promotion = next(e for e in entries if e["type"] == "PROMOTION")
    rejection = next(e for e in entries if e["type"] == "REJECTION")

    assert promotion["modelVersion"] == "model-v1"
    assert promotion["decisionReason"] == "VALIDATED"
    assert promotion["status"] == "PROMOTED"
    assert rejection["modelVersion"] == "model-v2"
    assert rejection["decisionReason"] == "REGRESSED"
    assert rejection["status"] == "REJECTED"


def _make_experiment(session, *, name, hypothesis="test hypothesis"):
    experiment = Experiment(name=name, hypothesis=hypothesis, experiment_version="EXP-001")
    session.add(experiment)
    session.flush()
    return experiment


def _make_arm(session, experiment, *, arm_name, model_version="test-model-1"):
    arm = ExperimentArm(
        experiment_id=experiment.id, arm_name=arm_name, model_version=model_version,
        window_label="w1", window_start=None, window_end=None, horizon_days_filter=None,
    )
    session.add(arm)
    session.flush()
    return arm


def _make_result(session, arm, *, verdict, accuracy=None, sample_count=25):
    result = ExperimentResult(
        experiment_arm_id=arm.id, sample_count=sample_count, accuracy=accuracy, avg_return=None,
        avg_drawdown=None, calibration_error=None, consistency_stdev=None, verdict=verdict,
        arm_config_snapshot={}, computed_at=AS_OF, framework_version="EXP-001",
    )
    session.add(result)
    session.flush()
    return result


def test_experiments_endpoint_classifies_status_and_picks_best_ready_arm(session, client):
    pending_exp = _make_experiment(session, name="pending-experiment")
    _make_arm(session, pending_exp, arm_name="baseline")

    insufficient_exp = _make_experiment(session, name="insufficient-experiment")
    insufficient_arm = _make_arm(session, insufficient_exp, arm_name="baseline")
    _make_result(session, insufficient_arm, verdict="INSUFFICIENT_SAMPLE", sample_count=3)

    ready_exp = _make_experiment(session, name="ready-experiment")
    baseline_arm = _make_arm(session, ready_exp, arm_name="baseline", model_version="v1")
    candidate_arm = _make_arm(session, ready_exp, arm_name="candidate", model_version="v2")
    _make_result(session, baseline_arm, verdict="READY", accuracy=Decimal("0.55"))
    _make_result(session, candidate_arm, verdict="READY", accuracy=Decimal("0.70"))

    session.add(
        FeedbackDrivenExperiment(
            experiment_id=ready_exp.id, feedback_category=CATEGORY_TARGET, feedback_reason_code=REASON_TOO_HIGH,
            evaluated_count_at_creation=40, distinct_user_count_at_creation=5, repeated_prediction_count_at_creation=2,
            success_rate_at_creation=Decimal("0.20"), pipeline_version="FEP-001",
        )
    )
    session.commit()

    experiments = {e["name"]: e for e in client.get("/api/v1/learning/experiments").json()["data"]}

    assert experiments["pending-experiment"]["status"] == "PENDING"
    assert experiments["pending-experiment"]["feedbackDriven"] is False

    assert experiments["insufficient-experiment"]["status"] == "INSUFFICIENT_SAMPLE"

    ready = experiments["ready-experiment"]
    assert ready["status"] == "READY"
    assert ready["bestArmName"] == "candidate"
    assert ready["feedbackDriven"] is True
    assert ready["feedbackCategory"] == CATEGORY_TARGET
    assert ready["feedbackReasonCode"] == REASON_TOO_HIGH
    assert len(ready["arms"]) == 2


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
        model_version="test-model-1", feature_version="FV-001",
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


def test_summary_surfaces_a_genuine_weak_feedback_signal_as_a_failure_pattern(session, client):
    scan = _make_scan(session, date(2027, 1, 1))
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        prediction = _make_evaluated(session, scan, f"F{i}", as_of=AS_OF, win=False)
        submit_feedback(session, prediction, user_id=f"user-{i}", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)
    for i in range(total):
        prediction = _make_evaluated(session, scan, f"S{i}", as_of=AS_OF, win=True)
        submit_feedback(session, prediction, user_id=f"user-s{i}", category=CATEGORY_TARGET, reason_code=REASON_AGREE, submitted_at=AS_OF)
    session.commit()

    resp = client.get("/api/v1/learning/summary")
    data = resp.json()["data"]

    assert data["failurePatternCount"] >= 1
    weak_signal = next(s for s in data["recentSignals"] if s["verdict"] == VERDICT_WEAK)
    assert weak_signal["reasonCode"] == REASON_TOO_HIGH
    ok_reason_codes = {s["reasonCode"] for s in data["recentSignals"] if s["verdict"] == VERDICT_OK}
    assert REASON_AGREE in ok_reason_codes
