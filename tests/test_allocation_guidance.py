from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.allocation_guidance import (
    DEFAULT_MAX_POSITION_PERCENTAGE,
    GUIDANCE_STATUS_BLOCKED,
    GUIDANCE_STATUS_CONSTRAINED,
    GUIDANCE_STATUS_GUIDED,
    GUIDANCE_STATUS_INSUFFICIENT_RISK_INFORMATION,
    REASON_ALREADY_EXPOSED,
    REASON_CAPPED_BY_USER_LIMIT,
    REASON_SECTOR_CONCENTRATION,
    InvalidAllocationLimitError,
    generate_allocation_guidance,
    get_current_allocation_limit,
    set_allocation_limit,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.portfolio_awareness import ACTION_HELD, SECTOR_CONCENTRATION_THRESHOLD, record_holding
from app.position_risk_assessment import assess_position_risk
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2026, 11, 1, tzinfo=timezone.utc)


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


_scan_counter = iter(range(100000))


def _make_prediction(session, symbol="AAA", *, sector="Energy", confidence=Decimal("0.80"),
                      target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), atr_percent=Decimal("0.035")):
    # each call gets its own scan so building several predictions in one
    # test never collides on scan_date+universe_version.
    from datetime import timedelta
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=confidence, sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=target_return, stop_return=stop_return,
    )
    return session.get(Prediction, generation.prediction_id), stock


def _risk_assessment(session, prediction):
    publication = publish_recommendation(session, prediction, published_at=AS_OF)
    return assess_position_risk(session, prediction, publication, assessed_at=AS_OF)


def test_missing_risk_assessment_prevents_guidance(session):
    prediction, _stock = _make_prediction(session)

    guidance = generate_allocation_guidance(session, user_id="user-1", prediction=prediction, risk_assessment=None, effective_at=AS_OF)

    assert guidance.guidance_status == GUIDANCE_STATUS_INSUFFICIENT_RISK_INFORMATION
    assert guidance.suggested_allocation_percentage is None


def test_horizon_inconsistent_risk_prevents_guidance(session):
    # downside 0.01 / atr 0.035 = 0.286, below MIN_ATR_MULTIPLE_STOP -> inconsistent
    prediction, _stock = _make_prediction(session, stop_return=Decimal("-0.01"))
    risk = _risk_assessment(session, prediction)
    assert risk.horizon_consistent is False

    guidance = generate_allocation_guidance(session, user_id="user-1", prediction=prediction, risk_assessment=risk, effective_at=AS_OF)

    assert guidance.guidance_status == GUIDANCE_STATUS_INSUFFICIENT_RISK_INFORMATION
    assert guidance.suggested_allocation_percentage is None


def test_normal_case_produces_guided_allocation_within_default_limit(session):
    prediction, _stock = _make_prediction(session, confidence=Decimal("0.80"))
    risk = _risk_assessment(session, prediction)
    assert risk.horizon_consistent is True

    guidance = generate_allocation_guidance(session, user_id="user-1", prediction=prediction, risk_assessment=risk, effective_at=AS_OF)

    assert guidance.guidance_status == GUIDANCE_STATUS_GUIDED
    assert guidance.suggested_allocation_percentage is not None
    assert Decimal("0") < guidance.suggested_allocation_percentage <= DEFAULT_MAX_POSITION_PERCENTAGE


def test_tighter_user_limit_caps_the_suggestion(session):
    prediction, _stock = _make_prediction(session, confidence=Decimal("0.95"))
    risk = _risk_assessment(session, prediction)
    set_allocation_limit(session, user_id="user-2", effective_at=AS_OF, max_position_percentage=Decimal("0.01"))

    guidance = generate_allocation_guidance(session, user_id="user-2", prediction=prediction, risk_assessment=risk, effective_at=AS_OF)

    assert guidance.suggested_allocation_percentage == Decimal("0.01")
    assert REASON_CAPPED_BY_USER_LIMIT in guidance.reasons
    assert guidance.guidance_status == GUIDANCE_STATUS_CONSTRAINED


def test_already_held_stock_is_blocked(session):
    prediction, stock = _make_prediction(session)
    risk = _risk_assessment(session, prediction)
    record_holding(session, user_id="user-3", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)

    guidance = generate_allocation_guidance(session, user_id="user-3", prediction=prediction, risk_assessment=risk, effective_at=AS_OF)

    assert guidance.guidance_status == GUIDANCE_STATUS_BLOCKED
    assert guidance.suggested_allocation_percentage == Decimal("0")
    assert REASON_ALREADY_EXPOSED in guidance.reasons


def test_sector_concentration_constrains_but_does_not_block(session):
    prediction, stock = _make_prediction(session, sector="Energy")
    risk = _risk_assessment(session, prediction)
    for i in range(SECTOR_CONCENTRATION_THRESHOLD - 1):
        held_prediction, held_stock = _make_prediction(session, symbol=f"H{i}", sector="Energy")
        record_holding(session, user_id="user-4", stock_id=held_stock.id, action=ACTION_HELD, recorded_at=AS_OF)

    guidance = generate_allocation_guidance(session, user_id="user-4", prediction=prediction, risk_assessment=risk, effective_at=AS_OF)

    assert guidance.guidance_status == GUIDANCE_STATUS_CONSTRAINED
    assert REASON_SECTOR_CONCENTRATION in guidance.reasons
    assert guidance.suggested_allocation_percentage > Decimal("0")


def test_invalid_allocation_limit_is_rejected(session):
    with pytest.raises(InvalidAllocationLimitError):
        set_allocation_limit(session, user_id="user-5", effective_at=AS_OF, max_position_percentage=Decimal("1.5"))
    with pytest.raises(InvalidAllocationLimitError):
        set_allocation_limit(session, user_id="user-5", effective_at=AS_OF, max_sector_percentage=Decimal("0"))


def test_new_user_gets_a_default_limit_idempotently(session):
    first = get_current_allocation_limit(session, "user-6", effective_at=AS_OF)
    second = get_current_allocation_limit(session, "user-6", effective_at=AS_OF)

    assert first.id == second.id
    assert first.max_position_percentage == DEFAULT_MAX_POSITION_PERCENTAGE


def test_guidance_is_reproducible_and_never_writes_to_prediction(session):
    prediction, _stock = _make_prediction(session)
    risk = _risk_assessment(session, prediction)
    before = (prediction.confidence, prediction.opportunity_score)

    first = generate_allocation_guidance(session, user_id="user-7", prediction=prediction, risk_assessment=risk, effective_at=AS_OF)
    second = generate_allocation_guidance(session, user_id="user-7", prediction=prediction, risk_assessment=risk, effective_at=AS_OF)

    after = (prediction.confidence, prediction.opportunity_score)
    assert first == second
    assert before == after
