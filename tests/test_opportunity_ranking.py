from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_quality import QUALITY_HIGH
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_SUFFICIENT
from app.models import (
    DailyCandidateScan,
    EvidenceQualityDecision,
    MarketPrice,
    Prediction,
    PredictionStabilityAssessment,
    PredictionTrustScore,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import (
    OPPORTUNITY_RANKING_VERSION,
    REASON_DUPLICATE_STOCK_LOWER_SCORE,
    REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT,
    REASON_MISSING_TRUST_SCORE,
    REASON_NOT_GATE_PASSED,
    REASON_SECTOR_CONCENTRATION_LIMIT,
    MAX_INCLUDED_PER_SECTOR,
    PositiveOpportunityRankingImmutableError,
    get_ranking_history,
    rank_positive_opportunities,
)
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_stability import STABILITY_ASSESSMENT_VERSION, STABILITY_VERDICT_STABLE
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION
from app.target_stop_loss import publish_recommendation

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
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


def _make_prediction(session, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), stock=None):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    if stock is None:
        stock = Stock(symbol=symbol, exchange="NSE", sector=sector, is_active=True)
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
    return prediction


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


def _add_stability(session, prediction, verdict=STABILITY_VERDICT_STABLE):
    session.add(PredictionStabilityAssessment(
        original_prediction_id=prediction.id, revision_count=0, max_score_delta=None, max_confidence_delta=None,
        unexplained_revision_count=0, stability_verdict=verdict, model_agreement_verdict="NO_DISAGREEMENT_DATA",
        model_agreement_score_delta=None, stability_backed_by_outcomes=False, trust_reduction_recommended=False,
        assessed_at=AS_OF, assessment_rule_version=STABILITY_ASSESSMENT_VERSION,
    ))
    session.commit()


def _make_gate_passed_prediction(session, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), trust_score=Decimal("0.9"), stock=None):
    prediction = _make_prediction(session, symbol=symbol, sector=sector, target_return=target_return, stock=stock)
    _add_evidence_quality(session, prediction)
    _add_trust_score(session, prediction, score=trust_score)
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    return prediction


def test_not_gate_passed_is_excluded(session):
    prediction = _make_prediction(session)

    rows = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)

    assert len(rows) == 1
    assert rows[0].included is False
    assert rows[0].exclusion_reason == REASON_NOT_GATE_PASSED
    assert rows[0].composite_score is None
    assert rows[0].ranking_rule_version == OPPORTUNITY_RANKING_VERSION


def test_gate_passed_single_candidate_is_included_and_ranked_first(session):
    prediction = _make_gate_passed_prediction(session)

    rows = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)

    assert len(rows) == 1
    row = rows[0]
    assert row.included is True
    assert row.exclusion_reason is None
    assert row.rank_position == 1
    assert row.expected_return_component == Decimal("0.05")
    assert row.trust_component == Decimal("0.9")
    assert row.reward_risk_component is None
    assert row.stability_component is None
    assert Decimal("0") < row.composite_score <= Decimal("1")


def test_reward_risk_and_stability_included_when_available(session):
    prediction = _make_gate_passed_prediction(session)
    publish_recommendation(session, prediction, published_at=AS_OF)
    _add_stability(session, prediction)

    rows = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)

    row = rows[0]
    assert row.reward_risk_component is not None
    assert row.stability_component == Decimal("1")
    assert row.included is True


def test_higher_score_ranks_above_lower_score(session):
    strong = _make_gate_passed_prediction(session, symbol="AAA", sector="TECH", target_return=Decimal("0.10"), trust_score=Decimal("0.9"))
    weak = _make_gate_passed_prediction(session, symbol="BBB", sector="PHARMA", target_return=Decimal("0.02"), trust_score=Decimal("0.3"))

    rows = rank_positive_opportunities(session, [weak.id, strong.id], evaluated_at=AS_OF)

    by_prediction = {r.prediction_id: r for r in rows}
    assert by_prediction[strong.id].rank_position == 1
    assert by_prediction[weak.id].rank_position == 2
    assert by_prediction[strong.id].composite_score > by_prediction[weak.id].composite_score


