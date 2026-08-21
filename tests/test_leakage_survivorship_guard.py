from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import evaluate_evidence_quality
from app.evidence_snapshot import (
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_SNAPSHOT_VERSION,
    STATUS_AVAILABLE,
    capture_evidence_snapshot,
)
from app.leakage_survivorship_guard import (
    BIAS_GUARD_VERSION,
    BiasGuardCheckImmutableError,
    BiasGuardOverrideImmutableError,
    InvalidBiasGuardWorkflowError,
    InvalidOverrideError,
    OverrideAlreadyRecordedError,
    REASON_LEAKAGE_DETECTED,
    REASON_POST_DECISION_REVISION,
    REASON_UNVERIFIED_UNIVERSE_MEMBERSHIP,
    VERDICT_BLOCKED,
    VERDICT_PASS,
    WORKFLOW_EVALUATION,
    WORKFLOW_TRAINING,
    get_bias_guard_history,
    get_override_for_check,
    is_effectively_passed,
    record_bias_guard_override,
    run_bias_guard_check,
)
from app.models import DailyCandidateScan, MarketPrice, Prediction, RecommendationEvidenceItem, ScanCandidate, Stock
from app.recommendation_revalidation import revalidate_recommendation
from app.recommendation_tracking import record_daily_observations
from app.recommendations import record_recommendation
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2027, 5, 1, tzinfo=timezone.utc)
_scan_counter = iter(range(100000))


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


def make_stock(session, symbol="AAA"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def make_prediction_via_real_pipeline(session, symbol="AAA", *, atr_percent=Decimal("0.035")):
    """A genuine, platform-produced prediction: discovered, routed through
    consensus/qualification, linked back to its `ScanCandidate` via a
    `RecommendationGeneration` row -- verified universe membership."""
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = make_stock(session, symbol)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, stock


def make_prediction_without_provenance(session, symbol="ZZZ"):
    """A prediction inserted directly, never having gone through the real
    discovery/consensus/qualification pipeline -- no `RecommendationGeneration`
    links to it at all. This is the shape a hand-picked or backfilled row
    injected straight into a training set would have."""
    stock = make_stock(session, symbol)
    prediction = record_recommendation(
        session, stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version="m1", feature_version="f1",
        consensus_contract_version="PCC-001", horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001", opportunity_score=Decimal("70.00"),
    )
    return prediction, stock


def test_clean_prediction_passes(session):
    prediction, _ = make_prediction_via_real_pipeline(session)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    assert check.verdict == VERDICT_PASS
    assert check.reason_codes == []
    assert check.guard_rule_version == BIAS_GUARD_VERSION


def test_unknown_workflow_type_is_rejected(session):
    prediction, _ = make_prediction_via_real_pipeline(session)
    with pytest.raises(InvalidBiasGuardWorkflowError):
        run_bias_guard_check(session, prediction, workflow_type="NOT_A_REAL_WORKFLOW", checked_at=AS_OF)


def test_leakage_is_detected_and_blocking(session):
    prediction, _ = make_prediction_via_real_pipeline(session, "DDD")
    # simulate a known adversarial leakage scenario: a category already
    # "captured" with an evidence_timestamp after the decision's own as_of.
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category=EVIDENCE_CATEGORY_NEWS, status=STATUS_AVAILABLE,
        source="test-leak", reference="future news", evidence_timestamp=AS_OF + timedelta(days=10),
        is_stale=False, snapshot_rule_version=EVIDENCE_SNAPSHOT_VERSION, captured_at=AS_OF,
    ))
    session.commit()
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    assert check.verdict == VERDICT_BLOCKED
    assert REASON_LEAKAGE_DETECTED in check.reason_codes
    assert check.evidence["leaked_categories"] == [EVIDENCE_CATEGORY_NEWS]


def test_post_decision_revision_is_detected_and_blocking(session):
    prediction, stock = make_prediction_via_real_pipeline(session, "BBB", atr_percent=Decimal("0.001"))  # horizon=7
    publish_recommendation(session, prediction, published_at=AS_OF)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("101"), high=Decimal("102"), low=Decimal("100"), close=Decimal("101"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)
    much_later = AS_OF + timedelta(days=5)
    revalidate_recommendation(session, prediction, checked_at=much_later)  # stale market data -> WITHDRAWN

    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_EVALUATION, checked_at=much_later)

    assert check.verdict == VERDICT_BLOCKED
    assert REASON_POST_DECISION_REVISION in check.reason_codes
    assert check.evidence["revalidation_outcomes"] == ["WITHDRAWN"]


