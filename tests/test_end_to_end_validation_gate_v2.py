from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.end_to_end_validation_gate_v2 import (
    CHECK_CHAMPION_CHALLENGER_SHADOWING,
    CHECK_EVENT_DRIVEN_REVISION_AND_FRESHNESS,
    CHECK_EXECUTION_COST_ASSUMPTIONS,
    CHECK_FAIL,
    CHECK_HORIZON_COVERAGE,
    CHECK_IMMUTABLE_HISTORY_AND_REPLAY,
    CHECK_INSUFFICIENT_EVIDENCE,
    CHECK_MODEL_PROVIDER_COST_VS_VALUE,
    CHECK_PASS,
    CHECK_PORTFOLIO_AND_CROSS_SECTIONAL_RANKING,
    CHECK_POSITIVE_ONLY_AND_ABSTENTION,
    CHECK_PROVIDER_PROVENANCE,
    CHECK_PURGED_EMBARGOED_VALIDATION,
    CHECK_TARGET_STOP_HORIZON_CLOSURE,
    CHECK_TRUST_SCORE_RISE_AND_REGRESSION,
    GATE_V2_VERSION,
    OVERALL_NOT_READY,
    _champion_challenger_shadowing_check,
    _event_driven_revision_and_freshness_check,
    _execution_cost_assumptions_check,
    _horizon_coverage_check,
    _immutable_history_and_replay_check,
    _model_provider_cost_vs_value_check,
    _portfolio_and_cross_sectional_ranking_check,
    _positive_only_and_abstention_check,
    _provider_provenance_check,
    _purged_embargoed_validation_check,
    _target_stop_horizon_closure_check,
    _trust_score_rise_and_regression_check,
    compile_end_to_end_validation_report,
    get_validation_gate_report_history,
)
from app.model_regression_detection import VERDICT_HEALTHY, VERDICT_REGRESSED
from app.models import (
    ChampionRollback,
    CostQualityTradeoffReport,
    DailyPredictionSnapshot,
    ExecutionCostAssessment,
    InformationLatencyAssessment,
    MicrostructureSnapshot,
    ModelPromotion,
    ModelRegressionCheck,
    Prediction,
    PredictionFreshnessDecision,
    PredictionOutcomeEvent,
    PortfolioSelectionEffectivenessReport,
    RankingEffectivenessReport,
    ReplayRun,
    ResolvedFact,
    SegmentAbstentionQualityReport,
    ShadowChallengerComparisonReport,
    Stock,
    TemporalValidationPolicyDecision,
)
from app.prediction_outcome_monitor import STATE_TARGET_HIT
from app.purged_embargo_validation import POLICY_VERDICT_FAIL, POLICY_VERDICT_PASS
from app.recommendations import record_recommendation

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)


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


def _make_prediction(session, *, model_version="m1"):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return record_recommendation(
        session, stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=5,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=model_version, feature_version="f1", consensus_contract_version="c1",
        horizon_selection_version="h1", scoring_contract_version="s1", opportunity_score=Decimal("60.00"),
    )


def test_full_report_is_all_insufficient_evidence_on_empty_database(session):
    report = compile_end_to_end_validation_report(session, model_version="m1", computed_at=AS_OF)

    assert report.overall_verdict == OVERALL_NOT_READY
    assert len(report.blocking_issues) == len(report.check_results)
    assert all(c["status"] != CHECK_PASS for c in report.check_results)
    assert report.gate_rule_version == GATE_V2_VERSION
    assert len(get_validation_gate_report_history(session, "m1")) == 1


def test_horizon_coverage_insufficient_then_pass(session):
    result = _horizon_coverage_check(session)
    assert result["check"] == CHECK_HORIZON_COVERAGE
    assert result["status"] == CHECK_INSUFFICIENT_EVIDENCE


def test_purged_embargoed_validation_pass_and_fail(session):
    insufficient = _purged_embargoed_validation_check(session, "m1")
    assert insufficient["status"] == CHECK_INSUFFICIENT_EVIDENCE

    session.add(TemporalValidationPolicyDecision(
        model_version="m1", fold_ids=[1], verdict=POLICY_VERDICT_PASS, fail_reasons=[],
        evaluated_at=AS_OF, policy_version="PEV-001",
    ))
    session.commit()
    passing = _purged_embargoed_validation_check(session, "m1")
    assert passing["check"] == CHECK_PURGED_EMBARGOED_VALIDATION
    assert passing["status"] == CHECK_PASS

    session.add(TemporalValidationPolicyDecision(
        model_version="m1", fold_ids=[2], verdict=POLICY_VERDICT_FAIL, fail_reasons=["EMBARGO_VIOLATION"],
        evaluated_at=AS_OF + timedelta(days=1), policy_version="PEV-001",
    ))
    session.commit()
    failing = _purged_embargoed_validation_check(session, "m1")
    assert failing["status"] == CHECK_FAIL


