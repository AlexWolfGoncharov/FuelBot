#!/usr/bin/env python3
"""
Copy FuelBot data from a local SQLite file into PostgreSQL (e.g. Railway Postgres).

Usage:
  export DATABASE_URL='postgresql://...'   # target Postgres (Railway copies this to clipboard)
  python scripts/migrate_sqlite_to_postgres.py --sqlite data/fuel_tracker.db

  # Wipe target tables and re-import:
  python scripts/migrate_sqlite_to_postgres.py --sqlite data/fuel_tracker.db --truncate
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Project root on PYTHONPATH
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config.db_url import normalize_database_url_for_async
from models.database import Base, ChatHistory, Refuel, User


def _sqlite_url_from_path(path: str) -> str:
    path = os.path.abspath(path).replace("\\", "/")
    return "sqlite+aiosqlite:///" + path


async def _sqlite_counts(session: AsyncSession) -> tuple[int, int, int]:
    nu = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    nr = (await session.execute(select(func.count()).select_from(Refuel))).scalar_one()
    try:
        nc = (await session.execute(select(func.count()).select_from(ChatHistory))).scalar_one()
    except Exception:
        nc = 0
    return int(nu), int(nr), int(nc)


async def _pg_counts(session: AsyncSession) -> tuple[int, int, int]:
    nu = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    nr = (await session.execute(select(func.count()).select_from(Refuel))).scalar_one()
    nc = (await session.execute(select(func.count()).select_from(ChatHistory))).scalar_one()
    return int(nu), int(nr), int(nc)


async def migrate(sqlite_path: str, postgres_url: str, *, truncate: bool) -> None:
    sqlite_url = _sqlite_url_from_path(sqlite_path)
    pg_url = normalize_database_url_for_async(postgres_url)

    sqlite_engine = create_async_engine(sqlite_url, echo=False, poolclass=NullPool)
    pg_engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)

    SessionSQLite = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionSQLite() as s0:
        su, sr, sc = await _sqlite_counts(s0)
    print(f"SQLite ({sqlite_path}): users={su}, refuels={sr}, chat_history={sc}")

    async with pg_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if truncate:
            await conn.execute(
                text(
                    "TRUNCATE TABLE chat_history, refuels, users RESTART IDENTITY CASCADE"
                )
            )

    SessionPg = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionSQLite() as src, SessionPg() as dst:
        users = (await src.execute(select(User))).scalars().all()
        for u in users:
            dst.add(
                User(
                    id=u.id,
                    telegram_id=u.telegram_id,
                    username=u.username,
                    first_name=u.first_name,
                    created_at=u.created_at,
                )
            )
        await dst.flush()

        refuels = (await src.execute(select(Refuel))).scalars().all()
        for r in refuels:
            dst.add(
                Refuel(
                    id=r.id,
                    user_id=r.user_id,
                    date=r.date,
                    station_name=r.station_name,
                    fuel_type=r.fuel_type,
                    liters=r.liters,
                    price_per_liter=r.price_per_liter,
                    total_cost=r.total_cost,
                    usd_rate=r.usd_rate,
                    total_cost_usd=r.total_cost_usd,
                    price_per_liter_usd=r.price_per_liter_usd,
                    odometer=r.odometer,
                    distance_from_last=r.distance_from_last,
                    consumption=r.consumption,
                    full_tank=r.full_tank,
                    latitude=r.latitude,
                    longitude=r.longitude,
                    receipt_file_id=r.receipt_file_id,
                    odometer_file_id=r.odometer_file_id,
                    ai_confidence=r.ai_confidence,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
            )
        await dst.flush()

        chats = (await src.execute(select(ChatHistory))).scalars().all()
        for c in chats:
            dst.add(
                ChatHistory(
                    id=c.id,
                    user_id=c.user_id,
                    role=c.role,
                    message=c.message,
                    created_at=c.created_at,
                )
            )
        await dst.commit()

    async with pg_engine.begin() as conn:
        for table in ("users", "refuels", "chat_history"):
            await conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
                )
            )

    async with SessionPg() as verify:
        pu, pr, pc = await _pg_counts(verify)
    print(f"PostgreSQL: users={pu}, refuels={pr}, chat_history={pc}")
    if (pu, pr, pc) != (su, sr, sc):
        print(
            "Warning: row counts differ from SQLite — check for an earlier partial import or duplicate telegram_id.",
            file=sys.stderr,
        )

    await sqlite_engine.dispose()
    await pg_engine.dispose()
    print("Done: SQLite → PostgreSQL migration finished.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate FuelBot SQLite DB to PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default=os.environ.get("SQLITE_PATH", "data/fuel_tracker.db"),
        help="Path to fuel_tracker.db (default: data/fuel_tracker.db or SQLITE_PATH)",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.environ.get("POSTGRES_URL")
        or os.environ.get("RAILWAY_DATABASE_URL")
        or os.environ.get("DATABASE_URL"),
        help="Target Postgres URL (prefer POSTGRES_URL if DATABASE_URL is local SQLite)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate target tables before import (destructive)",
    )
    args = parser.parse_args()
    if not args.postgres_url or "sqlite" in args.postgres_url:
        print(
            "Error: need PostgreSQL URL. Set POSTGRES_URL (recommended) or pass --postgres-url. "
            "If DATABASE_URL in .env is SQLite for Docker, add POSTGRES_URL=postgresql://... for migration.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not os.path.isfile(args.sqlite):
        print(f"Error: SQLite file not found: {args.sqlite}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(migrate(args.sqlite, args.postgres_url, truncate=args.truncate))


if __name__ == "__main__":
    main()
