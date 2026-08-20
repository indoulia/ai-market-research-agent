"""EPIC-M1.4-SUB-01: verify recommendation immutability is enforced at the database
boundary (a Postgres trigger), not solely by the app-level ORM event listener. These
tests need a real PostgreSQL connection (the trigger is Postgres-specific PL/pgSQL) and
are skipped when one isn't reachable -- e.g. in CI, which does not provision Postgres.
"""
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models import Prediction, Stock
from app.settings import settings

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture(scope="module")
def scratch_db_url():
    admin_dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    try:
        conn = psycopg.connect(admin_dsn, autocommit=True, connect_timeout=3)
    except Exception:
        pytest.skip("PostgreSQL is not reachable; skipping database-boundary integrity tests")
        return

    db_name = f"market_agent_sub01_{uuid.uuid4().hex[:8]}"
    conn.cursor().execute(f"CREATE DATABASE {db_name}")
    conn.close()
    scratch_url = re.sub(r"/[^/]+$", f"/{db_name}", settings.database_url)

    original_url = settings.database_url
    settings.database_url = scratch_url
    try:
        cfg = Config(str(ALEMBIC_INI))
        command.upgrade(cfg, "0002_upstox_instrument_key")
        command.stamp(cfg, "0003_market_price_dedupe")
        command.upgrade(cfg, "head")
    finally:
        settings.database_url = original_url

    yield scratch_url

    admin_conn = psycopg.connect(admin_dsn, autocommit=True, connect_timeout=3)
    admin_conn.cursor().execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
    admin_conn.close()


@pytest.fixture
def session(scratch_db_url):
    engine = create_engine(scratch_db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        engine.dispose()


def make_recommendation(session):
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    # each test commits for real against the shared scratch DB (no rollback isolation,
    # since we need the trigger's rejection to actually hit the database) -- a unique
    # symbol per call avoids colliding with rows other tests in this module committed.
    symbol = f"TEST{uuid.uuid4().hex[:8].upper()}"
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    rec = Prediction(
        stock_id=stock.id,
        created_at=now,
        as_of_timestamp=now,
        entry_price=Decimal("100"),
        horizon_days=5,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"),
        model_version="m1-baseline-1",
        feature_version="f1",
        consensus_contract_version="PCC-001",
        horizon_selection_version="PHS-001",
        status="OPEN",
    )
    session.add(rec)
    session.commit()
    return rec


def test_raw_sql_update_rejects_immutable_field_change(session):
    rec = make_recommendation(session)

    with pytest.raises(Exception, match="immutable fields cannot be modified"):
        session.execute(
            text("UPDATE predictions SET entry_price = :price WHERE id = :id"),
            {"price": Decimal("999"), "id": rec.id},
        )
        session.commit()
    session.rollback()

    session.refresh(rec)
    assert rec.entry_price == Decimal("100")


def test_bulk_orm_update_rejects_immutable_field_change(session):
    rec = make_recommendation(session)

    with pytest.raises(Exception, match="immutable fields cannot be modified"):
        session.query(Prediction).filter(Prediction.id == rec.id).update({"target_return": Decimal("0.99")})
        session.commit()
    session.rollback()

    session.refresh(rec)
    assert rec.target_return == Decimal("0.05")


def test_raw_sql_update_still_allows_status_change(session):
    rec = make_recommendation(session)

    session.execute(
        text("UPDATE predictions SET status = :status WHERE id = :id"),
        {"status": "EVALUATED", "id": rec.id},
    )
    session.commit()

    session.refresh(rec)
    assert rec.status == "EVALUATED"