def test_execution_cost_assumptions_check(session):
    assert _execution_cost_assumptions_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    prediction = _make_prediction(session)
    session.add(ExecutionCostAssessment(
        prediction_id=prediction.id, gross_return=Decimal("0.05"), liquidity_bucket="HIGH",
        executability_verdict="EXECUTABLE", estimated_cost_percent=Decimal("0.002"), net_return=Decimal("0.048"),
        cost_model_version="ECM-001", assessed_at=AS_OF,
    ))
    session.commit()
    assert _execution_cost_assumptions_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE  # still missing microstructure

    session.add(MicrostructureSnapshot(
        prediction_id=prediction.id, liquidity_bucket="HIGH", previous_liquidity_bucket=None, liquidity_regime_changed=False,
        average_daily_turnover=Decimal("1000000.00"), gap_percent=Decimal("0.01"), gap_bucket="LOW",
        probable_circuit_band_event=False, recorded_at=AS_OF, snapshot_version="MLI-001",
    ))
    session.commit()
    result = _execution_cost_assumptions_check(session)
    assert result["check"] == CHECK_EXECUTION_COST_ASSUMPTIONS
    assert result["status"] == CHECK_PASS


def test_target_stop_horizon_closure_check(session):
    assert _target_stop_horizon_closure_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    prediction = _make_prediction(session)
    session.add(PredictionOutcomeEvent(
        prediction_id=prediction.id, state=STATE_TARGET_HIT, detected_at=AS_OF, observed_at=AS_OF,
        observed_price=Decimal("105"), provider="yahoo", prediction_version="v1", evidence={},
        monitor_rule_version="RTM-001",
    ))
    session.commit()
    result = _target_stop_horizon_closure_check(session)
    assert result["check"] == CHECK_TARGET_STOP_HORIZON_CLOSURE
    assert result["status"] == CHECK_PASS


def test_event_driven_revision_and_freshness_check(session):
    assert _event_driven_revision_and_freshness_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    prediction = _make_prediction(session)
    session.add(PredictionFreshnessDecision(
        prediction_id=prediction.id, revalidation_outcome="NO_ACTION_NEEDED", triggers=[], re_analysis_recommended=False,
        revision_trigger_reason=None, evaluated_at=AS_OF, engine_rule_version="PFE-001",
    ))
    session.commit()
    assert _event_driven_revision_and_freshness_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE  # still missing latency

    session.add(InformationLatencyAssessment(
        prediction_id=prediction.id, horizon_days=5, sla_multiplier=Decimal("1.0"), category_latency_seconds={},
        sla_violations=[], suppress_eligibility=False, reasons=[], evaluated_at=AS_OF, latency_rule_version="ILT-001",
    ))
    session.commit()
    result = _event_driven_revision_and_freshness_check(session)
    assert result["check"] == CHECK_EVENT_DRIVEN_REVISION_AND_FRESHNESS
    assert result["status"] == CHECK_PASS


