from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.continuous_discovery import record_discovery_for_scan, run_scheduled_discovery_scan
from app.db import Base
from app.discovery import SOURCE_DAILY_UNIVERSE_SCAN
from app.market_data.quality import NSE_TIMEZONE
from app.models import DiscoveryRecord, MarketPrice, Prediction, RecommendationGeneration, Stock
from app.recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED
from app.scan import CandidateSignals, run_daily_candidate_scan

SCAN_DATE = date(2026, 8, 20)
AS_OF = datetime(2026, 8, 20, tzinfo=timezone.utc)


class StubSignalProvider:
    model_version = "test-model-1"

    def __init__(self, predicted_probability=Decimal("0.65"), confidence=Decimal("0.70")):
        self._predicted_probability = predicted_probability
        self._confidence = confidence

    def predict(self, stock_id, features):
        return CandidateSignals(predicted_probability=self._predicted_probability, confidence=self._confidence)


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


def _make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_rising_price_history(session, stock_id, last_session=SCAN_DATE, count=25, base_price=Decimal("100")):
    for offset in range(count):
        session_date = last_session - timedelta(days=count - 1 - offset)
        timestamp = datetime.combine(session_date, time.min, NSE_TIMEZONE)
        price = base_price + Decimal(offset)
        session.add(
            MarketPrice(
                stock_id=stock_id,
                timestamp=timestamp,
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                volume=10_000,
                source="test",
            )
        )
    session.flush()


def _run_kwargs(signal_provider=None, **overrides):
    kwargs = dict(
        scan_date=SCAN_DATE,
        signal_provider=signal_provider or StubSignalProvider(),
        as_of_timestamp=AS_OF,
        entry_price_for=lambda stock_id: Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        # real technical features off this fixture's price history don't reliably
        # clear the production score floor -- these tests care about routing/
        # idempotency, not the M1.9 score itself, so admit every qualifying score.
        min_score=Decimal("0"),
    )
    kwargs.update(overrides)
    return kwargs


def test_scheduled_scan_routes_a_qualifying_candidate_through_generation_and_selection(session):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)

    result = run_scheduled_discovery_scan(session, **_run_kwargs())

    assert len(result.generations) == 1
    assert result.generations[0].outcome == OUTCOME_QUALIFIED
    assert result.generations[0].prediction_id is not None
    assert len(result.selections) == 1
    assert result.selections[0].selected is True
    discovery = next(d for d in result.discovery_records if d.stock_id == stock.id)
    assert discovery.source == SOURCE_DAILY_UNIVERSE_SCAN
    assert discovery.recommendation_generation_id is None  # discovery itself never links to the generation


def test_ineligible_candidate_gets_a_discovery_record_but_no_generation(session):
    _make_stock(session)  # no market data at all -> excluded as missing_market_data

    result = run_scheduled_discovery_scan(session, **_run_kwargs())

    assert len(result.discovery_records) == 1  # provenance recorded even for excluded candidates
    assert result.generations == ()
    assert session.query(RecommendationGeneration).count() == 0
    assert session.query(Prediction).count() == 0


def test_non_qualifying_candidate_is_preserved_as_backlog_not_deleted(session):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)
    low_probability_provider = StubSignalProvider(predicted_probability=Decimal("0.10"))

    result = run_scheduled_discovery_scan(session, **_run_kwargs(low_probability_provider))

    assert result.generations[0].outcome == OUTCOME_NOT_QUALIFIED
    assert result.generations[0].prediction_id is None
    assert session.query(RecommendationGeneration).count() == 1  # preserved, not deleted
    assert session.query(Prediction).count() == 0


def test_discovery_recording_alone_never_creates_a_recommendation(session):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)
    summary = run_daily_candidate_scan(session, SCAN_DATE, StubSignalProvider())

    records = record_discovery_for_scan(session, summary.scan, AS_OF)

    assert len(records) == 1
    assert session.query(RecommendationGeneration).count() == 0
    assert session.query(Prediction).count() == 0


def test_rerunning_the_same_scheduled_scan_is_fully_idempotent(session):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)

    first = run_scheduled_discovery_scan(session, **_run_kwargs())
    second = run_scheduled_discovery_scan(session, **_run_kwargs())

    assert first.scan.id == second.scan.id
    assert [g.id for g in first.generations] == [g.id for g in second.generations]
    assert [s.id for s in first.selections] == [s.id for s in second.selections]
    assert session.query(DiscoveryRecord).count() == 1
    assert session.query(RecommendationGeneration).count() == 1
    assert session.query(Prediction).count() == 1
