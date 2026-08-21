"""Contract tests for GET /api/v1/opportunities (EPIC-M3.3)."""

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
from app.lifecycle import LIFECYCLE_VERSION, STATE_AWAITING_HORIZON, STATE_EVALUATED, STATE_ISSUED
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


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # api.rate_limit.default_limiter is a module-level singleton shared by
    # every TestClient across the whole pytest session (keyed on the fixed
    # fake client host TestClient always uses), so this file's ~20 extra
    # requests would otherwise accumulate into whatever count later test
    # files (e.g. test_api_tracking.py) inherit within the same 60s fixed
    # window -- clearing it before/after this file's own tests keeps this
    # file both self-contained and a no-op contributor to that shared state.
    from api.rate_limit import default_limiter

    default_limiter._hits.clear()
    yield
    default_limiter._hits.clear()


def _make_prediction(
    session,
    symbol="AAA",
    sector="TECH",
    company_name=None,
    target_return=Decimal("0.05"),
    market_cap=Decimal("1000000000"),
    volume_ratio_20d=Decimal("1.10"),
):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(
        symbol=symbol, exchange="NSE", sector=sector, company_name=company_name or f"{symbol} Ltd",
        market_cap=market_cap, is_active=True,
    )
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
        volume_ratio_20d=volume_ratio_20d, atr_percent=Decimal("0.035"),
        data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
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


def _make_gate_passed(session, *, symbol="AAA", sector="TECH", company_name=None, target_return=Decimal("0.05"),
                       trust_score=Decimal("0.9"), market_cap=Decimal("1000000000"), volume_ratio_20d=Decimal("1.10")):
    prediction, generation, stock, _scan = _make_prediction(
        session, symbol=symbol, sector=sector, company_name=company_name, target_return=target_return,
        market_cap=market_cap, volume_ratio_20d=volume_ratio_20d,
    )
    _add_evidence_quality(session, prediction)
    _add_trust_score(session, prediction, score=trust_score)
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    return prediction, generation, stock


def _rank_and_activate(session, entries, *, evaluated_at=AS_OF, state=STATE_ISSUED):
    predictions = [prediction for prediction, _generation, _stock in entries]
    rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=evaluated_at)
    for _prediction, generation, _stock in entries:
        _add_lifecycle(session, generation, state=state)
    return entries


def _make_ranked_opportunity(session, **kwargs):
    entry = _make_gate_passed(session, **kwargs)
    _rank_and_activate(session, [entry])
    return entry


def test_empty_when_no_ranking_batch_exists(client):
    response = client.get("/api/v1/opportunities")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["pageSize"] == 20
    assert data["asOf"] is None


def test_returns_ranked_opportunity_with_full_fields_and_paging_metadata(client, session):
    prediction, generation, stock = _make_ranked_opportunity(session)

    response = client.get("/api/v1/opportunities")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["pageSize"] == 20
    assert data["asOf"] is not None
    item = data["items"][0]
    assert item["id"] == generation.id
    assert item["symbol"] == "AAA"
    assert item["recommendation"] == "POSITIVE_OPPORTUNITY"
    assert item["status"] == STATE_ISSUED
    assert item["trustScore"] == "0.90000000"
    assert data["filters"]["sort"] == "-score"
    assert data["filters"]["market"] is None


def test_only_positive_eligible_opportunities_are_returned(client, session):
    passed = _make_gate_passed(session, symbol="AAA")
    prediction, generation, stock, _scan = _make_prediction(session, symbol="BBB")
    not_passed = (prediction, generation, stock)
    _rank_and_activate(session, [passed, not_passed])

    response = client.get("/api/v1/opportunities")
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["AAA"]


def test_closed_lifecycle_opportunities_excluded_by_default(client, session):
    prediction, generation, stock = _make_ranked_opportunity(session, symbol="AAA")
    lifecycle = session.query(RecommendationLifecycle).filter_by(recommendation_generation_id=generation.id).one()
    lifecycle.state = STATE_EVALUATED
    session.commit()

    response = client.get("/api/v1/opportunities")
    assert response.json()["data"]["items"] == []
    assert response.json()["data"]["total"] == 0


