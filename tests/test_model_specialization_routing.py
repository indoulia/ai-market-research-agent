from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.model_specialization_routing import (
    DIMENSION_HORIZON,
    DIMENSION_REGIME,
    DIMENSION_SECTOR,
    DIMENSION_SETUP,
    SEGMENT_VERDICT_INSUFFICIENT_SAMPLE,
    SPECIALIZATION_ROUTING_VERSION,
    VERDICT_ROUTE_TO_SPECIALIZED,
    VERDICT_USE_GLOBAL_FALLBACK,
    evaluate_specialization_candidate,
    get_specialization_routing_history,
)
from app.models import Prediction, PredictionAttributionSnapshot, Stock
from app.out_of_sample_validation import EvaluationWindow

SPECIALIZED_MODEL = "specialized-v1"
GLOBAL_MODEL = "global-v1"
BASE_TIME = datetime(2027, 1, 1, tzinfo=timezone.utc)
BASELINE_WINDOW = EvaluationWindow(label="baseline", start=BASE_TIME, end=BASE_TIME + timedelta(days=30))
CONFIRMATION_WINDOW = EvaluationWindow(label="confirmation", start=BASE_TIME + timedelta(days=31), end=BASE_TIME + timedelta(days=60))
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


def _add_snapshots(session, *, model_version, window, count, outcome, horizon_days=5, regime="BULLISH_LOW_VOL", sma_bucket="STRONG", volume_bucket="HIGH", sector="TECH"):
    mid = window.start + (window.end - window.start) / 2
    for _ in range(count):
        n = next(_counter)
        stock = Stock(symbol=f"S{n}", exchange="NSE", sector=sector, is_active=True)
        session.add(stock)
        session.flush()
        prediction = Prediction(
            stock_id=stock.id, as_of_timestamp=mid, entry_price=Decimal("100"), horizon_days=horizon_days,
            target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
            confidence=Decimal("0.8"), model_version=model_version, feature_version="FV-001",
            consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
            opportunity_score=Decimal("60.00"),
        )
        session.add(prediction)
        session.flush()
        session.add(PredictionAttributionSnapshot(
            prediction_id=prediction.id, model_version=model_version, horizon_days=horizon_days, regime=regime,
            sma20_distance_bucket=sma_bucket, volume_ratio_bucket=volume_bucket, evidence_categories_available=[],
            outcome=outcome, snapshotted_at=mid, attribution_rule_version="ATB-001",
        ))
    session.commit()


def test_route_to_specialized_when_both_windows_validate(session):
    for window in (BASELINE_WINDOW, CONFIRMATION_WINDOW):
        _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=window, count=20, outcome="SUCCESS", horizon_days=5)
        _add_snapshots(session, model_version=GLOBAL_MODEL, window=window, count=20, outcome="FAILURE", horizon_days=5)

    decision = evaluate_specialization_candidate(
        session, dimension=DIMENSION_HORIZON, segment_key="5", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )

    assert decision.routing_verdict == VERDICT_ROUTE_TO_SPECIALIZED
    assert decision.routing_rule_version == SPECIALIZATION_ROUTING_VERSION


def test_global_fallback_when_confirmation_window_does_not_replicate(session):
    _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=BASELINE_WINDOW, count=20, outcome="SUCCESS", horizon_days=5)
    _add_snapshots(session, model_version=GLOBAL_MODEL, window=BASELINE_WINDOW, count=20, outcome="FAILURE", horizon_days=5)
    # Confirmation window: specialized no longer outperforms.
    _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=CONFIRMATION_WINDOW, count=20, outcome="FAILURE", horizon_days=5)
    _add_snapshots(session, model_version=GLOBAL_MODEL, window=CONFIRMATION_WINDOW, count=20, outcome="SUCCESS", horizon_days=5)

    decision = evaluate_specialization_candidate(
        session, dimension=DIMENSION_HORIZON, segment_key="5", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )

    assert decision.routing_verdict == VERDICT_USE_GLOBAL_FALLBACK
    assert decision.confirmation_verdict != "VALIDATED"


def test_global_fallback_when_insufficient_sample(session):
    decision = evaluate_specialization_candidate(
        session, dimension=DIMENSION_HORIZON, segment_key="5", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )

    assert decision.routing_verdict == VERDICT_USE_GLOBAL_FALLBACK
    assert decision.baseline_verdict == SEGMENT_VERDICT_INSUFFICIENT_SAMPLE


