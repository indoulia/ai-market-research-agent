from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.decision_trace import capture_decision_trace
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.investment_decision_journal import (
    DECISION_ACTED_ON,
    DECISION_DEFERRED,
    DECISION_DISMISSED,
    InvalidDecisionError,
    JOURNAL_RULE_VERSION,
    UserDecisionImmutableError,
    get_decision_history,
    get_journal_entry,
    get_journal_for_user,
    record_decision,
)
from app.models import DailyCandidateScan, MarketPrice, Prediction, PredictionOutcome, ScanCandidate, Stock, UserDecision
from app.outcome_measurement import OUTCOME_SUCCESS, measure_outcome
from app.outcomes import evaluate_recommendation
from app.recommendation_feedback import CATEGORY_OVERALL, REASON_AGREE, submit_feedback

AS_OF = datetime(2026, 1, 10, tzinfo=timezone.utc)
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


def _make_generation(session, symbol="X1", *, win=True):
    scan_date = date(2026, 1, 10) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
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
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=AS_OF)
    capture_decision_trace(session, generation, traced_at=AS_OF)
    return generation, prediction


def test_record_decision_rejects_invalid_decision(session):
    generation, _ = _make_generation(session)
    with pytest.raises(InvalidDecisionError):
        record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision="MAYBE", decided_at=AS_OF)


def test_full_lifecycle_is_inspectable(session):
    generation, prediction = _make_generation(session, win=True)
    submit_feedback(session, prediction, user_id="u1", category=CATEGORY_OVERALL, reason_code=REASON_AGREE, submitted_at=AS_OF)
    record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision=DECISION_ACTED_ON, decided_at=AS_OF, rationale="looked solid")

    entry = get_journal_entry(session, user_id="u1", recommendation_generation_id=generation.id)

    assert entry.version == JOURNAL_RULE_VERSION
    assert entry.recommendation_snapshot is not None
    assert entry.recommendation_snapshot.prediction_id == prediction.id
    assert len(entry.decisions) == 1
    assert entry.decisions[0].decision == DECISION_ACTED_ON
    assert len(entry.feedback) == 1
    assert entry.prediction_vs_actual is not None
    assert entry.prediction_vs_actual.target_return == Decimal("0.05")
    assert entry.prediction_vs_actual.actual_return == Decimal("0.05")
    assert entry.prediction_vs_actual.outcome == "SUCCESS"
    assert entry.prediction_vs_actual.outcome_classification == OUTCOME_SUCCESS


def test_decisions_and_system_outcomes_are_clearly_separated(session):
    generation, prediction = _make_generation(session, win=False)
    record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision=DECISION_DISMISSED, decided_at=AS_OF)

    entry = get_journal_entry(session, user_id="u1", recommendation_generation_id=generation.id)

    # the user dismissed it, but the objective outcome is tracked independently
    assert entry.decisions[0].decision == DECISION_DISMISSED
    assert entry.prediction_vs_actual.outcome == "FAILURE"
    assert not hasattr(entry.decisions[0], "outcome")


def test_changing_a_decision_preserves_full_history(session):
    generation, _ = _make_generation(session)
    record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision=DECISION_DEFERRED, decided_at=AS_OF)
    record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision=DECISION_ACTED_ON, decided_at=AS_OF + timedelta(days=1))

    history = get_decision_history(session, user_id="u1", recommendation_generation_id=generation.id)
    assert [d.decision for d in history] == [DECISION_DEFERRED, DECISION_ACTED_ON]


def test_decision_is_immutable(session):
    generation, _ = _make_generation(session)
    decision = record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision=DECISION_ACTED_ON, decided_at=AS_OF)

    decision.decision = DECISION_DISMISSED
    with pytest.raises(UserDecisionImmutableError):
        session.commit()
    session.rollback()


def test_journal_survives_recommendation_retirement(session):
    generation, prediction = _make_generation(session, win=True)
    record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision=DECISION_ACTED_ON, decided_at=AS_OF)

    assert prediction.status == "EVALUATED"  # already "retired" by evaluate_recommendation

    entry = get_journal_entry(session, user_id="u1", recommendation_generation_id=generation.id)
    assert entry.recommendation_snapshot is not None
    assert entry.prediction_vs_actual is not None
    assert len(entry.decisions) == 1


def test_get_journal_for_user_returns_every_decided_generation(session):
    gen1, _ = _make_generation(session, symbol="J1")
    gen2, _ = _make_generation(session, symbol="J2")
    record_decision(session, user_id="u2", recommendation_generation_id=gen1.id, decision=DECISION_ACTED_ON, decided_at=AS_OF)
    record_decision(session, user_id="u2", recommendation_generation_id=gen2.id, decision=DECISION_DISMISSED, decided_at=AS_OF)

    entries = get_journal_for_user(session, "u2")
    assert {e.recommendation_generation_id for e in entries} == {gen1.id, gen2.id}
    assert get_journal_for_user(session, "someone-else") == ()


def test_journal_never_writes_to_predictions_or_feedback(session):
    generation, prediction = _make_generation(session)
    submit_feedback(session, prediction, user_id="u1", category=CATEGORY_OVERALL, reason_code=REASON_AGREE, submitted_at=AS_OF)
    record_decision(session, user_id="u1", recommendation_generation_id=generation.id, decision=DECISION_ACTED_ON, decided_at=AS_OF)

    before_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    before_outcomes = {o.id: o.outcome for o in session.query(PredictionOutcome).all()}

    get_journal_entry(session, user_id="u1", recommendation_generation_id=generation.id)
    get_journal_for_user(session, "u1")

    after_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    after_outcomes = {o.id: o.outcome for o in session.query(PredictionOutcome).all()}
    assert before_predictions == after_predictions
    assert before_outcomes == after_outcomes
