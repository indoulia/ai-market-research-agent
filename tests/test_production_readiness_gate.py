from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.model_regression_detection import VERDICT_HEALTHY
from app.models import (
    BiasGuardCheck,
    ModelRegressionCheck,
    Prediction,
    PredictionOutcome,
    PredictionQualityBenchmarkReport,
    PredictionTrustScore,
    PredictionUsefulnessAssessment,
    ProviderOutageSnapshot,
    Stock,
)
from app.out_of_sample_validation import EvaluationWindow
from app.production_readiness_gate import (
    BRIER_SCORE_ACCEPTABLE_THRESHOLD,
    CHECK_FAIL,
    CHECK_INSUFFICIENT_EVIDENCE,
    CHECK_PASS,
    OVERALL_NOT_READY,
    OVERALL_READY,
    READINESS_GATE_VERSION,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_MEASURED,
    _benchmark_performance_documented_check,
    _continuous_operation_check,
    _integrity_and_reproducibility_check,
    _promotion_regression_learning_loop_check,
    _trust_usefulness_monotonicity_check,
    compile_release_readiness_report,
    compute_probabilistic_scores,
    get_readiness_report_history,
)
from app.provider_outage_tracker import SEVERITY_NONE, SEVERITY_TOTAL

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
WINDOW = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))
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


def _make_prediction(session, *, predicted_probability=Decimal("0.7"), model_version=MODEL_VERSION):
    n = next(_counter)
    stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=predicted_probability,
        confidence=Decimal("0.8"), model_version=model_version, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.commit()
    return prediction


def _add_outcome(session, prediction, outcome):
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("95"),
        closing_price=Decimal("105"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.05"),
        actual_return=Decimal("0.05") if outcome == "SUCCESS" else Decimal("-0.03"), prediction_error=Decimal("0.01"),
        target_hit=(outcome == "SUCCESS"), stop_hit=(outcome == "FAILURE"), outcome=outcome,
    ))
    session.commit()


def test_probabilistic_scores_insufficient_sample(session):
    report = compute_probabilistic_scores(session, model_version=MODEL_VERSION, window=WINDOW, computed_at=AS_OF)

    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert report.brier_score is None
    assert report.report_rule_version == READINESS_GATE_VERSION


def test_probabilistic_scores_measured_perfect_confidence(session):
    # 20 predictions, p=0.9, all SUCCESS -> brier = (0.1)^2 = 0.01; well below threshold.
    for _ in range(20):
        prediction = _make_prediction(session, predicted_probability=Decimal("0.9"))
        _add_outcome(session, prediction, "SUCCESS")

    report = compute_probabilistic_scores(session, model_version=MODEL_VERSION, window=WINDOW, computed_at=AS_OF)

    assert report.verdict == VERDICT_MEASURED
    assert report.brier_score == Decimal("0.01")
    assert report.brier_score <= BRIER_SCORE_ACCEPTABLE_THRESHOLD


def test_probabilistic_scores_poorly_calibrated(session):
    # 20 predictions, p=0.9, all FAILURE -> brier = (0.9)^2 = 0.81; well above threshold.
    for _ in range(20):
        prediction = _make_prediction(session, predicted_probability=Decimal("0.9"))
        _add_outcome(session, prediction, "FAILURE")

    report = compute_probabilistic_scores(session, model_version=MODEL_VERSION, window=WINDOW, computed_at=AS_OF)

    assert report.brier_score == Decimal("0.81")
    assert report.brier_score > BRIER_SCORE_ACCEPTABLE_THRESHOLD


def test_integrity_check_fails_on_biasguard_blocked(session):
    prediction = _make_prediction(session)
    session.add(BiasGuardCheck(
        prediction_id=prediction.id, workflow_type="DISCOVERY", verdict="BLOCKED", reason_codes=["LEAKAGE"],
        evidence={}, checked_at=AS_OF, guard_rule_version="BGC-001",
    ))
    session.commit()

    result = _integrity_and_reproducibility_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_FAIL


def test_integrity_check_passes_when_no_blocked_checks(session):
    _make_prediction(session)

    result = _integrity_and_reproducibility_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_PASS


def test_continuous_operation_fails_on_total_outage(session):
    session.add(ProviderOutageSnapshot(
        data_type="MARKET_DATA", total_registered_providers=2, healthy_provider_count=0, degraded_provider_count=2,
        degraded_provider_ids=["yahoo-finance", "upstox-v3"], severity=SEVERITY_TOTAL, evaluated_at=AS_OF,
        snapshot_rule_version="POT-001",
    ))
    session.commit()

    result = _continuous_operation_check(session)

    assert result["status"] == CHECK_FAIL


def test_continuous_operation_passes_when_no_total_outage(session):
    session.add(ProviderOutageSnapshot(
        data_type="MARKET_DATA", total_registered_providers=2, healthy_provider_count=2, degraded_provider_count=0,
        degraded_provider_ids=[], severity=SEVERITY_NONE, evaluated_at=AS_OF, snapshot_rule_version="POT-001",
    ))
    session.commit()

    result = _continuous_operation_check(session)

    assert result["status"] == CHECK_PASS


def _add_trust_and_usefulness(session, *, trust_quality, usefulness_verdict, count):
    for _ in range(count):
        prediction = _make_prediction(session)
        session.add(PredictionTrustScore(
            prediction_id=prediction.id, overall_trust_score=Decimal("0.5"), trust_quality=trust_quality,
            calibration_component=None, historical_accuracy_component=None, recent_performance_component=None,
            horizon_reliability_component=None, regime_reliability_component=None, evidence_quality_component=None,
            available_component_count=1, reasons=[], computed_at=AS_OF, trust_score_version="PTS-001",
        ))
        session.add(PredictionUsefulnessAssessment(
            prediction_id=prediction.id, directional_outcome="SUCCESS", risk_adjusted_ratio=Decimal("1.5"),
            usefulness_verdict=usefulness_verdict, assessed_at=AS_OF, usefulness_rule_version="PUM-001",
        ))
    session.commit()


