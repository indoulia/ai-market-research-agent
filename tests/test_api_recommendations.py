"""Contract tests for GET /api/v1/recommendations (EPIC-M1.135)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.confidence_quality import QUALITY_HIGH
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_SUFFICIENT
from app.lifecycle import LIFECYCLE_VERSION, STATE_ISSUED
from app.models import (
    DailyCandidateScan,
    EvidenceQualityDecision,
    MarketPrice,
    Prediction,
    PredictionTrustScore,
    RecommendationEvidenceItem,
    RecommendationGeneration,
    RecommendationLifecycle,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import rank_positive_opportunities
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

from api.deps import get_db
from app.main import app

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
_scan_counter = iter(range(100000))


@pytest.fixture
def session():
    # StaticPool + check_same_thread=False: the FastAPI TestClient dispatches
    # sync route handlers onto a worker thread, and a bare `sqlite:///:memory:`
    # engine hands each thread its own empty in-memory database (or errors
    # outright) -- a single shared connection is required for the app and
    # this fixture's session to see the same tables/rows.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _make_prediction(session, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), market_cap=Decimal("1000000000")):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, company_name=f"{symbol} Ltd", market_cap=market_cap, is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=target_return, stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, generation, stock, scan


def _add_evidence_quality(session, prediction, state=STATE_SUFFICIENT):
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=state, available_category_count=2, stale_category_count=0,
        unavailable_category_count=3, categories_considered=["TECHNICAL_VOLUME", "NEWS"], leaked_categories=[],
        reasons=[], confidence_adjustment_ceiling=prediction.confidence, blocks_publication=(state != STATE_SUFFICIENT),
        evaluated_at=AS_OF, gate_rule_version=EVIDENCE_QUALITY_GATE_VERSION,
    ))
    session.commit()


def _add_trust_score(session, prediction, score=Decimal("0.9")):
    session.add(PredictionTrustScore(
        prediction_id=prediction.id, overall_trust_score=score, trust_quality=QUALITY_HIGH,
        calibration_component=None, historical_accuracy_component=None, recent_performance_component=None,
        horizon_reliability_component=None, regime_reliability_component=None, evidence_quality_component=None,
        available_component_count=1, reasons=[], computed_at=AS_OF, trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    ))
    session.commit()


def _add_lifecycle(session, generation, state=STATE_ISSUED):
    lifecycle = RecommendationLifecycle(
        recommendation_generation_id=generation.id, state=state, lifecycle_rule_version=LIFECYCLE_VERSION, check_count=0,
    )
    session.add(lifecycle)
    session.commit()
    return lifecycle


def _make_gate_passed(session, *, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), trust_score=Decimal("0.9"), market_cap=Decimal("1000000000")):
    """Create a prediction that clears M1.81's positive gate, WITHOUT ranking
    it. `rank_positive_opportunities` is idempotent per `evaluated_at` -- a
    second call for the same timestamp returns the first call's snapshot
    unchanged -- so every prediction meant to appear in the same feed must
    be ranked together in one `_rank_and_activate` call, not one-by-one."""
    prediction, generation, stock, _scan = _make_prediction(session, symbol=symbol, sector=sector, target_return=target_return, market_cap=market_cap)
    _add_evidence_quality(session, prediction)
    _add_trust_score(session, prediction, score=trust_score)
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    return prediction, generation, stock


def _rank_and_activate(session, entries, *, evaluated_at=AS_OF):
    """Rank every (prediction, generation, stock) tuple together in one
    batch, then bring each generation into the live feed (ISSUED). Returns
    the input unchanged for convenient chaining."""
    predictions = [prediction for prediction, _generation, _stock in entries]
    rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=evaluated_at)
    for _prediction, generation, _stock in entries:
        _add_lifecycle(session, generation)
    return entries


def _make_ranked_recommendation(session, **kwargs):
    """Convenience for the common single-recommendation case."""
    entry = _make_gate_passed(session, **kwargs)
    _rank_and_activate(session, [entry])
    return entry


def test_empty_when_no_ranking_batch_exists(client):
    response = client.get("/api/v1/recommendations")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["nextCursor"] is None
    assert body["meta"]["pageSize"] == 20


def test_returns_ranked_positive_recommendation_with_full_fields(client, session):
    prediction, generation, stock = _make_ranked_recommendation(session)

    response = client.get("/api/v1/recommendations")
    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == generation.id
    assert item["symbol"] == "AAA"
    assert item["exchange"] == "NSE"
    assert item["companyName"] == "AAA Ltd"
    assert item["recommendation"] == "POSITIVE_OPPORTUNITY"
    assert item["status"] == STATE_ISSUED
    assert item["probability"] == "0.72000000"
    assert item["trustScore"] == "0.90000000"
    assert item["evidenceFreshness"] == "UNKNOWN"  # no RecommendationEvidenceItem recorded
    assert item["predictionVersion"]["modelVersion"] == MODEL_VERSION
    assert item["predictionVersion"]["rankingVersion"]
    assert Decimal(item["score"]) > 0


def test_only_positive_eligible_recommendations_are_returned(client, session):
    passed = _make_gate_passed(session, symbol="AAA")
    # Never gate-passed -> ranked-but-excluded (REASON_NOT_GATE_PASSED), not visible.
    prediction, generation, stock, _scan = _make_prediction(session, symbol="BBB")
    not_passed = (prediction, generation, stock)
    _rank_and_activate(session, [passed, not_passed])

    response = client.get("/api/v1/recommendations")
    symbols = [item["symbol"] for item in response.json()["data"]]
    assert symbols == ["AAA"]


def test_closed_lifecycle_recommendations_are_excluded(client, session):
    from app.lifecycle import STATE_EVALUATED

    prediction, generation, stock = _make_ranked_recommendation(session, symbol="AAA")
    # _make_ranked_recommendation already added an ISSUED lifecycle; move it to terminal.
    lifecycle = session.query(RecommendationLifecycle).filter_by(recommendation_generation_id=generation.id).one()
    lifecycle.state = STATE_EVALUATED
    session.commit()

    response = client.get("/api/v1/recommendations")
    assert response.json()["data"] == []


def test_ranking_is_ordered_by_score_descending_by_default(client, session):
    low = _make_gate_passed(session, symbol="LOW", target_return=Decimal("0.02"), trust_score=Decimal("0.3"))
    high = _make_gate_passed(session, symbol="HIGH", target_return=Decimal("0.15"), trust_score=Decimal("0.95"))
    _rank_and_activate(session, [low, high])

    response = client.get("/api/v1/recommendations")
    symbols = [item["symbol"] for item in response.json()["data"]]
    assert symbols == ["HIGH", "LOW"]


def test_market_cap_bucket_filter_uses_crore_thresholds(client, session):
    # Regression test: this filter must reuse app.discovery_segmentation's
    # canonical INR-crore thresholds (LARGE_CAP >= 20000, MID_CAP >= 5000,
    # else SMALL_CAP) -- an earlier version of this endpoint invented its
    # own absolute-currency thresholds that never matched real data.
    small = _make_gate_passed(session, symbol="SMALL", sector="S1", market_cap=Decimal("1000"))
    large = _make_gate_passed(session, symbol="LARGE", sector="S2", market_cap=Decimal("50000"))
    _rank_and_activate(session, [small, large])

    response = client.get("/api/v1/recommendations", params={"marketCapBucket": "LARGE_CAP"})
    symbols = [item["symbol"] for item in response.json()["data"]]
    assert symbols == ["LARGE"]

    response = client.get("/api/v1/recommendations", params={"marketCapBucket": "SMALL_CAP"})
    symbols = [item["symbol"] for item in response.json()["data"]]
    assert symbols == ["SMALL"]


def test_horizon_filter(client, session):
    aaa = _make_gate_passed(session, symbol="AAA")
    bbb = _make_gate_passed(session, symbol="BBB")
    _rank_and_activate(session, [aaa, bbb])
    aaa_horizon = aaa[0].horizon_days
    bbb_horizon = bbb[0].horizon_days

    response = client.get("/api/v1/recommendations", params={"horizon": bbb_horizon})
    symbols = [item["symbol"] for item in response.json()["data"]]
    assert "BBB" in symbols
    if aaa_horizon != bbb_horizon:
        assert "AAA" not in symbols


def test_min_score_filter_excludes_low_scoring_rows(client, session):
    low = _make_gate_passed(session, symbol="LOW", target_return=Decimal("0.01"), trust_score=Decimal("0.2"))
    high = _make_gate_passed(session, symbol="HIGH", target_return=Decimal("0.15"), trust_score=Decimal("0.95"))
    _rank_and_activate(session, [low, high])

    all_items = client.get("/api/v1/recommendations").json()["data"]
    low_score = next(i for i in all_items if i["symbol"] == "LOW")["score"]

    response = client.get("/api/v1/recommendations", params={"minScore": str(Decimal(low_score) + Decimal("0.01"))})
    symbols = [item["symbol"] for item in response.json()["data"]]
    assert symbols == ["HIGH"]


def test_sort_by_trust_ascending(client, session):
    aaa = _make_gate_passed(session, symbol="AAA", trust_score=Decimal("0.4"))
    bbb = _make_gate_passed(session, symbol="BBB", trust_score=Decimal("0.9"))
    _rank_and_activate(session, [aaa, bbb])

    response = client.get("/api/v1/recommendations", params={"sort": "trust", "direction": "asc"})
    symbols = [item["symbol"] for item in response.json()["data"]]
    assert symbols == ["AAA", "BBB"]


def test_cursor_pagination_covers_every_row_exactly_once(client, session):
    # Distinct sectors: M1.87's ranking caps included opportunities at
    # MAX_INCLUDED_PER_SECTOR=3 per sector, which would otherwise silently
    # exclude 2 of these 5 and has nothing to do with pagination itself.
    entries = [
        _make_gate_passed(session, symbol=f"S{i}", sector=f"SECTOR{i}", target_return=Decimal("0.02") + Decimal(i) / 100)
        for i in range(5)
    ]
    _rank_and_activate(session, entries)

    seen = []
    cursor = None
    for _ in range(10):
        params = {"pageSize": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/v1/recommendations", params=params).json()
        seen.extend(item["symbol"] for item in body["data"])
        cursor = body["meta"]["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


def test_stale_evidence_is_reported_not_hidden(client, session):
    prediction, generation, stock = _make_ranked_recommendation(session, symbol="AAA")
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category="NEWS_EVENT", status="STALE", source="test",
        reference=None, evidence_timestamp=AS_OF, is_stale=True, snapshot_rule_version="EV-001", captured_at=AS_OF,
    ))
    session.commit()

    response = client.get("/api/v1/recommendations")
    assert response.json()["data"][0]["evidenceFreshness"] == "STALE"


def test_unknown_sort_field_is_rejected(client):
    response = client.get("/api/v1/recommendations", params={"sort": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_invalid_cursor_is_rejected(client, session):
    _make_ranked_recommendation(session)
    response = client.get("/api/v1/recommendations", params={"cursor": "not-valid-base64!!"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"
