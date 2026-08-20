"""EPIC-M1.4-SUB-02: verify a genuinely fresh PostgreSQL database can reach the
current Alembic head via a real `alembic upgrade head`, with no manual stamping past
`0003_market_price_dedupe` (which previously duplicated 0001's unique constraint under
`create_index` and always failed on a fresh database). These tests need a real
PostgreSQL connection and are skipped when one isn't reachable -- e.g. in CI, which
does not provision Postgres.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import MarketPrice, Stock
from app.settings import settings

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture
def admin_dsn():
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    try:
        conn = psycopg.connect(dsn, autocommit=True, connect_timeout=3)
        conn.close()
    except Exception:
        pytest.skip("PostgreSQL is not reachable; skipping fresh-database migration tests")
        return
    return dsn


def _create_scratch_db(admin_dsn: str) -> tuple[str, str]:
    db_name = f"market_agent_sub02_{uuid.uuid4().hex[:8]}"
    conn = psycopg.connect(admin_dsn, autocommit=True, connect_timeout=3)
    conn.cursor().execute(f"CREATE DATABASE {db_name}")
    conn.close()
    return db_name, re.sub(r"/[^/]+$", f"/{db_name}", settings.database_url)


def _drop_scratch_db(admin_dsn: str, db_name: str) -> None:
    conn = psycopg.connect(admin_dsn, autocommit=True, connect_timeout=3)
    conn.cursor().execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
    conn.close()


def test_fresh_database_upgrades_to_head_without_stamping(admin_dsn):
    db_name, scratch_url = _create_scratch_db(admin_dsn)
    original_url = settings.database_url
    settings.database_url = scratch_url
    try:
        cfg = Config(str(ALEMBIC_INI))
        # No `command.stamp(...)` workaround: this is the fix under test.
        command.upgrade(cfg, "head")

        engine = create_engine(scratch_url)
        with engine.connect() as conn:
            current_head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        engine.dispose()
        assert current_head == "0007_outcome_actual_return"
    finally:
        settings.database_url = original_url
        _drop_scratch_db(admin_dsn, db_name)


def test_market_prices_uniqueness_is_still_enforced_after_fix(admin_dsn):
    db_name, scratch_url = _create_scratch_db(admin_dsn)
    original_url = settings.database_url
    settings.database_url = scratch_url
    try:
        cfg = Config(str(ALEMBIC_INI))
        command.upgrade(cfg, "head")

        engine = create_engine(scratch_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            now = datetime(2026, 8, 1, tzinfo=timezone.utc)
            stock = Stock(symbol="DEDUPE", exchange="NSE", is_active=True, created_at=now, updated_at=now)
            session.add(stock)
            session.flush()
            ts = now + timedelta(days=1)
            session.add(MarketPrice(
                stock_id=stock.id, timestamp=ts, open=100, high=101, low=99, close=100,
                volume=1000, source="test",
            ))
            session.commit()

            session.add(MarketPrice(
                stock_id=stock.id, timestamp=ts, open=200, high=201, low=199, close=200,
                volume=2000, source="test",
            ))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        finally:
            session.close()
            engine.dispose()
    finally:
        settings.database_url = original_url
        _drop_scratch_db(admin_dsn, db_name)


def test_downgrade_then_upgrade_round_trip_is_clean(admin_dsn):
    db_name, scratch_url = _create_scratch_db(admin_dsn)
    original_url = settings.database_url
    settings.database_url = scratch_url
    try:
        cfg = Config(str(ALEMBIC_INI))
        command.upgrade(cfg, "head")

        # Round-trip through every revision boundary, including the fixed no-op 0003.
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

        engine = create_engine(scratch_url)
        with engine.connect() as conn:
            current_head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        engine.dispose()
        assert current_head == "0007_outcome_actual_return"
    finally:
        settings.database_url = original_url
        _drop_scratch_db(admin_dsn, db_name)