def test_monotonicity_check_insufficient_with_one_bucket(session):
    _add_trust_and_usefulness(session, trust_quality="HIGH", usefulness_verdict="USEFUL", count=20)

    result = _trust_usefulness_monotonicity_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_INSUFFICIENT_EVIDENCE


def test_monotonicity_check_passes_when_non_decreasing(session):
    _add_trust_and_usefulness(session, trust_quality="LOW", usefulness_verdict="NOT_USEFUL", count=20)
    _add_trust_and_usefulness(session, trust_quality="HIGH", usefulness_verdict="USEFUL", count=20)

    result = _trust_usefulness_monotonicity_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_PASS


def test_monotonicity_check_fails_when_inverted(session):
    _add_trust_and_usefulness(session, trust_quality="LOW", usefulness_verdict="USEFUL", count=20)
    _add_trust_and_usefulness(session, trust_quality="HIGH", usefulness_verdict="NOT_USEFUL", count=20)

    result = _trust_usefulness_monotonicity_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_FAIL


def test_benchmark_documented_check_insufficient_when_missing(session):
    result = _benchmark_performance_documented_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_INSUFFICIENT_EVIDENCE


def test_promotion_loop_insufficient_when_no_regression_checks(session):
    result = _promotion_regression_learning_loop_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_INSUFFICIENT_EVIDENCE


def test_promotion_loop_passes_when_regression_check_exists(session):
    session.add(ModelRegressionCheck(
        model_version=MODEL_VERSION, baseline_window_label="baseline", baseline_success_rate=Decimal("0.8"),
        baseline_sample_count=25, monitoring_window_label="monitoring", monitoring_success_rate=Decimal("0.8"),
        monitoring_sample_count=25, verdict=VERDICT_HEALTHY, segment_regressions=[], rollback_triggered=False,
        checked_at=AS_OF, detection_rule_version="MRD-001",
    ))
    session.commit()

    result = _promotion_regression_learning_loop_check(session, MODEL_VERSION)

    assert result["status"] == CHECK_PASS


def test_overall_not_ready_when_nothing_computed(session):
    report = compile_release_readiness_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)

    assert report.overall_verdict == OVERALL_NOT_READY
    assert len(report.blocking_issues) > 0


def test_overall_ready_when_all_checks_pass(session):
    # 1) Integrity: no BiasGuardCheck at all -> PASS by construction.
    # 2) Probabilistic calibration: well-calibrated predictions.
    for _ in range(20):
        prediction = _make_prediction(session, predicted_probability=Decimal("0.9"))
        _add_outcome(session, prediction, "SUCCESS")
    compute_probabilistic_scores(session, model_version=MODEL_VERSION, window=WINDOW, computed_at=AS_OF)
    # 3) Trust/usefulness monotonicity.
    _add_trust_and_usefulness(session, trust_quality="LOW", usefulness_verdict="NOT_USEFUL", count=20)
    _add_trust_and_usefulness(session, trust_quality="HIGH", usefulness_verdict="USEFUL", count=20)
    # 4) Benchmark documented.
    session.add(PredictionQualityBenchmarkReport(
        model_version=MODEL_VERSION, window_label="w", sample_count=25, directional_accuracy=Decimal("0.6"),
        target_hit_rate=Decimal("0.5"), stop_hit_rate=Decimal("0.2"), avg_expected_return=Decimal("0.05"),
        avg_realized_return=Decimal("0.04"), avg_max_favorable_excursion=Decimal("0.06"),
        avg_max_adverse_excursion=Decimal("-0.02"), avg_time_to_exit_days=Decimal("3"), benchmark_stock_id=None,
        avg_benchmark_return=None, avg_excess_return=None, benchmark_coverage_count=0, benchmark_verdict="NO_BENCHMARK_DATA",
        segment_breakdown=[], verdict="MEASURED", trust_reduction_recommended=False, computed_at=AS_OF,
        benchmark_rule_version="PQB-001",
    ))
    # 5) Continuous operation: no total outage.
    session.add(ProviderOutageSnapshot(
        data_type="MARKET_DATA", total_registered_providers=1, healthy_provider_count=1, degraded_provider_count=0,
        degraded_provider_ids=[], severity=SEVERITY_NONE, evaluated_at=AS_OF, snapshot_rule_version="POT-001",
    ))
    # 6) Promotion/regression/learning loop.
    session.add(ModelRegressionCheck(
        model_version=MODEL_VERSION, baseline_window_label="baseline", baseline_success_rate=Decimal("0.8"),
        baseline_sample_count=25, monitoring_window_label="monitoring", monitoring_success_rate=Decimal("0.8"),
        monitoring_sample_count=25, verdict=VERDICT_HEALTHY, segment_regressions=[], rollback_triggered=False,
        checked_at=AS_OF, detection_rule_version="MRD-001",
    ))
    session.commit()

    report = compile_release_readiness_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)

    assert report.overall_verdict == OVERALL_READY, report.blocking_issues
    assert report.blocking_issues == []


def test_idempotent_report_history(session):
    compile_release_readiness_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)
    compile_release_readiness_report(session, model_version=MODEL_VERSION, computed_at=AS_OF + timedelta(hours=1))

    assert len(get_readiness_report_history(session, MODEL_VERSION)) == 2
