from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.evidence_snapshot import (
    EVIDENCE_CATEGORY_FUNDAMENTAL,
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME,
    STATUS_AVAILABLE,
)
from app.information_latency import (
    LATENCY_RULE_VERSION,
    REASON_MISSING_TIMESTAMP,
    REASON_STALE_CATEGORY,
    VERDICT_DEGRADED,
    VERDICT_IMPROVED,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_STABLE,
    assess_information_latency,
    get_degradation_report_history,
    get_latency_history,
    horizon_adjusted_threshold,
    measure_latency_degradation,
    sla_multiplier_for_horizon,
)
from app.models import DataFetchAttempt, Prediction, RecommendationEvidenceItem, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.refresh_policy import DATA_TYPE_MARKET, FRESHNESS_POLICY, REFRESH_POLICY_VERSION

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)


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


_stock_counter = iter(range(1000000))


def _make_prediction(session, *, horizon_days=5):
    stock = Stock(symbol=f"S{next(_stock_counter)}", exchange="NSE", is_active=True)
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
    return prediction


def _add_item(session, prediction, *, category, evidence_timestamp, status=STATUS_AVAILABLE):
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category=category, status=status, source="test",
        reference=None, evidence_timestamp=evidence_timestamp, is_stale=False, snapshot_rule_version="EVS-001",
        captured_at=AS_OF,
    ))
    session.commit()


def test_sla_multiplier_tightens_for_short_horizons():
    assert sla_multiplier_for_horizon(1) == Decimal("0.5")
    assert sla_multiplier_for_horizon(3) == Decimal("0.75")
    assert sla_multiplier_for_horizon(7) == Decimal("1.0")


def test_horizon_adjusted_threshold_scales_base_policy():
    base = FRESHNESS_POLICY[DATA_TYPE_MARKET]
    assert horizon_adjusted_threshold(base, 1) == base * 0.5
    assert horizon_adjusted_threshold(base, 7) == base


def test_no_violations_when_evidence_within_horizon_adjusted_sla(session):
    prediction = _make_prediction(session, horizon_days=7)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=AS_OF - timedelta(hours=2))
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_NEWS, evidence_timestamp=AS_OF - timedelta(hours=1))

    assessment = assess_information_latency(session, prediction, evaluated_at=AS_OF)

    assert assessment.sla_violations == []
    assert assessment.suppress_eligibility is False
    assert assessment.latency_rule_version == LATENCY_RULE_VERSION
    assert assessment.category_latency_seconds[EVIDENCE_CATEGORY_TECHNICAL_VOLUME] == 7200.0


def test_short_horizon_flags_evidence_that_a_long_horizon_would_accept(session):
    # Market data freshness policy is 1 day; 20 hours old is within a
    # 7-day horizon's full SLA but violates a 1-day horizon's tightened one.
    long_horizon = _make_prediction(session, horizon_days=7)
    short_horizon = _make_prediction(session, horizon_days=1)
    stale_timestamp = AS_OF - timedelta(hours=20)
    _add_item(session, long_horizon, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=stale_timestamp)
    _add_item(session, short_horizon, category=EVIDENCE_CATEGORY_TECHNICAL_VOLUME, evidence_timestamp=stale_timestamp)

    long_assessment = assess_information_latency(session, long_horizon, evaluated_at=AS_OF)
    short_assessment = assess_information_latency(session, short_horizon, evaluated_at=AS_OF)

    assert long_assessment.suppress_eligibility is False
    assert short_assessment.suppress_eligibility is True
    assert EVIDENCE_CATEGORY_TECHNICAL_VOLUME in short_assessment.sla_violations
    assert f"{EVIDENCE_CATEGORY_TECHNICAL_VOLUME}:{REASON_STALE_CATEGORY}" in short_assessment.reasons


