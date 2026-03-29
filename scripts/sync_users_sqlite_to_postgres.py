#!/usr/bin/env python3
"""
Copy only the `users` table from SQLite into PostgreSQL (e.g. repair Railway if users were missing).

Keeps the same user ids so refuels.user_id stays valid.

  export POSTGRES_URL='postgresql://...'
  python scripts/sync_users_sqlite_to_postgres.py --sqlite data/fuel_tracker.db
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config.db_url import normalize_database_url_for_async
from models.database import Base, User


def _sqlite_url_from_path(path: str) -> str:
    path = os.path.abspath(path).replace("\\", "/")
    return "sqlite+aiosqlite:///" + path


async def sync_users(sqlite_path: str, postgres_url: str) -> None:
    sqlite_url = _sqlite_url_from_path(sqlite_path)
    pg_url = normalize_database_url_for_async(postgres_url)

    sqlite_engine = create_async_engine(sqlite_url, echo=False, poolclass=NullPool)
    pg_engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)

    async with pg_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionSQLite = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    SessionPg = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionSQLite() as src, SessionPg() as dst:
        from_sqlite = (await src.execute(select(User).order_by(User.id))).scalars().all()
        existing_ids = set(
            (await dst.execute(select(User.id))).scalars().all()
        )
        added = 0
        for u in from_sqlite:
            if u.id in existing_ids:
                continue
            dst.add(
                User(
                    id=u.id,
                    telegram_id=u.telegram_id,
                    username=u.username,
                    first_name=u.first_name,
                    created_at=u.created_at,
                )
            )
            added += 1
        await dst.commit()

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('users', 'id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM users))"
            )
        )

    await sqlite_engine.dispose()
    await pg_engine.dispose()
    print(
        f"Done: SQLite had {len(from_sqlite)} user(s); "
        f"inserted {added} missing row(s) into PostgreSQL."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync users table from SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default=os.environ.get("SQLITE_PATH", "data/fuel_tracker.db"),
        help="Path to SQLite DB with users",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL"),
        help="PostgreSQL URL",
    )
    args = parser.parse_args()
    if not args.postgres_url or "sqlite" in args.postgres_url:
        print("Set POSTGRES_URL or DATABASE_URL to PostgreSQL.", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.sqlite):
        print(f"SQLite file not found: {args.sqlite}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(sync_users(args.sqlite, args.postgres_url))


if __name__ == "__main__":
    main()
