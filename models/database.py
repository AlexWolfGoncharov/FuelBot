"""
Database models for the Fuel Tracker Bot
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Numeric, BigInteger, Text, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from config.settings import settings


def _create_async_engine():
    url = settings.database_url
    if url.startswith("sqlite"):
        return create_async_engine(url, echo=False, poolclass=NullPool)
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


class Base(DeclarativeBase):
    """Base class for all database models"""
    pass


class User(Base):
    """User model for storing Telegram users"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"


class Refuel(Base):
    """Refuel model for storing fuel refill records"""
    __tablename__ = "refuels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Refuel data (UAH)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    station_name: Mapped[str] = mapped_column(String(255), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    liters: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_per_liter: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # USD conversion
    usd_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    total_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    price_per_liter_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    # Odometer data
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_from_last: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    consumption: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    full_tank: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)  # Чи заправка до повного бака

    # Location data
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7), nullable=True)

    # File references
    receipt_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    odometer_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # AI confidence score
    ai_confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Refuel(id={self.id}, date={self.date}, liters={self.liters}, cost={self.total_cost})>"


class ChatHistory(Base):
    """Chat history for AI assistant conversations"""
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' or 'assistant'
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        return f"<ChatHistory(user_id={self.user_id}, role={self.role})>"


# Database engine and session
engine = _create_async_engine()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Initialize database and create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get a new database session"""
    async with async_session() as session:
        yield session
