from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.services.context_summaries import latest_market_price_pair, latest_market_price_pairs
from app.db import Base
from app.models import MarketPrice, Stock

BASE_TS = datetime(2026, 8, 20, tzinfo=timezone.utc)


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


def _stock(session, symbol):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _price(session, stock_id, close, days_ago):
    session.add(
        MarketPrice(
            stock_id=stock_id,
            timestamp=BASE_TS - timedelta(days=days_ago),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000,
            source="test",
        )
    )


def test_batched_lookup_matches_per_stock_lookup_across_edge_cases(session):
    two_prices = _stock(session, "TWOPRC")
    _price(session, two_prices.id, Decimal("110"), days_ago=0)
    _price(session, two_prices.id, Decimal("100"), days_ago=1)

    one_price = _stock(session, "ONEPRC")
    _price(session, one_price.id, Decimal("50"), days_ago=0)

    zero_prior = _stock(session, "ZEROPRC")
    _price(session, zero_prior.id, Decimal("10"), days_ago=0)
    _price(session, zero_prior.id, Decimal("0"), days_ago=1)

    no_price = _stock(session, "NOPRICE")
    session.flush()

    stock_ids = [two_prices.id, one_price.id, zero_prior.id, no_price.id]
    batched = latest_market_price_pairs(session, stock_ids)

    for stock_id in stock_ids:
        assert batched[stock_id] == latest_market_price_pair(session, stock_id)

    assert batched[two_prices.id] == (Decimal("110"), Decimal("10"))
    assert batched[one_price.id] == (Decimal("50"), None)
    assert batched[zero_prior.id] == (Decimal("10"), None)
    assert batched[no_price.id] == (None, None)


def test_batched_lookup_with_no_stock_ids_returns_empty_dict(session):
    assert latest_market_price_pairs(session, []) == {}