def test_missing_evidence_timestamp_is_flagged_not_silently_ignored(session):
    prediction = _make_prediction(session, horizon_days=5)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_FUNDAMENTAL, evidence_timestamp=None)

    assessment = assess_information_latency(session, prediction, evaluated_at=AS_OF)

    assert assessment.suppress_eligibility is True
    assert f"{EVIDENCE_CATEGORY_FUNDAMENTAL}:{REASON_MISSING_TIMESTAMP}" in assessment.reasons


def test_assessment_is_idempotent(session):
    prediction = _make_prediction(session, horizon_days=5)
    _add_item(session, prediction, category=EVIDENCE_CATEGORY_NEWS, evidence_timestamp=AS_OF - timedelta(hours=1))

    first = assess_information_latency(session, prediction, evaluated_at=AS_OF)
    second = assess_information_latency(session, prediction, evaluated_at=AS_OF)

    assert first.id == second.id
    assert len(get_latency_history(session, prediction.id)) == 1


def _add_fetch_attempt(session, *, requested_at, source_timestamp):
    session.add(DataFetchAttempt(
        data_type=DATA_TYPE_MARKET, scope_key="AAA", requested_at=requested_at, source_timestamp=source_timestamp,
        success=True, failure_reason=None, refresh_policy_version=REFRESH_POLICY_VERSION, provider_id="yahoo",
    ))
    session.commit()


def test_degradation_report_insufficient_sample_below_minimum(session):
    _add_fetch_attempt(session, requested_at=AS_OF, source_timestamp=AS_OF - timedelta(minutes=30))
    window = EvaluationWindow(label="current", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))
    baseline = EvaluationWindow(label="baseline", start=AS_OF - timedelta(days=30), end=AS_OF - timedelta(days=1))

    report = measure_latency_degradation(session, data_type=DATA_TYPE_MARKET, window=window, baseline_window=baseline, computed_at=AS_OF)

    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_degradation_report_flags_worsening_latency(session):
    baseline_start = AS_OF - timedelta(days=30)
    for i in range(20):
        _add_fetch_attempt(session, requested_at=baseline_start + timedelta(hours=i), source_timestamp=baseline_start + timedelta(hours=i) - timedelta(minutes=10))
    for i in range(20):
        _add_fetch_attempt(session, requested_at=AS_OF + timedelta(hours=i), source_timestamp=AS_OF + timedelta(hours=i) - timedelta(hours=6))

    window = EvaluationWindow(label="current", start=AS_OF - timedelta(hours=1), end=AS_OF + timedelta(days=2))
    baseline = EvaluationWindow(label="baseline", start=baseline_start - timedelta(hours=1), end=baseline_start + timedelta(days=1))

    report = measure_latency_degradation(session, data_type=DATA_TYPE_MARKET, window=window, baseline_window=baseline, computed_at=AS_OF)

    assert report.verdict == VERDICT_DEGRADED
    assert report.degradation_ratio > 0
    assert len(get_degradation_report_history(session, DATA_TYPE_MARKET)) == 1


def test_degradation_report_flags_improving_latency(session):
    baseline_start = AS_OF - timedelta(days=30)
    for i in range(20):
        _add_fetch_attempt(session, requested_at=baseline_start + timedelta(hours=i), source_timestamp=baseline_start + timedelta(hours=i) - timedelta(hours=6))
    for i in range(20):
        _add_fetch_attempt(session, requested_at=AS_OF + timedelta(hours=i), source_timestamp=AS_OF + timedelta(hours=i) - timedelta(minutes=10))

    window = EvaluationWindow(label="current", start=AS_OF - timedelta(hours=1), end=AS_OF + timedelta(days=2))
    baseline = EvaluationWindow(label="baseline", start=baseline_start - timedelta(hours=1), end=baseline_start + timedelta(days=1))

    report = measure_latency_degradation(session, data_type=DATA_TYPE_MARKET, window=window, baseline_window=baseline, computed_at=AS_OF)

    assert report.verdict == VERDICT_IMPROVED
    assert report.degradation_ratio < 0