def test_provider_provenance_check(session):
    assert _provider_provenance_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    stock = Stock(symbol="BBB", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(ResolvedFact(
        fact_type="FUNDAMENTAL_EPS", stock_id=stock.id, fact_key="eps_q1", resolved_value_numeric=Decimal("12.5"),
        resolved_value_text=None, winning_source="provider_a", winning_source_authority_tier=Decimal("1.0"),
        source_count=2, sources_considered=["provider_a", "provider_b"], conflicting=False, resolution_reason="AUTHORITY_TIER",
        confidence=Decimal("0.9"), resolved_at=AS_OF, resolution_rule_version="SAR-001",
    ))
    session.commit()
    result = _provider_provenance_check(session)
    assert result["check"] == CHECK_PROVIDER_PROVENANCE
    assert result["status"] == CHECK_PASS


def test_champion_challenger_shadowing_check(session):
    assert _champion_challenger_shadowing_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    session.add(ShadowChallengerComparisonReport(
        challenger_model_version="chal-1", champion_model_version="champ-1", window_label="w", sample_count=20,
        champion_success_rate=Decimal("0.7"), challenger_success_rate=Decimal("0.75"), success_rate_delta=Decimal("0.05"),
        champion_calibration_error=Decimal("0.1"), challenger_calibration_error=Decimal("0.09"), by_horizon=[],
        verdict="VALIDATED", computed_at=AS_OF, comparison_rule_version="SCC-001",
    ))
    session.commit()
    result = _champion_challenger_shadowing_check(session)
    assert result["check"] == CHECK_CHAMPION_CHALLENGER_SHADOWING
    assert result["status"] == CHECK_PASS
    assert "0 rollback(s)" in result["detail"]


def test_trust_score_rise_and_regression_check_requires_both_verdicts(session):
    assert _trust_score_rise_and_regression_check(session, "m1")["status"] == CHECK_INSUFFICIENT_EVIDENCE

    session.add(ModelRegressionCheck(
        model_version="m1", baseline_window_label="b", baseline_success_rate=Decimal("0.7"), baseline_sample_count=30,
        monitoring_window_label="m", monitoring_success_rate=Decimal("0.72"), monitoring_sample_count=30,
        verdict=VERDICT_HEALTHY, segment_regressions=[], rollback_triggered=False, checked_at=AS_OF, detection_rule_version="MRD-001",
    ))
    session.commit()
    only_healthy = _trust_score_rise_and_regression_check(session, "m1")
    assert only_healthy["status"] == CHECK_INSUFFICIENT_EVIDENCE

    session.add(ModelRegressionCheck(
        model_version="m1", baseline_window_label="b", baseline_success_rate=Decimal("0.7"), baseline_sample_count=30,
        monitoring_window_label="m2", monitoring_success_rate=Decimal("0.5"), monitoring_sample_count=30,
        verdict=VERDICT_REGRESSED, segment_regressions=[], rollback_triggered=True, checked_at=AS_OF + timedelta(days=1), detection_rule_version="MRD-001",
    ))
    session.commit()
    result = _trust_score_rise_and_regression_check(session, "m1")
    assert result["check"] == CHECK_TRUST_SCORE_RISE_AND_REGRESSION
    assert result["status"] == CHECK_PASS


def test_positive_only_and_abstention_check(session):
    assert _positive_only_and_abstention_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    session.add(SegmentAbstentionQualityReport(
        window_label="w", sample_count=20, segment_breakdown=[], verdict="LEARNING_HEALTHY",
        computed_at=AS_OF, report_rule_version="SAQ-001",
    ))
    session.commit()
    result = _positive_only_and_abstention_check(session)
    assert result["check"] == CHECK_POSITIVE_ONLY_AND_ABSTENTION
    assert result["status"] == CHECK_PASS


def test_immutable_history_and_replay_check(session):
    assert _immutable_history_and_replay_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    prediction = _make_prediction(session)
    session.add(DailyPredictionSnapshot(
        prediction_id=prediction.id, recommendation_decision_trace_id=None, prediction_trust_score_id=None,
        snapshot_date=AS_OF.date(), is_canonical=True, snapshotted_at=AS_OF, snapshot_rule_version="DPS-001",
    ))
    session.commit()
    assert _immutable_history_and_replay_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE  # still missing replay

    session.add(ReplayRun(
        recommendation_generation_id=1, replayed_at=AS_OF, limitation=None, replayed_qualifies=True,
        replayed_failed_criteria=[], replayed_opportunity_score=Decimal("60.00"), replayed_horizon_days=5,
        replayed_predicted_probability=Decimal("0.7"), replayed_model_version="m1", replayed_feature_version="f1",
        replayed_consensus_contract_version="c1", replayed_scoring_contract_version="s1", replayed_horizon_selection_version="h1",
        matches_original=True, replay_rule_version="RR-001",
    ))
    session.commit()
    result = _immutable_history_and_replay_check(session)
    assert result["check"] == CHECK_IMMUTABLE_HISTORY_AND_REPLAY
    assert result["status"] == CHECK_PASS


def test_portfolio_and_cross_sectional_ranking_check(session):
    assert _portfolio_and_cross_sectional_ranking_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    session.add(RankingEffectivenessReport(
        window_label="w", top_k=5, composite_sample_count=20, composite_success_count=12, composite_success_rate=Decimal("0.6"),
        alternative_sample_count=20, alternative_success_count=10, alternative_success_rate=Decimal("0.5"),
        success_rate_delta=Decimal("0.1"), verdict="COMPOSITE_BETTER", computed_at=AS_OF, effectiveness_rule_version="CSR-001",
    ))
    session.commit()
    assert _portfolio_and_cross_sectional_ranking_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE  # still missing portfolio

    prediction = _make_prediction(session)
    session.add(PortfolioSelectionEffectivenessReport(
        window_label="w", top_k=5, diversified_sample_count=20, diversified_success_count=13, diversified_success_rate=Decimal("0.65"),
        raw_sample_count=20, raw_success_count=12, raw_success_rate=Decimal("0.6"), success_rate_delta=Decimal("0.05"),
        verdict="DIVERSIFIED_BETTER", computed_at=AS_OF, effectiveness_rule_version="PSE-001",
    ))
    session.commit()
    result = _portfolio_and_cross_sectional_ranking_check(session)
    assert result["check"] == CHECK_PORTFOLIO_AND_CROSS_SECTIONAL_RANKING
    assert result["status"] == CHECK_PASS


def test_model_provider_cost_vs_value_check(session):
    assert _model_provider_cost_vs_value_check(session)["status"] == CHECK_INSUFFICIENT_EVIDENCE

    session.add(CostQualityTradeoffReport(
        data_type="MARKET_DATA", provider_candidates=["yahoo"], recommended_provider_id="yahoo", best_free_provider_id="yahoo",
        quality_floor=Decimal("0.8"), verdict="COST_OPTIMIZED_SELECTION", computed_at=AS_OF, report_rule_version="CQO-001",
    ))
    session.commit()
    result = _model_provider_cost_vs_value_check(session)
    assert result["check"] == CHECK_MODEL_PROVIDER_COST_VS_VALUE
    assert result["status"] == CHECK_PASS


def test_report_is_always_freshly_computed_never_idempotent(session):
    first = compile_end_to_end_validation_report(session, model_version="m1", computed_at=AS_OF)
    second = compile_end_to_end_validation_report(session, model_version="m1", computed_at=AS_OF)

    assert first.id != second.id
    assert len(get_validation_gate_report_history(session, "m1")) == 2
