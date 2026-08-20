from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.market_regime import (
    REGIME_RULE_VERSION,
    InsufficientRegimeEvidenceError,
    classify_market_regime,
)
from app.models import DailyCandidateScan, MarketRegime, ScanCandidate, Stock


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


def _make_scan(session):
    scan = DailyCandidateScan(scan_date=date(2026, 8, 21), universe_version="DCS-001", eligible_count=0, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_candidate(session, scan, symbol, *, sma20_distance, atr_percent, eligible=True):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=eligible,
        exclusion_reason=None if eligible else "missing_market_data",
        sma20_distance=sma20_distance,
        atr_percent=atr_percent,
        data_quality_passed=eligible,
    )
    session.add(candidate)
    session.flush()
    return candidate


def test_no_eligible_candidates_raises(session):
    scan = _make_scan(session)

    with pytest.raises(InsufficientRegimeEvidenceError):
        classify_market_regime(session, scan.id)


def test_ineligible_candidates_are_excluded_from_breadth(session):
    scan = _make_scan(session)
    _make_candidate(session, scan, "EXCLUDED", sma20_distance=Decimal("0.05"), atr_percent=Decimal("0.01"), eligible=False)

    with pytest.raises(InsufficientRegimeEvidenceError):
        classify_market_regime(session, scan.id)


def test_bullish_low_vol_regime(session):
    scan = _make_scan(session)
    for i in range(6):
        _make_candidate(session, scan, f"UP{i}", sma20_distance=Decimal("0.02"), atr_percent=Decimal("0.01"))
    for i in range(4):
        _make_candidate(session, scan, f"DOWN{i}", sma20_distance=Decimal("-0.02"), atr_percent=Decimal("0.01"))

    regime = classify_market_regime(session, scan.id)

    assert regime.breadth_positive_ratio == Decimal("0.6")
    assert regime.average_atr_percent == Decimal("0.01")
    assert regime.regime == "BULLISH_LOW_VOL"
    assert regime.regime_rule_version == REGIME_RULE_VERSION
    assert regime.eligible_count == 10


def test_bearish_high_vol_regime(session):
    scan = _make_scan(session)
    for i in range(4):
        _make_candidate(session, scan, f"UP{i}", sma20_distance=Decimal("0.02"), atr_percent=Decimal("0.05"))
    for i in range(6):
        _make_candidate(session, scan, f"DOWN{i}", sma20_distance=Decimal("-0.02"), atr_percent=Decimal("0.05"))

    regime = classify_market_regime(session, scan.id)

    assert regime.breadth_positive_ratio == Decimal("0.4")
    assert regime.regime == "BEARISH_HIGH_VOL"


def test_neutral_regime_between_thresholds(session):
    scan = _make_scan(session)
    for i in range(5):
        _make_candidate(session, scan, f"UP{i}", sma20_distance=Decimal("0.02"), atr_percent=Decimal("0.01"))
    for i in range(5):
        _make_candidate(session, scan, f"DOWN{i}", sma20_distance=Decimal("-0.02"), atr_percent=Decimal("0.01"))

    regime = classify_market_regime(session, scan.id)

    assert regime.breadth_positive_ratio == Decimal("0.5")
    assert regime.regime == "NEUTRAL_LOW_VOL"


def test_missing_atr_data_omits_volatility_suffix(session):
    scan = _make_scan(session)
    for i in range(6):
        _make_candidate(session, scan, f"UP{i}", sma20_distance=Decimal("0.02"), atr_percent=None)
    for i in range(4):
        _make_candidate(session, scan, f"DOWN{i}", sma20_distance=Decimal("-0.02"), atr_percent=None)

    regime = classify_market_regime(session, scan.id)

    assert regime.average_atr_percent is None
    assert regime.regime == "BULLISH"


def test_reclassifying_the_same_scan_is_idempotent(session):
    scan = _make_scan(session)
    for i in range(6):
        _make_candidate(session, scan, f"UP{i}", sma20_distance=Decimal("0.02"), atr_percent=Decimal("0.01"))
    for i in range(4):
        _make_candidate(session, scan, f"DOWN{i}", sma20_distance=Decimal("-0.02"), atr_percent=Decimal("0.01"))

    first = classify_market_regime(session, scan.id)
    # add more candidates after the first classification -- must not shift the historical record
    _make_candidate(session, scan, "NEWDOWN", sma20_distance=Decimal("-0.05"), atr_percent=Decimal("0.09"))
    second = classify_market_regime(session, scan.id)

    assert first.id == second.id
    assert second.regime == "BULLISH_LOW_VOL"
    assert session.query(MarketRegime).count() == 1
