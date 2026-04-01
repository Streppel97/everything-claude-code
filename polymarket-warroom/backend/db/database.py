"""Database connection and table definitions using SQLAlchemy async."""

import logging
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class MarketRow(Base):
    __tablename__ = "markets"

    id = Column(String, primary_key=True)
    question = Column(Text, nullable=False)
    category = Column(String, default="")
    outcome_yes_price = Column(Float, default=0.5)
    outcome_no_price = Column(Float, default=0.5)
    volume_24h = Column(Float, default=0.0)
    liquidity = Column(Float, default=0.0)
    spread = Column(Float, default=0.0)
    resolution_date = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)
    condition_id = Column(String, default="")
    slug = Column(String, default="")
    active = Column(Boolean, default=True)


class SignalRow(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    confidence = Column(Float, default=0.0)
    strategy = Column(String, default="")
    entry_price = Column(Float, default=0.0)
    target_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    expected_value = Column(Float, default=0.0)
    reasoning = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    acted_on = Column(Boolean, default=False)


class TradeRow(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, nullable=False)
    question = Column(Text, default="")
    direction = Column(String, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    position_size = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    status = Column(String, default="OPEN")
    mode = Column(String, default="PAPER")
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    strategy = Column(String, default="")
    stop_loss = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)


class PortfolioSnapshotRow(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    total_value = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    positions_value = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class PriceHistoryRow(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, nullable=False)
    price_yes = Column(Float, nullable=False)
    price_no = Column(Float, nullable=False)
    volume = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Enable WAL mode for SQLite
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with async_session() as session:
        yield session