def test_duplicate_stock_keeps_only_higher_score(session):
    prediction_weak = _make_gate_passed_prediction(session, symbol="AAA", target_return=Decimal("0.02"), trust_score=Decimal("0.4"))
    # Second prediction on the SAME stock, stronger signal.
    stock = session.get(Stock, prediction_weak.stock_id)
    prediction_strong = _make_gate_passed_prediction(session, target_return=Decimal("0.09"), trust_score=Decimal("0.9"), stock=stock)

    rows = rank_positive_opportunities(session, [prediction_weak.id, prediction_strong.id], evaluated_at=AS_OF)

    by_prediction = {r.prediction_id: r for r in rows}
    assert by_prediction[prediction_strong.id].included is True
    assert by_prediction[prediction_strong.id].rank_position == 1
    assert by_prediction[prediction_weak.id].included is False
    assert by_prediction[prediction_weak.id].exclusion_reason == REASON_DUPLICATE_STOCK_LOWER_SCORE
    assert by_prediction[prediction_weak.id].rank_position is None


def test_sector_concentration_limit_excludes_overflow(session):
    predictions = [
        _make_gate_passed_prediction(
            session, symbol=f"SEC{i}", sector="TECH",
            target_return=Decimal("0.05") + Decimal(i) / Decimal("1000"), trust_score=Decimal("0.9"),
        )
        for i in range(MAX_INCLUDED_PER_SECTOR + 2)
    ]

    rows = rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=AS_OF)

    included = [r for r in rows if r.included]
    excluded_for_sector = [r for r in rows if r.exclusion_reason == REASON_SECTOR_CONCENTRATION_LIMIT]
    assert len(included) == MAX_INCLUDED_PER_SECTOR
    assert len(excluded_for_sector) == 2
    # The two weakest (lowest target_return -> lowest composite score) are the ones excluded.
    excluded_ids = {r.prediction_id for r in excluded_for_sector}
    assert excluded_ids == {predictions[0].id, predictions[1].id}


def test_missing_trust_score_excluded_defensively(session):
    prediction = _make_prediction(session)
    _add_evidence_quality(session, prediction)
    # No trust score computed, but simulate an inconsistent PASS decision.
    from app.models import PositiveRecommendationGateDecision
    session.add(PositiveRecommendationGateDecision(
        prediction_id=prediction.id, verdict="GATE_PASS", evidence_quality_met=True, trust_quality_met=True,
        segment_trust_met=True, calibration_drift_met=True, suppression_reasons=[], evaluated_at=AS_OF,
        gate_rule_version="PRG-001",
    ))
    session.commit()

    rows = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)

    assert rows[0].included is False
    assert rows[0].exclusion_reason == REASON_MISSING_TRUST_SCORE


def test_evidence_quality_not_sufficient_excluded_defensively(session):
    prediction = _make_prediction(session)
    _add_trust_score(session, prediction)
    from app.models import PositiveRecommendationGateDecision
    session.add(PositiveRecommendationGateDecision(
        prediction_id=prediction.id, verdict="GATE_PASS", evidence_quality_met=True, trust_quality_met=True,
        segment_trust_met=True, calibration_drift_met=True, suppression_reasons=[], evaluated_at=AS_OF,
        gate_rule_version="PRG-001",
    ))
    session.commit()

    rows = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)

    assert rows[0].included is False
    assert rows[0].exclusion_reason == REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT


def test_idempotent_by_evaluated_at(session):
    prediction = _make_gate_passed_prediction(session)

    first = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)
    second = rank_positive_opportunities(session, [], evaluated_at=AS_OF)

    assert [r.id for r in first] == [r.id for r in second]


def test_horizon_days_filter_excludes_other_horizons(session):
    prediction = _make_gate_passed_prediction(session)
    assert prediction.horizon_days == 1

    rows = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF, horizon_days=5)

    assert rows == ()


def test_ranking_row_is_immutable(session):
    prediction = _make_gate_passed_prediction(session)
    row = rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)[0]

    row.rank_position = 99
    with pytest.raises(PositiveOpportunityRankingImmutableError):
        session.commit()
    session.rollback()


def test_get_ranking_history_returns_rows_for_prediction(session):
    prediction = _make_gate_passed_prediction(session)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF + timedelta(days=1))

    history = get_ranking_history(session, prediction.id)

    assert len(history) == 2
    assert history[0].evaluated_at < history[1].evaluated_at
