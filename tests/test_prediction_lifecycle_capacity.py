from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    DailyCandidateScan,
    Prediction,
    PredictionOutcome,
    PositiveOpportunityRanking,
    RecommendationGeneration,
    RecommendationLifecycle,
    RecommendationRevalidationOutcome,
    RecommendationRevision,
    ScanCandidate,
    Stock,
)
from app.prediction_lifecycle_capacity import (
    LIFECYCLE_CAPACITY_VERSION,
    REASON_CAPACITY_EXCEEDED,
    REASON_DUPLICATE_ACTIVE_OPPORTUNITY,
    REASON_SELECTED,
    STATE_ACTIVE,
    STATE_CREATED,
    STATE_EVALUATED,
    STATE_EXPIRED,
    STATE_INVALIDATED,
    STATE_REVISED,
    STATE_SL_HIT,
    STATE_TARGET_HIT,
    apply_capacity_control,
    classify_prediction_lifecycle_state,
    get_capacity_decision_history,
    get_lifecycle_history,
    snapshot_prediction_lifecycle,
)

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
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


def _make_prediction(session, *, stock=None, horizon_days=1, symbol=None):
    n = next(_counter)
    if stock is None:
        stock = Stock(symbol=symbol or f"S{n}", exchange="NSE", is_active=True)
        session.add(stock)
        session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=horizon_days,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.commit()
    return prediction, stock


def _link_generation(session, prediction, *, scan=None):
    if scan is None:
        n = next(_counter)
        scan = DailyCandidateScan(scan_date=date(2027, 1, 1) + timedelta(days=n), universe_version="DCS-001", eligible_count=1, excluded_count=0)
        session.add(scan)
        session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=prediction.stock_id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.1"), atr_percent=Decimal("0.02"),
        data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    generation = RecommendationGeneration(
        scan_candidate_id=candidate.id, outcome="QUALIFIED", consensus_contract_version="CC-001",
        failed_criteria=None, prediction_id=prediction.id,
    )
    session.add(generation)
    session.commit()
    return generation, scan, candidate


def test_created_state_with_no_evidence(session):
    prediction, _stock = _make_prediction(session)

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_CREATED


def test_active_state_when_tracked_by_lifecycle(session):
    prediction, _stock = _make_prediction(session)
    generation, _scan, _candidate = _link_generation(session, prediction)
    session.add(RecommendationLifecycle(
        recommendation_generation_id=generation.id, state="ISSUED", lifecycle_rule_version="RLS-001",
    ))
    session.commit()

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_ACTIVE


def test_target_hit_state(session):
    prediction, _stock = _make_prediction(session)
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
        closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.05"), prediction_error=Decimal("0.01"), target_hit=True, stop_hit=False, outcome="SUCCESS",
    ))
    session.commit()

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_TARGET_HIT


def test_sl_hit_state(session):
    prediction, _stock = _make_prediction(session)
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("101"), lowest_price=Decimal("96"),
        closing_price=Decimal("97"), maximum_return=Decimal("0.01"), maximum_drawdown=Decimal("-0.03"),
        actual_return=Decimal("-0.03"), prediction_error=Decimal("0.01"), target_hit=False, stop_hit=True, outcome="FAILURE",
    ))
    session.commit()

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_SL_HIT


def test_evaluated_state_without_target_or_stop(session):
    prediction, _stock = _make_prediction(session)
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("102"), lowest_price=Decimal("99"),
        closing_price=Decimal("101"), maximum_return=Decimal("0.02"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.01"), prediction_error=Decimal("0.01"), target_hit=False, stop_hit=False, outcome="SUCCESS",
    ))
    session.commit()

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_EVALUATED


def test_expired_state_from_revalidation(session):
    prediction, _stock = _make_prediction(session)
    session.add(RecommendationRevalidationOutcome(
        prediction_id=prediction.id, outcome="EXPIRED", reason="horizon elapsed", elapsed_days=6,
        current_return=None, evidence_timestamp=AS_OF, checked_at=AS_OF, revalidation_engine_version="RVL-001",
    ))
    session.commit()

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_EXPIRED


def test_invalidated_state_from_revalidation(session):
    prediction, _stock = _make_prediction(session)
    session.add(RecommendationRevalidationOutcome(
        prediction_id=prediction.id, outcome="WITHDRAWN", reason="stale market data", elapsed_days=1,
        current_return=None, evidence_timestamp=AS_OF, checked_at=AS_OF, revalidation_engine_version="RVL-001",
    ))
    session.commit()

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_INVALIDATED


