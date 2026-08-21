"""EPIC-M1.131: the final evidence gate declaring the MRA prediction
architecture complete -- a superset of M1.117's own release-readiness
gate, extended with every capability built since (M1.119-M1.130).

`compile_end_to_end_validation_report` deliberately recomputes almost
nothing new: it embeds M1.117's own `compile_release_readiness_report`
verdict as one check, then adds one check per this EPIC's own remaining
scope bullets, each reading an already-persisted report/decision table
from the EPIC that owns that capability -- never a second, competing
measurement of something another EPIC already measures.

Every check is honest about insufficient evidence, mirroring M1.117's
own posture exactly: a check that finds no data at all is
`CHECK_INSUFFICIENT_EVIDENCE`, never a silent pass (AC: "insufficient
evidence is not converted into a pass"). The overall verdict is
`READY_FOR_PRODUCTION_V2` only when every check is an explicit
`CHECK_PASS`; any `CHECK_FAIL` or `CHECK_INSUFFICIENT_EVIDENCE` keeps
the system `NOT_READY`, named in `blocking_issues` (AC: "no critical
gate can be bypassed because aggregate accuracy looks good"). This
module never promotes, suppresses or gates anything itself -- read-only,
matching M1.117's own non-goal.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .champion_challenger_shadow import get_rollback_history
from .model_regression_detection import VERDICT_HEALTHY, VERDICT_REGRESSED, get_regression_history
from .models import (
    ChampionRollback,
    CostQualityTradeoffReport,
    DailyPredictionSnapshot,
    EndToEndValidationGateReport,
    ExecutionCostAssessment,
    InformationLatencyAssessment,
    MicrostructureSnapshot,
    ModelRegressionCheck,
    Prediction,
    PredictionFreshnessDecision,
    PredictionOutcome,
    PredictionOutcomeEvent,
    PortfolioSelectionEffectivenessReport,
    RankingEffectivenessReport,
    ReplayRun,
    ResolvedFact,
    SegmentAbstentionQualityReport,
    ShadowChallengerComparisonReport,
    TemporalValidationPolicyDecision,
)
from .prediction_outcome_monitor import TERMINAL_STATES
from .production_readiness_gate import OVERALL_READY, compile_release_readiness_report
from .purged_embargo_validation import POLICY_VERDICT_PASS
from .recommendations import VALID_HORIZON_DAYS
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

GATE_V2_VERSION = "E2E-131-001"

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
CHECK_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

OVERALL_READY_V2 = "READY_FOR_PRODUCTION_V2"
OVERALL_NOT_READY = "NOT_READY"

CHECK_RELEASE_READINESS_V1 = "RELEASE_READINESS_V1"
CHECK_HORIZON_COVERAGE = "HORIZON_COVERAGE"
CHECK_PURGED_EMBARGOED_VALIDATION = "PURGED_EMBARGOED_VALIDATION"
CHECK_EXECUTION_COST_ASSUMPTIONS = "EXECUTION_COST_ASSUMPTIONS"
CHECK_TARGET_STOP_HORIZON_CLOSURE = "TARGET_STOP_HORIZON_CLOSURE"
CHECK_EVENT_DRIVEN_REVISION_AND_FRESHNESS = "EVENT_DRIVEN_REVISION_AND_FRESHNESS"
CHECK_PROVIDER_PROVENANCE = "PROVIDER_PROVENANCE"
CHECK_CHAMPION_CHALLENGER_SHADOWING = "CHAMPION_CHALLENGER_SHADOWING"
CHECK_TRUST_SCORE_RISE_AND_REGRESSION = "TRUST_SCORE_RISE_AND_REGRESSION"
CHECK_POSITIVE_ONLY_AND_ABSTENTION = "POSITIVE_ONLY_AND_ABSTENTION"
CHECK_IMMUTABLE_HISTORY_AND_REPLAY = "IMMUTABLE_HISTORY_AND_REPLAY"
CHECK_PORTFOLIO_AND_CROSS_SECTIONAL_RANKING = "PORTFOLIO_AND_CROSS_SECTIONAL_RANKING"
CHECK_MODEL_PROVIDER_COST_VS_VALUE = "MODEL_PROVIDER_COST_VS_VALUE"

# Named, not fabricated: this platform's actually-supported horizons
# (app.recommendations.VALID_HORIZON_DAYS) differ from the EPIC's own
# scope text ("1/2/3/5/7") -- there is no 2-day horizon in this system.
# Validating a horizon that does not exist would be a fabricated check,
# so this gate validates the real set and says so explicitly.
_SCOPE_TEXT_HORIZONS = (1, 2, 3, 5, 7)


def _release_readiness_v1_check(session: Session, model_version: str, computed_at: datetime) -> dict:
    report = compile_release_readiness_report(session, model_version=model_version, computed_at=computed_at)
    if report.overall_verdict == OVERALL_READY:
        return {"check": CHECK_RELEASE_READINESS_V1, "status": CHECK_PASS, "detail": "M1.117 release-readiness gate: READY_FOR_PRODUCTION"}
    return {
        "check": CHECK_RELEASE_READINESS_V1, "status": CHECK_FAIL,
        "detail": f"M1.117 release-readiness gate NOT_READY, blocking: {report.blocking_issues}",
    }


def _horizon_coverage_check(session: Session) -> dict:
    unsupported = [h for h in _SCOPE_TEXT_HORIZONS if h not in VALID_HORIZON_DAYS]
    insufficient = []
    for horizon_days in VALID_HORIZON_DAYS:
        sample_count = len(session.scalars(
            select(Prediction.id)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .where(Prediction.horizon_days == horizon_days, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
        ).all())
        if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
            insufficient.append(horizon_days)

    detail = f"supported horizons {VALID_HORIZON_DAYS} (scope text names {_SCOPE_TEXT_HORIZONS}; {sorted(unsupported)} not a real horizon on this platform)"
    if insufficient:
        return {"check": CHECK_HORIZON_COVERAGE, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": f"{detail}; insufficient sample for horizon(s) {insufficient}"}
    return {"check": CHECK_HORIZON_COVERAGE, "status": CHECK_PASS, "detail": detail}


def _purged_embargoed_validation_check(session: Session, model_version: str) -> dict:
    latest = session.scalar(
        select(TemporalValidationPolicyDecision)
        .where(TemporalValidationPolicyDecision.model_version == model_version)
        .order_by(TemporalValidationPolicyDecision.id.desc())
    )
    if latest is None:
        return {"check": CHECK_PURGED_EMBARGOED_VALIDATION, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no M1.125 temporal validation policy decision computed yet"}
    if latest.verdict == POLICY_VERDICT_PASS:
        return {"check": CHECK_PURGED_EMBARGOED_VALIDATION, "status": CHECK_PASS, "detail": "M1.125 purged/embargoed policy decision: PASS"}
    return {"check": CHECK_PURGED_EMBARGOED_VALIDATION, "status": CHECK_FAIL, "detail": f"M1.125 purged/embargoed policy decision FAILED: {latest.fail_reasons}"}


def _execution_cost_assumptions_check(session: Session) -> dict:
    has_cost_assessment = session.scalar(select(ExecutionCostAssessment.id).limit(1))
    has_microstructure_snapshot = session.scalar(select(MicrostructureSnapshot.id).limit(1))
    missing = [
        name
        for name, present in (("M1.98 execution cost assessments", has_cost_assessment), ("M1.128 microstructure/liquidity snapshots", has_microstructure_snapshot))
        if present is None
    ]
    if missing:
        return {"check": CHECK_EXECUTION_COST_ASSUMPTIONS, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": f"missing: {missing}"}
    return {"check": CHECK_EXECUTION_COST_ASSUMPTIONS, "status": CHECK_PASS, "detail": "M1.98 execution cost assessments and M1.128 microstructure/liquidity snapshots both present"}


def _target_stop_horizon_closure_check(session: Session) -> dict:
    terminal_count = session.scalar(select(PredictionOutcomeEvent.id).where(PredictionOutcomeEvent.state.in_(tuple(TERMINAL_STATES))).limit(1))
    if terminal_count is None:
        return {"check": CHECK_TARGET_STOP_HORIZON_CLOSURE, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no M1.119 terminal outcome-monitor event recorded yet"}
    return {"check": CHECK_TARGET_STOP_HORIZON_CLOSURE, "status": CHECK_PASS, "detail": "M1.119 has recorded terminal target/stop/horizon-expiry closures"}


def _event_driven_revision_and_freshness_check(session: Session) -> dict:
    has_freshness = session.scalar(select(PredictionFreshnessDecision.id).limit(1))
    has_latency = session.scalar(select(InformationLatencyAssessment.id).limit(1))
    missing = [name for name, present in (("M1.105 freshness decisions", has_freshness), ("M1.126 latency assessments", has_latency)) if present is None]
    if missing:
        return {"check": CHECK_EVENT_DRIVEN_REVISION_AND_FRESHNESS, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": f"missing: {missing}"}
    return {"check": CHECK_EVENT_DRIVEN_REVISION_AND_FRESHNESS, "status": CHECK_PASS, "detail": "M1.105 freshness decisions and M1.126 latency assessments both present"}


def _provider_provenance_check(session: Session) -> dict:
    has_resolved_fact = session.scalar(select(ResolvedFact.id).limit(1))
    if has_resolved_fact is None:
        return {"check": CHECK_PROVIDER_PROVENANCE, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no M1.127 resolved-fact provenance record yet"}
    return {"check": CHECK_PROVIDER_PROVENANCE, "status": CHECK_PASS, "detail": "M1.127 source-authority provenance resolution present"}


def _champion_challenger_shadowing_check(session: Session) -> dict:
    has_comparison = session.scalar(select(ShadowChallengerComparisonReport.id).limit(1))
    if has_comparison is None:
        return {"check": CHECK_CHAMPION_CHALLENGER_SHADOWING, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no M1.123 shadow comparison report computed yet"}
    rollback_count = len(get_rollback_history(session))
    return {
        "check": CHECK_CHAMPION_CHALLENGER_SHADOWING, "status": CHECK_PASS,
        "detail": f"M1.123 shadow comparison mechanism exercised; {rollback_count} rollback(s) on record",
    }


def _trust_score_rise_and_regression_check(session: Session, model_version: str) -> dict:
    history = get_regression_history(session, model_version)
    verdicts = {check.verdict for check in history}
    if not history:
        return {"check": CHECK_TRUST_SCORE_RISE_AND_REGRESSION, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no M1.67 regression checks recorded for this model version"}
    if VERDICT_HEALTHY in verdicts and VERDICT_REGRESSED in verdicts:
        return {"check": CHECK_TRUST_SCORE_RISE_AND_REGRESSION, "status": CHECK_PASS, "detail": "both HEALTHY and REGRESSED verdicts observed across regression check history"}
    return {
        "check": CHECK_TRUST_SCORE_RISE_AND_REGRESSION, "status": CHECK_INSUFFICIENT_EVIDENCE,
        "detail": f"only {sorted(verdicts)} observed so far -- both rise and regression cases not yet demonstrated",
    }


def _positive_only_and_abstention_check(session: Session) -> dict:
    has_abstention_report = session.scalar(select(SegmentAbstentionQualityReport.id).limit(1))
    if has_abstention_report is None:
        return {"check": CHECK_POSITIVE_ONLY_AND_ABSTENTION, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no M1.130 segment abstention quality report computed yet"}
    return {"check": CHECK_POSITIVE_ONLY_AND_ABSTENTION, "status": CHECK_PASS, "detail": "M1.130 segment abstention quality reporting present"}


def _immutable_history_and_replay_check(session: Session) -> dict:
    has_snapshot = session.scalar(select(DailyPredictionSnapshot.id).limit(1))
    has_replay = session.scalar(select(ReplayRun.id).limit(1))
    missing = [name for name, present in (("M1.78 daily prediction snapshots", has_snapshot), ("M1.115 replay runs", has_replay)) if present is None]
    if missing:
        return {"check": CHECK_IMMUTABLE_HISTORY_AND_REPLAY, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": f"missing: {missing}"}
    return {"check": CHECK_IMMUTABLE_HISTORY_AND_REPLAY, "status": CHECK_PASS, "detail": "M1.78 daily snapshots and M1.115 replay runs both present"}


def _portfolio_and_cross_sectional_ranking_check(session: Session) -> dict:
    has_cross_sectional = session.scalar(select(RankingEffectivenessReport.id).limit(1))
    has_portfolio = session.scalar(select(PortfolioSelectionEffectivenessReport.id).limit(1))
    missing = [name for name, present in (("M1.99 cross-sectional ranking effectiveness", has_cross_sectional), ("M1.124 portfolio selection effectiveness", has_portfolio)) if present is None]
    if missing:
        return {"check": CHECK_PORTFOLIO_AND_CROSS_SECTIONAL_RANKING, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": f"missing: {missing}"}
    return {"check": CHECK_PORTFOLIO_AND_CROSS_SECTIONAL_RANKING, "status": CHECK_PASS, "detail": "M1.99 and M1.124 ranking-effectiveness reporting both present"}


def _model_provider_cost_vs_value_check(session: Session) -> dict:
    has_tradeoff_report = session.scalar(select(CostQualityTradeoffReport.id).limit(1))
    if has_tradeoff_report is None:
        return {"check": CHECK_MODEL_PROVIDER_COST_VS_VALUE, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no M1.93 cost/quality tradeoff report computed yet"}
    return {"check": CHECK_MODEL_PROVIDER_COST_VS_VALUE, "status": CHECK_PASS, "detail": "M1.93 cost/quality tradeoff reporting present"}


def compile_end_to_end_validation_report(session: Session, *, model_version: str, computed_at: datetime) -> EndToEndValidationGateReport:
    """Always computes and persists a fresh, independent report row.
    `READY_FOR_PRODUCTION_V2` requires every check to be an explicit
    `CHECK_PASS` -- mirrors M1.117's own posture exactly."""
    checks = [
        _release_readiness_v1_check(session, model_version, computed_at),
        _horizon_coverage_check(session),
        _purged_embargoed_validation_check(session, model_version),
        _execution_cost_assumptions_check(session),
        _target_stop_horizon_closure_check(session),
        _event_driven_revision_and_freshness_check(session),
        _provider_provenance_check(session),
        _champion_challenger_shadowing_check(session),
        _trust_score_rise_and_regression_check(session, model_version),
        _positive_only_and_abstention_check(session),
        _immutable_history_and_replay_check(session),
        _portfolio_and_cross_sectional_ranking_check(session),
        _model_provider_cost_vs_value_check(session),
    ]

    blocking_issues = [c["check"] for c in checks if c["status"] != CHECK_PASS]
    overall_verdict = OVERALL_READY_V2 if not blocking_issues else OVERALL_NOT_READY

    report = EndToEndValidationGateReport(
        model_version=model_version,
        check_results=checks,
        blocking_issues=blocking_issues,
        overall_verdict=overall_verdict,
        computed_at=computed_at,
        gate_rule_version=GATE_V2_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_validation_gate_report_history(session: Session, model_version: str) -> tuple[EndToEndValidationGateReport, ...]:
    return tuple(
        session.scalars(
            select(EndToEndValidationGateReport)
            .where(EndToEndValidationGateReport.model_version == model_version)
            .order_by(EndToEndValidationGateReport.id.asc())
        ).all()
    )