def test_unverified_universe_membership_is_detected_and_blocking(session):
    prediction, _ = make_prediction_without_provenance(session)

    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    assert check.verdict == VERDICT_BLOCKED
    assert REASON_UNVERIFIED_UNIVERSE_MEMBERSHIP in check.reason_codes


def test_check_is_idempotent(session):
    prediction, _ = make_prediction_via_real_pipeline(session)

    first = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)
    second = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    assert first.id == second.id


def test_check_fields_are_immutable(session):
    prediction, _ = make_prediction_without_provenance(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    check.verdict = VERDICT_PASS
    with pytest.raises(BiasGuardCheckImmutableError):
        session.flush()
    session.rollback()


def test_override_requires_a_blocked_check(session):
    prediction, _ = make_prediction_via_real_pipeline(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    with pytest.raises(InvalidOverrideError):
        record_bias_guard_override(session, check, justification="looks fine", authorized_by="analyst-1", recorded_at=AS_OF)


def test_override_requires_a_real_justification(session):
    prediction, _ = make_prediction_without_provenance(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    with pytest.raises(InvalidOverrideError):
        record_bias_guard_override(session, check, justification="   ", authorized_by="analyst-1", recorded_at=AS_OF)


def test_override_never_rewrites_the_original_verdict(session):
    prediction, _ = make_prediction_without_provenance(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    override = record_bias_guard_override(
        session, check, justification="manually verified against the exchange's own historical listing records",
        authorized_by="analyst-1", recorded_at=AS_OF,
    )

    assert check.verdict == VERDICT_BLOCKED  # never rewritten
    assert override.check_id == check.id
    assert get_override_for_check(session, check.id).id == override.id


def test_cannot_override_the_same_check_twice(session):
    prediction, _ = make_prediction_without_provenance(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)
    record_bias_guard_override(session, check, justification="first justification", authorized_by="analyst-1", recorded_at=AS_OF)

    with pytest.raises(OverrideAlreadyRecordedError):
        record_bias_guard_override(session, check, justification="second attempt", authorized_by="analyst-2", recorded_at=AS_OF)


def test_override_fields_are_immutable(session):
    prediction, _ = make_prediction_without_provenance(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)
    override = record_bias_guard_override(session, check, justification="justified", authorized_by="analyst-1", recorded_at=AS_OF)

    override.justification = "changed my mind"
    with pytest.raises(BiasGuardOverrideImmutableError):
        session.flush()
    session.rollback()


def test_is_effectively_passed_without_override(session):
    prediction, _ = make_prediction_without_provenance(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    assert is_effectively_passed(check, None) is False


def test_is_effectively_passed_with_a_real_override(session):
    prediction, _ = make_prediction_without_provenance(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)
    override = record_bias_guard_override(session, check, justification="justified", authorized_by="analyst-1", recorded_at=AS_OF)

    assert is_effectively_passed(check, override) is True


def test_is_effectively_passed_true_for_a_clean_pass_with_no_override(session):
    prediction, _ = make_prediction_via_real_pipeline(session)
    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    assert is_effectively_passed(check, None) is True


def test_history_returns_every_check_for_a_prediction(session):
    prediction, _ = make_prediction_via_real_pipeline(session)
    run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)
    run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_EVALUATION, checked_at=AS_OF)

    history = get_bias_guard_history(session, prediction.id)

    assert len(history) == 2
    assert {c.workflow_type for c in history} == {WORKFLOW_TRAINING, WORKFLOW_EVALUATION}


def test_delisted_stocks_prediction_still_passes_the_guard(session):
    """Survivorship-bias non-regression: a since-delisted stock's clean
    prediction must not be penalized by this guard just for being inactive
    today."""
    from app.corporate_actions import ACTION_DELISTING, record_corporate_action

    prediction, stock = make_prediction_via_real_pipeline(session)
    record_corporate_action(
        session, stock=stock, action_type=ACTION_DELISTING, effective_date=AS_OF.date() + timedelta(days=30),
        source="test", recorded_at=AS_OF,
    )
    assert stock.is_active is False

    check = run_bias_guard_check(session, prediction, workflow_type=WORKFLOW_TRAINING, checked_at=AS_OF)

    assert REASON_UNVERIFIED_UNIVERSE_MEMBERSHIP not in check.reason_codes
