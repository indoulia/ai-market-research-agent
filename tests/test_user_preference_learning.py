from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Prediction, RecommendationFeedback, Stock, UserPreference, UserPreferenceSuggestion
from app.recommendation_feedback import CATEGORY_OVERALL, REASON_AGREE, REASON_TOO_HIGH, submit_feedback
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON
from app.user_preference_learning import (
    PREFERENCE_LEARNING_VERSION,
    UserPreferenceSuggestionImmutableError,
    generate_preference_suggestion,
    get_suggestions_for_user,
    observe_horizon_band_feedback,
)
from app.user_preferences import HORIZON_BAND_LONG, HORIZON_BAND_SHORT, set_user_preference

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


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


def _make_prediction(session, symbol, horizon_days):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        horizon_days=horizon_days, target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.7"), confidence=Decimal("0.8"), model_version="test-model-1",
        feature_version="FV-001", consensus_contract_version="CC-001", horizon_selection_version="HS-001",
        scoring_contract_version="SC-001", opportunity_score=Decimal("50.00"),
    )
    session.add(prediction)
    session.commit()
    session.refresh(prediction)
    return prediction


def _seed_band_feedback(session, user_id, *, prefix, horizon_days, total, agree_count):
    for i in range(total):
        prediction = _make_prediction(session, f"{prefix}{i}", horizon_days)
        reason = REASON_AGREE if i < agree_count else REASON_TOO_HIGH
        submit_feedback(session, prediction, user_id=user_id, category=CATEGORY_OVERALL, reason_code=reason, submitted_at=AS_OF)


def test_no_feedback_produces_no_suggestion(session):
    assert generate_preference_suggestion(session, "user-1", as_of=AS_OF) is None
    signals = observe_horizon_band_feedback(session, "user-1")
    assert len(signals) == 3
    assert all(s.total_feedback_count == 0 and s.agree_rate is None for s in signals)


def test_insufficient_sample_produces_no_suggestion(session):
    _seed_band_feedback(session, "user-2", prefix="A", horizon_days=35, total=MIN_SAMPLE_SIZE_FOR_COMPARISON - 1, agree_count=MIN_SAMPLE_SIZE_FOR_COMPARISON - 1)
    assert generate_preference_suggestion(session, "user-2", as_of=AS_OF) is None


def test_stable_preference_signal_produces_suggestion(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON + 5
    _seed_band_feedback(session, "user-3", prefix="L", horizon_days=35, total=total, agree_count=total)
    _seed_band_feedback(session, "user-3", prefix="S", horizon_days=5, total=total, agree_count=0)

    suggestion = generate_preference_suggestion(session, "user-3", as_of=AS_OF)

    assert suggestion is not None
    assert suggestion.suggested_horizon_band == HORIZON_BAND_LONG
    assert suggestion.current_horizon_band is None
    assert suggestion.evidence_sample_count == total
    assert suggestion.evidence_agree_rate == Decimal("1")
    assert suggestion.learning_rule_version == PREFERENCE_LEARNING_VERSION
    assert HORIZON_BAND_LONG in suggestion.rationale


def test_current_band_already_best_produces_no_suggestion(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON + 5
    set_user_preference(session, user_id="user-4", effective_at=AS_OF, horizon_band=HORIZON_BAND_SHORT)
    _seed_band_feedback(session, "user-4", prefix="S", horizon_days=5, total=total, agree_count=total)
    _seed_band_feedback(session, "user-4", prefix="M", horizon_days=15, total=total, agree_count=0)

    assert generate_preference_suggestion(session, "user-4", as_of=AS_OF) is None


def test_small_margin_does_not_trigger_suggestion(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON + 5
    set_user_preference(session, user_id="user-5", effective_at=AS_OF, horizon_band=HORIZON_BAND_SHORT)
    _seed_band_feedback(session, "user-5", prefix="S", horizon_days=5, total=total, agree_count=int(total * 0.6))
    _seed_band_feedback(session, "user-5", prefix="M", horizon_days=15, total=total, agree_count=int(total * 0.76))

    assert generate_preference_suggestion(session, "user-5", as_of=AS_OF) is None


def test_suggestion_is_immutable(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON + 5
    _seed_band_feedback(session, "user-6", prefix="L", horizon_days=35, total=total, agree_count=total)
    suggestion = generate_preference_suggestion(session, "user-6", as_of=AS_OF)

    suggestion.rationale = "edited after the fact"
    with pytest.raises(UserPreferenceSuggestionImmutableError):
        session.commit()
    session.rollback()


def test_never_writes_to_predictions_feedback_or_preferences(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON + 5
    set_user_preference(session, user_id="user-7", effective_at=AS_OF, horizon_band=HORIZON_BAND_SHORT)
    _seed_band_feedback(session, "user-7", prefix="L", horizon_days=35, total=total, agree_count=total)

    before_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    before_feedback_count = session.query(RecommendationFeedback).count()
    before_preference_count = session.query(UserPreference).count()

    suggestion = generate_preference_suggestion(session, "user-7", as_of=AS_OF)
    assert suggestion is not None

    after_predictions = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    after_feedback_count = session.query(RecommendationFeedback).count()
    after_preference_count = session.query(UserPreference).count()

    assert before_predictions == after_predictions
    assert before_feedback_count == after_feedback_count
    assert before_preference_count == after_preference_count


def test_get_suggestions_for_user_returns_stored_suggestions(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON + 5
    _seed_band_feedback(session, "user-8", prefix="L", horizon_days=35, total=total, agree_count=total)
    created = generate_preference_suggestion(session, "user-8", as_of=AS_OF)

    stored = get_suggestions_for_user(session, "user-8")
    assert len(stored) == 1
    assert stored[0].id == created.id
    assert get_suggestions_for_user(session, "someone-else") == ()