def test_status_filter_narrows_to_specific_open_state(client, session):
    issued = _make_gate_passed(session, symbol="ISS")
    awaiting = _make_gate_passed(session, symbol="AWT")
    # Both must be ranked together: rank_positive_opportunities is idempotent
    # per evaluated_at, so a second call for the same timestamp would be a
    # no-op and silently drop whichever entry wasn't in the first batch.
    _rank_and_activate(session, [issued, awaiting], state=STATE_ISSUED)
    lifecycle = session.query(RecommendationLifecycle).filter_by(recommendation_generation_id=awaiting[1].id).one()
    lifecycle.state = STATE_AWAITING_HORIZON
    session.commit()

    response = client.get("/api/v1/opportunities", params={"status": STATE_AWAITING_HORIZON})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["AWT"]


def test_status_filter_rejects_terminal_state(client, session):
    _make_ranked_opportunity(session)
    response = client.get("/api/v1/opportunities", params={"status": STATE_EVALUATED})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_default_sort_is_score_descending(client, session):
    low = _make_gate_passed(session, symbol="LOW", target_return=Decimal("0.02"), trust_score=Decimal("0.3"))
    high = _make_gate_passed(session, symbol="HIGH", target_return=Decimal("0.15"), trust_score=Decimal("0.95"))
    _rank_and_activate(session, [low, high])

    response = client.get("/api/v1/opportunities")
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["HIGH", "LOW"]


def test_sort_by_trust_ascending(client, session):
    aaa = _make_gate_passed(session, symbol="AAA", trust_score=Decimal("0.4"))
    bbb = _make_gate_passed(session, symbol="BBB", trust_score=Decimal("0.9"))
    _rank_and_activate(session, [aaa, bbb])

    response = client.get("/api/v1/opportunities", params={"sort": "trust"})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["AAA", "BBB"]


def test_sort_by_ranking_matches_sort_by_score(client, session):
    low = _make_gate_passed(session, symbol="LOW", target_return=Decimal("0.02"), trust_score=Decimal("0.3"))
    high = _make_gate_passed(session, symbol="HIGH", target_return=Decimal("0.15"), trust_score=Decimal("0.95"))
    _rank_and_activate(session, [low, high])

    by_score = client.get("/api/v1/opportunities", params={"sort": "-score"}).json()["data"]["items"]
    by_ranking = client.get("/api/v1/opportunities", params={"sort": "-ranking"}).json()["data"]["items"]
    assert [i["symbol"] for i in by_score] == [i["symbol"] for i in by_ranking]


def test_sort_by_probability(client, session):
    from app.models import ScanCandidate as SC

    low, gen_low, stock_low = _make_gate_passed(session, symbol="LOWP", trust_score=Decimal("0.5"))
    high, gen_high, stock_high = _make_gate_passed(session, symbol="HIP", trust_score=Decimal("0.5"))
    # bump predicted_probability directly for a deterministic ordering
    session.query(SC).filter_by(stock_id=stock_high.id).update({"predicted_probability": Decimal("0.95")})
    session.query(SC).filter_by(stock_id=stock_low.id).update({"predicted_probability": Decimal("0.55")})
    session.commit()
    _rank_and_activate(session, [(low, gen_low, stock_low), (high, gen_high, stock_high)])

    response = client.get("/api/v1/opportunities", params={"sort": "-probability"})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["HIP", "LOWP"]


def test_min_upside_filter(client, session):
    low = _make_gate_passed(session, symbol="LOW", target_return=Decimal("0.01"))
    high = _make_gate_passed(session, symbol="HIGH", target_return=Decimal("0.20"))
    _rank_and_activate(session, [low, high])

    response = client.get("/api/v1/opportunities", params={"minUpside": "10"})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["HIGH"]


