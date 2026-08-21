from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.prediction_stability import (
    AGREEMENT_VERDICT_AGREE,
    AGREEMENT_VERDICT_DISAGREE,
    AGREEMENT_VERDICT_NO_DATA,
    MAX_STABLE_REVISIONS,
    STABILITY_ASSESSMENT_VERSION,
    STABILITY_VERDICT_STABLE,
    STABILITY_VERDICT_UNSTABLE,
    assess_prediction_stability,
    get_stability_history,
)
from app.recommendation_revision import (
    REASON_EVIDENCE_STALE,
    REASON_MANUAL_TRIGGER,
    REASON_MATERIAL_EVIDENCE_CHANGE,
    create_recommendation_revision,
)

AS_OF = datetime(2026, 9, 20, tzinfo=timezone.utc)


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


def _make_prediction(session, stock, *, as_of, confidence=Decimal("0.80"), predicted_probability=Decimal("0.72"), model_version="test-model-1"):
    scan = DailyCandidateScan(scan_date=as_of.date(), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=predicted_probability, confidence=confidence, sma20_distance=Decimal("0.08"),
        volume_ratio_20d=Decimal("1.80"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=model_version, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id)


def _make_stock(session, symbol="AAA"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _evaluate(session, prediction, *, win: bool):
    session.add(MarketPrice(
        stock_id=prediction.stock_id, timestamp=prediction.as_of_timestamp + timedelta(days=1),
        open=Decimal("106") if win else Decimal("95"), high=Decimal("107") if win else Decimal("96"),
        low=Decimal("105") if win else Decimal("94"), close=Decimal("106") if win else Decimal("95"),
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)


def test_no_revisions_is_stable(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF)

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF)

    assert assessment.revision_count == 0
    assert assessment.stability_verdict == STABILITY_VERDICT_STABLE
    assert assessment.model_agreement_verdict == AGREEMENT_VERDICT_NO_DATA
    assert assessment.assessment_rule_version == STABILITY_ASSESSMENT_VERSION


def test_small_revisions_are_stable(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF, confidence=Decimal("0.80"), predicted_probability=Decimal("0.72"))
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), confidence=Decimal("0.81"), predicted_probability=Decimal("0.73"))
    create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=1),
    )

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=1))

    assert assessment.revision_count == 1
    assert assessment.stability_verdict == STABILITY_VERDICT_STABLE
    assert assessment.unexplained_revision_count == 0


def test_large_score_delta_is_unstable(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF, confidence=Decimal("0.61"), predicted_probability=Decimal("0.61"))
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), confidence=Decimal("0.98"), predicted_probability=Decimal("0.98"))
    create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=1),
    )

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=1))

    assert assessment.stability_verdict == STABILITY_VERDICT_UNSTABLE


def test_too_many_revisions_is_unstable(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF)
    previous = original
    for i in range(MAX_STABLE_REVISIONS + 1):
        as_of = AS_OF + timedelta(days=i + 1)
        revised = _make_prediction(session, stock, as_of=as_of, confidence=Decimal("0.80"), predicted_probability=Decimal("0.72"))
        create_recommendation_revision(
            session, original_prediction=original, previous_prediction=previous, revised_prediction=revised,
            revision_reason=REASON_EVIDENCE_STALE, revised_at=as_of,
        )
        previous = revised

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=10))

    assert assessment.revision_count == MAX_STABLE_REVISIONS + 1
    assert assessment.stability_verdict == STABILITY_VERDICT_UNSTABLE


def test_unexplained_instability_recommends_trust_reduction(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF)
    previous = original
    reasons = [REASON_MANUAL_TRIGGER] + [REASON_EVIDENCE_STALE] * MAX_STABLE_REVISIONS
    for i, reason in enumerate(reasons):
        as_of = AS_OF + timedelta(days=i + 1)
        revised = _make_prediction(session, stock, as_of=as_of, confidence=Decimal("0.80"), predicted_probability=Decimal("0.72"))
        create_recommendation_revision(
            session, original_prediction=original, previous_prediction=previous, revised_prediction=revised,
            revision_reason=reason, revised_at=as_of,
        )
        previous = revised

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=10))

    assert assessment.stability_verdict == STABILITY_VERDICT_UNSTABLE
    assert assessment.unexplained_revision_count == 1
    assert assessment.trust_reduction_recommended is True


def test_model_agreement_agree(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF, confidence=Decimal("0.80"), predicted_probability=Decimal("0.72"), model_version="model-a")
    _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), confidence=Decimal("0.81"), predicted_probability=Decimal("0.73"), model_version="model-b")

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=1))

    assert assessment.model_agreement_verdict == AGREEMENT_VERDICT_AGREE


def test_model_agreement_disagree(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF, confidence=Decimal("0.61"), predicted_probability=Decimal("0.61"), model_version="model-a")
    _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), confidence=Decimal("0.98"), predicted_probability=Decimal("0.98"), model_version="model-b")

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=1))

    assert assessment.model_agreement_verdict == AGREEMENT_VERDICT_DISAGREE
    assert assessment.trust_reduction_recommended is True


def test_stability_backed_by_outcomes_requires_success(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF)
    _evaluate(session, original, win=True)

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=1))

    assert assessment.stability_verdict == STABILITY_VERDICT_STABLE
    assert assessment.stability_backed_by_outcomes is True


def test_stability_without_outcome_is_not_backed(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF)

    assessment = assess_prediction_stability(session, original, assessed_at=AS_OF)

    assert assessment.stability_backed_by_outcomes is False


def test_idempotent_and_history(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF)

    first = assess_prediction_stability(session, original, assessed_at=AS_OF)
    second = assess_prediction_stability(session, original, assessed_at=AS_OF)
    third = assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=1))

    assert first.id == second.id
    assert third.id != first.id
    assert len(get_stability_history(session, original.id)) == 2


def test_never_writes_to_predictions_or_revisions(session):
    stock = _make_stock(session)
    original = _make_prediction(session, stock, as_of=AS_OF)
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1))
    create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=1),
    )
    before = [(p.confidence, p.opportunity_score) for p in (original, revised)]

    assess_prediction_stability(session, original, assessed_at=AS_OF + timedelta(days=1))

    after = [(p.confidence, p.opportunity_score) for p in (original, revised)]
    assert before == after
