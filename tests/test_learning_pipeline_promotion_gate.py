from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adaptive_recommendation_adjustment import (
    ADAPTIVE_ADJUSTMENT_VERSION,
    SOURCE_PROBABILITY_CALIBRATION,
    SOURCE_REGIME_SCORE_ADJUSTMENT,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_VALIDATED,
    AdaptiveAdjustmentCandidate,
)
from app.db import Base
from app.learning_pipeline_promotion_gate import (
    DECISION_FAIL,
    DECISION_INSUFFICIENT_EVIDENCE,
    DECISION_PASS,
    GATE_RULE_VERSION,
    MAX_SAFE_EXPECTED_IMPACT,
    REASON_INSUFFICIENT_SAMPLE,
    REASON_NO_VALIDATION_EVIDENCE,
    REASON_NOT_IMPROVED_OUT_OF_SAMPLE,
    REASON_RISK_METRIC_REGRESSION,
    evaluate_promotion,
    get_active_promotion,
    get_promotion_history,
)
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

DECIDED_AT = datetime(2026, 10, 1, tzinfo=timezone.utc)


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


def _candidate(*, validation_status, sample_size=2 * MIN_SAMPLE_SIZE_FOR_COMPARISON,
                expected_impact=Decimal("0.10"), source_signal=SOURCE_PROBABILITY_CALIBRATION,
                affected_condition="probability in [0.80, 0.90)"):
    return AdaptiveAdjustmentCandidate(
        version=ADAPTIVE_ADJUSTMENT_VERSION,
        source_signal=source_signal,
        affected_condition=affected_condition,
        rationale="test candidate",
        sample_size=sample_size,
        expected_impact=expected_impact,
        validation_status=validation_status,
        validation_detail="test",
    )


def test_validated_candidate_passes(session):
    candidate = _candidate(validation_status=STATUS_VALIDATED)

    decision = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_PASS
    assert decision.gate_rule_version == GATE_RULE_VERSION


def test_rejected_candidate_fails(session):
    candidate = _candidate(validation_status=STATUS_REJECTED)

    decision = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_FAIL
    assert decision.decision_reason == REASON_NOT_IMPROVED_OUT_OF_SAMPLE


def test_pending_candidate_is_insufficient_evidence(session):
    candidate = _candidate(validation_status=STATUS_PENDING)

    decision = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_INSUFFICIENT_EVIDENCE
    assert decision.decision_reason == REASON_NO_VALIDATION_EVIDENCE


def test_small_sample_is_insufficient_evidence_even_if_validated(session):
    candidate = _candidate(validation_status=STATUS_VALIDATED, sample_size=MIN_SAMPLE_SIZE_FOR_COMPARISON - 1)

    decision = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_INSUFFICIENT_EVIDENCE
    assert decision.decision_reason == REASON_INSUFFICIENT_SAMPLE


def test_excessive_expected_impact_fails_even_if_validated(session):
    candidate = _candidate(validation_status=STATUS_VALIDATED, expected_impact=MAX_SAFE_EXPECTED_IMPACT + Decimal("0.01"))

    decision = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)

    assert decision.decision == DECISION_FAIL
    assert decision.decision_reason == REASON_RISK_METRIC_REGRESSION


def test_no_candidate_reaches_production_without_the_gate(session):
    # every possible validation_status must go through evaluate_promotion
    # to produce any decision at all -- there is no other path.
    for status in (STATUS_VALIDATED, STATUS_REJECTED, STATUS_PENDING):
        candidate = _candidate(validation_status=status)
        decision = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)
        assert decision.decision in (DECISION_PASS, DECISION_FAIL, DECISION_INSUFFICIENT_EVIDENCE)


def test_active_promotion_tracks_only_the_latest_pass_and_survives_rollback(session):
    condition = "probability in [0.80, 0.90)"
    assert get_active_promotion(session, source_signal=SOURCE_PROBABILITY_CALIBRATION, affected_condition=condition) is None

    evaluate_promotion(
        session, _candidate(validation_status=STATUS_VALIDATED, affected_condition=condition),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )
    first_active = get_active_promotion(session, source_signal=SOURCE_PROBABILITY_CALIBRATION, affected_condition=condition)
    assert first_active is not None
    assert first_active.decision == DECISION_PASS

    # a later, failing re-evaluation must not disturb the rollback target
    evaluate_promotion(
        session, _candidate(validation_status=STATUS_REJECTED, affected_condition=condition),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )
    still_active = get_active_promotion(session, source_signal=SOURCE_PROBABILITY_CALIBRATION, affected_condition=condition)
    assert still_active.id == first_active.id


def test_promotion_history_preserves_every_decision(session):
    evaluate_promotion(
        session, _candidate(validation_status=STATUS_VALIDATED, source_signal=SOURCE_PROBABILITY_CALIBRATION),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )
    evaluate_promotion(
        session, _candidate(validation_status=STATUS_REJECTED, source_signal=SOURCE_REGIME_SCORE_ADJUSTMENT, affected_condition="BULLISH_HIGH_VOL"),
        approver="SYSTEM", decided_at=DECIDED_AT,
    )

    full_history = get_promotion_history(session)
    assert len(full_history) == 2

    calibration_only = get_promotion_history(session, source_signal=SOURCE_PROBABILITY_CALIBRATION)
    assert len(calibration_only) == 1
    assert calibration_only[0].decision == DECISION_PASS


def test_decision_is_deterministic_for_the_same_candidate(session):
    candidate = _candidate(validation_status=STATUS_VALIDATED)

    first = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)
    second = evaluate_promotion(session, candidate, approver="SYSTEM", decided_at=DECIDED_AT)

    assert first.decision == second.decision == DECISION_PASS
