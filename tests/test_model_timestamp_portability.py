"""EPIC-M1.4-SUB-03: verify model timestamp defaults are dialect-portable.

`server_default="now()"` (a plain Python string) is stored as a literal SQL default
clause verbatim, not evaluated per-dialect: PostgreSQL happens to accept `now()` as a
function call, but SQLite stores the literal text "now()" as the column's value, which
later fails to parse as a datetime. `sa.func.now()` compiles correctly per dialect
(`now()` on PostgreSQL, `CURRENT_TIMESTAMP` on SQLite) and is what these tests verify.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from app.db import Base
from app.models import DatasetValidationRun, ModelVersion, Prediction, Stock

TIMESTAMPED_MODELS = (Stock, DatasetValidationRun, Prediction, ModelVersion)


@pytest.mark.parametrize("model", TIMESTAMPED_MODELS, ids=lambda m: m.__name__)
def test_created_at_default_compiles_to_current_timestamp_on_sqlite(model):
    ddl = str(CreateTable(model.__table__).compile(dialect=sqlite.dialect()))
    assert "CURRENT_TIMESTAMP" in ddl
    assert "now()" not in ddl.lower()


@pytest.mark.parametrize("model", TIMESTAMPED_MODELS, ids=lambda m: m.__name__)
def test_created_at_default_compiles_to_now_on_postgresql(model):
    ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
    assert "now()" in ddl.lower()


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


def test_stock_gets_a_real_datetime_default_on_sqlite(session):
    stock = Stock(symbol="TESTPORT", exchange="NSE")
    session.add(stock)
    session.flush()

    assert isinstance(stock.created_at, datetime)
    assert isinstance(stock.updated_at, datetime)


def test_prediction_gets_a_real_datetime_default_on_sqlite(session):
    stock = Stock(symbol="TESTPORT2", exchange="NSE")
    session.add(stock)
    session.flush()

    prediction = Prediction(
        stock_id=stock.id,
        as_of_timestamp=datetime(2026, 8, 1),
        entry_price=100,
        horizon_days=5,
        target_return="0.05",
        stop_return="-0.03",
        predicted_probability="0.7",
        confidence="0.8",
        model_version="m1-baseline-1",
        feature_version="f1",
    )
    session.add(prediction)
    session.flush()

    assert isinstance(prediction.created_at, datetime)