def test_liquidity_bucket_filter(client, session):
    # volume_ratio_20d below 0.75 fails M1.8's consensus gate before a
    # prediction is ever created, so LOW-bucket opportunities cannot exist
    # in this universe -- exercise the two buckets that legitimately occur.
    normal = _make_gate_passed(session, symbol="NORMAL", sector="S1", volume_ratio_20d=Decimal("1.00"))
    heavy = _make_gate_passed(session, symbol="HEAVY", sector="S2", volume_ratio_20d=Decimal("2.00"))
    _rank_and_activate(session, [normal, heavy])

    response = client.get("/api/v1/opportunities", params={"liquidityBucket": "HIGH"})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["HEAVY"]

    response = client.get("/api/v1/opportunities", params={"liquidityBucket": "NORMAL"})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["NORMAL"]


def test_market_cap_filter_uses_crore_thresholds(client, session):
    small = _make_gate_passed(session, symbol="SMALL", sector="S1", market_cap=Decimal("1000"))
    large = _make_gate_passed(session, symbol="LARGE", sector="S2", market_cap=Decimal("50000"))
    _rank_and_activate(session, [small, large])

    response = client.get("/api/v1/opportunities", params={"marketCap": "LARGE_CAP"})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["LARGE"]


def test_search_matches_symbol_or_company_name(client, session):
    a = _make_gate_passed(session, symbol="RELI", sector="S1", company_name="Reliance Industries")
    b = _make_gate_passed(session, symbol="TCS", sector="S2", company_name="Tata Consultancy Services")
    _rank_and_activate(session, [a, b])

    by_symbol = client.get("/api/v1/opportunities", params={"search": "reli"}).json()["data"]["items"]
    assert [i["symbol"] for i in by_symbol] == ["RELI"]

    by_name = client.get("/api/v1/opportunities", params={"search": "Tata"}).json()["data"]["items"]
    assert [i["symbol"] for i in by_name] == ["TCS"]


def test_pagination_is_page_based_and_reports_total(client, session):
    entries = [
        _make_gate_passed(session, symbol=f"S{i}", sector=f"SECTOR{i}", target_return=Decimal("0.02") + Decimal(i) / 100)
        for i in range(5)
    ]
    _rank_and_activate(session, entries)

    page1 = client.get("/api/v1/opportunities", params={"pageSize": 2, "page": 1}).json()["data"]
    page2 = client.get("/api/v1/opportunities", params={"pageSize": 2, "page": 2}).json()["data"]
    page3 = client.get("/api/v1/opportunities", params={"pageSize": 2, "page": 3}).json()["data"]

    assert page1["total"] == 5
    assert page1["page"] == 1
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert len(page3["items"]) == 1
    all_symbols = [i["symbol"] for i in page1["items"] + page2["items"] + page3["items"]]
    assert len(set(all_symbols)) == 5


def test_stale_evidence_is_reported_not_hidden(client, session):
    prediction, generation, stock = _make_ranked_opportunity(session, symbol="AAA")
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category="NEWS_EVENT", status="STALE", source="test",
        reference=None, evidence_timestamp=AS_OF, is_stale=True, snapshot_rule_version="EV-001", captured_at=AS_OF,
    ))
    session.commit()

    response = client.get("/api/v1/opportunities")
    assert response.json()["data"]["items"][0]["evidenceFreshness"] == "STALE"


def test_sort_by_freshness_ranks_stale_last(client, session):
    fresh = _make_gate_passed(session, symbol="FRESH", sector="S1")
    stale = _make_gate_passed(session, symbol="STALE", sector="S2")
    _rank_and_activate(session, [fresh, stale])
    stale_prediction = stale[0]
    session.add(RecommendationEvidenceItem(
        prediction_id=stale_prediction.id, evidence_category="NEWS_EVENT", status="STALE", source="test",
        reference=None, evidence_timestamp=AS_OF, is_stale=True, snapshot_rule_version="EV-001", captured_at=AS_OF,
    ))
    session.commit()

    response = client.get("/api/v1/opportunities", params={"sort": "-freshness"})
    symbols = [item["symbol"] for item in response.json()["data"]["items"]]
    assert symbols == ["FRESH", "STALE"]


def test_unknown_sort_field_is_rejected(client):
    response = client.get("/api/v1/opportunities", params={"sort": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"