def test_multiplicity_correction_demotes_moderate_edge(session):
    for window in (BASELINE_WINDOW, CONFIRMATION_WINDOW):
        # Specialized: 13/20 success (0.65); global: 7/20 (0.35) -- delta ~0.30, would clear a 1x margin but not a 5x one.
        _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=window, count=13, outcome="SUCCESS", horizon_days=3)
        _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=window, count=7, outcome="FAILURE", horizon_days=3)
        _add_snapshots(session, model_version=GLOBAL_MODEL, window=window, count=7, outcome="SUCCESS", horizon_days=3)
        _add_snapshots(session, model_version=GLOBAL_MODEL, window=window, count=13, outcome="FAILURE", horizon_days=3)

    lenient = evaluate_specialization_candidate(
        session, dimension=DIMENSION_HORIZON, segment_key="3", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )
    strict = evaluate_specialization_candidate(
        session, dimension=DIMENSION_HORIZON, segment_key="3", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=5, computed_at=BASE_TIME + timedelta(seconds=1),
    )

    assert lenient.routing_verdict == VERDICT_ROUTE_TO_SPECIALIZED
    assert strict.routing_verdict == VERDICT_USE_GLOBAL_FALLBACK
    assert strict.adjusted_margin == Decimal("0.50")


def test_sector_dimension(session):
    for window in (BASELINE_WINDOW, CONFIRMATION_WINDOW):
        _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=window, count=20, outcome="SUCCESS", sector="PHARMA")
        _add_snapshots(session, model_version=GLOBAL_MODEL, window=window, count=20, outcome="FAILURE", sector="PHARMA")

    decision = evaluate_specialization_candidate(
        session, dimension=DIMENSION_SECTOR, segment_key="PHARMA", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )

    assert decision.routing_verdict == VERDICT_ROUTE_TO_SPECIALIZED


def test_setup_dimension(session):
    for window in (BASELINE_WINDOW, CONFIRMATION_WINDOW):
        _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=window, count=20, outcome="SUCCESS", sma_bucket="WEAK", volume_bucket="LOW")
        _add_snapshots(session, model_version=GLOBAL_MODEL, window=window, count=20, outcome="FAILURE", sma_bucket="WEAK", volume_bucket="LOW")

    decision = evaluate_specialization_candidate(
        session, dimension=DIMENSION_SETUP, segment_key="WEAK_LOW", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )

    assert decision.routing_verdict == VERDICT_ROUTE_TO_SPECIALIZED


def test_regime_dimension(session):
    for window in (BASELINE_WINDOW, CONFIRMATION_WINDOW):
        _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=window, count=20, outcome="SUCCESS", regime="BEARISH_HIGH_VOL")
        _add_snapshots(session, model_version=GLOBAL_MODEL, window=window, count=20, outcome="FAILURE", regime="BEARISH_HIGH_VOL")

    decision = evaluate_specialization_candidate(
        session, dimension=DIMENSION_REGIME, segment_key="BEARISH_HIGH_VOL", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )

    assert decision.routing_verdict == VERDICT_ROUTE_TO_SPECIALIZED


def test_idempotent(session):
    for window in (BASELINE_WINDOW, CONFIRMATION_WINDOW):
        _add_snapshots(session, model_version=SPECIALIZED_MODEL, window=window, count=20, outcome="SUCCESS", horizon_days=5)
        _add_snapshots(session, model_version=GLOBAL_MODEL, window=window, count=20, outcome="FAILURE", horizon_days=5)

    first = evaluate_specialization_candidate(
        session, dimension=DIMENSION_HORIZON, segment_key="5", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )
    second = evaluate_specialization_candidate(
        session, dimension=DIMENSION_HORIZON, segment_key="5", specialized_model_version=SPECIALIZED_MODEL,
        global_model_version=GLOBAL_MODEL, baseline_window=BASELINE_WINDOW, confirmation_window=CONFIRMATION_WINDOW,
        candidate_count=1, computed_at=BASE_TIME,
    )

    assert first.id == second.id
    assert len(get_specialization_routing_history(session, dimension=DIMENSION_HORIZON, segment_key="5")) == 1
