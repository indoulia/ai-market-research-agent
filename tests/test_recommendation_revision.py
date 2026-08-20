from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.recommendation_revision import (
    REASON_EVIDENCE_STALE,
    REASON_MATERIAL_EVIDENCE_CHANGE,
    REVISION_RULE_VERSION,
    ConcurrentRevisionError,
    InvalidRevisionError,
    RecommendationRevisionImmutableError,
    compare_versions,
    create_recommendation_revision,
    get_active_version,
    get_revision_history,
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


def _make_prediction(session, stock, *, as_of, confidence=Decimal("0.80"), opportunity_score_hint=Decimal("0.95")):
    # a fresh scan per call (keyed by as_of's date) so re-using the same
    # stock across multiple revisions never collides with DiscoveryRecord's
    # (scan_id, stock_id, source) uniqueness -- a later revision naturally
    # belongs to a later day's scan anyway.
    scan = DailyCandidateScan(scan_date=as_of.date(), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=opportunity_score_hint, confidence=confidence, sma20_distance=Decimal("0.08"),
        volume_ratio_20d=Decimal("1.80"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id)


def test_a_revision_never_overwrites_the_original(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF)
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), confidence=Decimal("0.90"))
    original_before = (original.entry_price, original.confidence, original.opportunity_score)

    create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=1),
    )

    original_after = (original.entry_price, original.confidence, original.opportunity_score)
    assert original_before == original_after


def test_every_revision_has_a_reason_and_timestamp(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF)
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1))

    revision = create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
    )

    assert revision.revision_reason == REASON_EVIDENCE_STALE
    assert revision.revised_at.replace(tzinfo=None) == (AS_OF + timedelta(days=1)).replace(tzinfo=None)
    assert revision.revision_rule_version == REVISION_RULE_VERSION
    assert revision.version_number == 2


def test_multiple_revisions_build_a_linear_chain(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    v1 = _make_prediction(session, stock, as_of=AS_OF)
    v2 = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1))
    v3 = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=2))

    create_recommendation_revision(
        session, original_prediction=v1, previous_prediction=v1, revised_prediction=v2,
        revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
    )
    create_recommendation_revision(
        session, original_prediction=v1, previous_prediction=v2, revised_prediction=v3,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=2),
    )

    history = get_revision_history(session, v1.id)
    assert [r.version_number for r in history] == [2, 3]
    assert get_active_version(session, v1).id == v3.id


def test_active_version_is_the_original_when_never_revised(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF)

    assert get_active_version(session, original).id == original.id


def test_duplicate_trigger_is_idempotent(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF)
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1))

    first = create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
    )
    second = create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
    )

    assert first.id == second.id
    assert len(get_revision_history(session, original.id)) == 1


def test_concurrent_trigger_with_a_different_revision_is_rejected(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF)
    revised_a = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1))
    revised_b = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=2))

    create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised_a,
        revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
    )

    with pytest.raises(ConcurrentRevisionError):
        create_recommendation_revision(
            session, original_prediction=original, previous_prediction=original, revised_prediction=revised_b,
            revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=1),
        )


def test_invalid_revision_reason_is_rejected(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF)
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1))

    with pytest.raises(InvalidRevisionError):
        create_recommendation_revision(
            session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
            revision_reason="NOT_A_REASON", revised_at=AS_OF + timedelta(days=1),
        )


def test_revision_for_a_different_stock_is_rejected(session):
    stock_a = Stock(symbol="AAA", exchange="NSE", is_active=True)
    stock_b = Stock(symbol="BBB", exchange="NSE", is_active=True)
    session.add_all([stock_a, stock_b])
    session.flush()
    original = _make_prediction(session, stock_a, as_of=AS_OF)
    revised = _make_prediction(session, stock_b, as_of=AS_OF + timedelta(days=1))

    with pytest.raises(InvalidRevisionError):
        create_recommendation_revision(
            session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
            revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
        )


def test_version_comparison_shows_what_changed(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF, confidence=Decimal("0.80"))
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), confidence=Decimal("0.90"))

    revision = create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
    )
    comparison = compare_versions(session, revision)

    assert comparison.confidence_delta == Decimal("0.10")
    assert comparison.previous_prediction_id == original.id
    assert comparison.revised_prediction_id == revised.id


def test_revision_is_immutable_after_creation(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    original = _make_prediction(session, stock, as_of=AS_OF)
    revised = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1))
    revision = create_recommendation_revision(
        session, original_prediction=original, previous_prediction=original, revised_prediction=revised,
        revision_reason=REASON_EVIDENCE_STALE, revised_at=AS_OF + timedelta(days=1),
    )

    revision.revision_reason = REASON_MATERIAL_EVIDENCE_CHANGE
    with pytest.raises(RecommendationRevisionImmutableError, match="revision_reason"):
        session.flush()
    session.rollback()
