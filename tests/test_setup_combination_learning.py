from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Prediction, PredictionAttributionSnapshot, Stock
from app.prediction_attribution import ASSOCIATION_FAILURE, ASSOCIATION_INSUFFICIENT_SAMPLE, ASSOCIATION_NONE, ASSOCIATION_SUCCESS
from app.setup_combination_learning import (
    REPORT_VERDICT_INSUFFICIENT_SAMPLE,
    REPORT_VERDICT_MEASURED,
    SETUP_COMBINATION_VERSION,
    compute_setup_combination_report,
    get_setup_combination_history,
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


def _add_snapshot(session, *, sma_bucket, volume_bucket, horizon_days=1, regime="BULLISH_LOW_VOL", outcome, count):
    for _ in range(count):
        n = next(_counter)
        stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
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
        session.flush()
        session.add(PredictionAttributionSnapshot(
            prediction_id=prediction.id, model_version=MODEL_VERSION, horizon_days=horizon_days, regime=regime,
            sma20_distance_bucket=sma_bucket, volume_ratio_bucket=volume_bucket, evidence_categories_available=[],
            outcome=outcome, snapshotted_at=AS_OF, attribution_rule_version="ATB-001",
        ))
    session.commit()


def test_insufficient_sample_overall(session):
    _add_snapshot(session, sma_bucket="STRONG", volume_bucket="HIGH", outcome="SUCCESS", count=5)

    report = compute_setup_combination_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)

    assert report.verdict == REPORT_VERDICT_INSUFFICIENT_SAMPLE
    assert report.combinations == []
    assert report.report_rule_version == SETUP_COMBINATION_VERSION


def test_combination_associated_with_success(session):
    _add_snapshot(session, sma_bucket="STRONG", volume_bucket="HIGH", outcome="SUCCESS", count=20)
    _add_snapshot(session, sma_bucket="WEAK", volume_bucket="LOW", outcome="FAILURE", count=20)

    report = compute_setup_combination_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)

    assert report.verdict == REPORT_VERDICT_MEASURED
    strong = next(c for c in report.combinations if c["setup_signature"] == "STRONG_HIGH")
    weak = next(c for c in report.combinations if c["setup_signature"] == "WEAK_LOW")
    assert strong["association"] == ASSOCIATION_SUCCESS
    assert weak["association"] == ASSOCIATION_FAILURE


def test_insufficient_sample_combination_marked_within_measured_report(session):
    _add_snapshot(session, sma_bucket="STRONG", volume_bucket="HIGH", outcome="SUCCESS", count=20)
    _add_snapshot(session, sma_bucket="MODERATE", volume_bucket="NORMAL", outcome="SUCCESS", count=5)

    report = compute_setup_combination_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)

    sparse = next(c for c in report.combinations if c["setup_signature"] == "MODERATE_NORMAL")
    assert sparse["association"] == ASSOCIATION_INSUFFICIENT_SAMPLE
    assert sparse["success_rate"] is None


def test_multiplicity_correction_requires_larger_delta_with_more_qualifying_combinations(session):
    # Two combinations, each with a moderate but real edge over baseline.
    _add_snapshot(session, sma_bucket="STRONG", volume_bucket="HIGH", horizon_days=1, outcome="SUCCESS", count=13)
    _add_snapshot(session, sma_bucket="STRONG", volume_bucket="HIGH", horizon_days=1, outcome="FAILURE", count=7)
    _add_snapshot(session, sma_bucket="MODERATE", volume_bucket="NORMAL", horizon_days=3, outcome="SUCCESS", count=12)
    _add_snapshot(session, sma_bucket="MODERATE", volume_bucket="NORMAL", horizon_days=3, outcome="FAILURE", count=8)
    _add_snapshot(session, sma_bucket="WEAK", volume_bucket="LOW", horizon_days=5, outcome="FAILURE", count=20)

    report = compute_setup_combination_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)

    # baseline = (13+12)/60 = 0.4167ish; both moderate-edge combos (0.65, 0.60)
    # should NOT clear a 2x-scaled margin even though they'd individually clear 1x.
    assert report.multiplicity_trial_count == 3
    assert report.adjusted_margin == Decimal("0.30")
    strong = next(c for c in report.combinations if c["setup_signature"] == "STRONG_HIGH")
    moderate = next(c for c in report.combinations if c["setup_signature"] == "MODERATE_NORMAL")
    assert strong["association"] == ASSOCIATION_NONE
    assert moderate["association"] == ASSOCIATION_NONE


def test_history_accumulates_reports(session):
    _add_snapshot(session, sma_bucket="STRONG", volume_bucket="HIGH", outcome="SUCCESS", count=20)

    compute_setup_combination_report(session, model_version=MODEL_VERSION, computed_at=AS_OF)
    compute_setup_combination_report(session, model_version=MODEL_VERSION, computed_at=AS_OF + timedelta(days=1))

    assert len(get_setup_combination_history(session, MODEL_VERSION)) == 2