def test_revised_state(session):
    prediction, _stock = _make_prediction(session)
    previous, _ = _make_prediction(session)
    revised, _ = _make_prediction(session)
    session.add(RecommendationRevision(
        original_prediction_id=prediction.id, previous_prediction_id=previous.id, revised_prediction_id=revised.id,
        version_number=2, revision_reason="MATERIAL_EVIDENCE_CHANGE", revised_at=AS_OF, revision_rule_version="RRV-001",
    ))
    session.commit()

    state, _reason = classify_prediction_lifecycle_state(session, prediction)

    assert state == STATE_REVISED


def test_snapshot_records_previous_state_transition(session):
    prediction, _stock = _make_prediction(session)

    first = snapshot_prediction_lifecycle(session, prediction, evaluated_at=AS_OF)
    assert first.state == STATE_CREATED
    assert first.previous_state is None

    generation, _scan, _candidate = _link_generation(session, prediction)
    session.add(RecommendationLifecycle(recommendation_generation_id=generation.id, state="ISSUED", lifecycle_rule_version="RLS-001"))
    session.commit()

    second = snapshot_prediction_lifecycle(session, prediction, evaluated_at=AS_OF + timedelta(hours=1))
    assert second.state == STATE_ACTIVE
    assert second.previous_state == STATE_CREATED
    assert len(get_lifecycle_history(session, prediction.id)) == 2
    assert second.lifecycle_rule_version == LIFECYCLE_CAPACITY_VERSION


def test_snapshot_idempotent(session):
    prediction, _stock = _make_prediction(session)

    first = snapshot_prediction_lifecycle(session, prediction, evaluated_at=AS_OF)
    second = snapshot_prediction_lifecycle(session, prediction, evaluated_at=AS_OF)

    assert first.id == second.id


def _make_ranked_qualified_prediction(session, scan, *, rank_position, stock=None, horizon_days=1):
    prediction, stock = _make_prediction(session, stock=stock, horizon_days=horizon_days)
    _link_generation(session, prediction, scan=scan)
    session.add(PositiveOpportunityRanking(
        prediction_id=prediction.id, stock_id=stock.id, horizon_days=horizon_days, composite_score=Decimal("0.8"),
        expected_return_component=Decimal("0.05"), probability_component=Decimal("0.7"), trust_component=Decimal("0.9"),
        reward_risk_component=None, evidence_quality_component=Decimal("1"), stability_component=None,
        rank_position=rank_position, included=True, exclusion_reason=None, evaluated_at=AS_OF, ranking_rule_version="OPR-001",
    ))
    session.commit()
    return prediction, stock


def test_capacity_control_selects_top_ranked_within_limit(session):
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1), universe_version="DCS-001", eligible_count=3, excluded_count=0)
    session.add(scan)
    session.flush()
    p1, _ = _make_ranked_qualified_prediction(session, scan, rank_position=1)
    p2, _ = _make_ranked_qualified_prediction(session, scan, rank_position=2)
    p3, _ = _make_ranked_qualified_prediction(session, scan, rank_position=3)

    decisions = apply_capacity_control(session, scan.id, capacity_limit=2, evaluated_at=AS_OF)

    by_prediction = {d.prediction_id: d for d in decisions}
    assert by_prediction[p1.id].included is True
    assert by_prediction[p2.id].included is True
    assert by_prediction[p3.id].included is False
    assert by_prediction[p3.id].exclusion_reason == REASON_CAPACITY_EXCEEDED
    assert by_prediction[p1.id].capacity_rule_version == LIFECYCLE_CAPACITY_VERSION


def test_capacity_control_excludes_duplicate_active_opportunity(session):
    stock = Stock(symbol="DUP", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    already_active, _ = _make_prediction(session, stock=stock, horizon_days=1)
    generation, _scan_a, _c = _link_generation(session, already_active)
    session.add(RecommendationLifecycle(recommendation_generation_id=generation.id, state="ISSUED", lifecycle_rule_version="RLS-001"))
    session.commit()

    scan = DailyCandidateScan(scan_date=date(2027, 2, 1), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    new_candidate, _ = _make_ranked_qualified_prediction(session, scan, rank_position=1, stock=stock, horizon_days=1)

    decisions = apply_capacity_control(session, scan.id, capacity_limit=10, evaluated_at=AS_OF)

    assert len(decisions) == 1
    assert decisions[0].prediction_id == new_candidate.id
    assert decisions[0].included is False
    assert decisions[0].exclusion_reason == REASON_DUPLICATE_ACTIVE_OPPORTUNITY


def test_capacity_control_idempotent(session):
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    prediction, _ = _make_ranked_qualified_prediction(session, scan, rank_position=1)

    first = apply_capacity_control(session, scan.id, capacity_limit=5, evaluated_at=AS_OF)
    second = apply_capacity_control(session, scan.id, capacity_limit=5, evaluated_at=AS_OF)

    assert [d.id for d in first] == [d.id for d in second]
    assert len(get_capacity_decision_history(session, prediction.id)) == 1
