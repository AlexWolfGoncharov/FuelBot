#!/usr/bin/env python3
"""
Create or update a users row so refuels.user_id (e.g. 1) matches your Telegram account.

When refuels point to user_id=1 but no users.id=1 exists, run:

  export POSTGRES_URL='postgresql://...'
  python scripts/fix_user_row_for_refuels.py --user-id 1 --telegram-id 123456789

Use your real Telegram numeric id (same as in ALLOWED_USER_IDS).
"""
from __future__ import annotations

import argparse
from typing import Optional
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.db_url import normalize_database_url_for_async
from models.database import Base, User


async def fix(
    postgres_url: str,
    *,
    user_id: int,
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
) -> None:
    pg_url = normalize_database_url_for_async(postgres_url)
    engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        by_id = await session.get(User, user_id)
        by_tg = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()

        if by_tg is not None and by_tg.id != user_id:
            print(
                f"Error: telegram_id {telegram_id} already belongs to users.id={by_tg.id}. "
                f"Remove or merge that row first, or use a different telegram account.",
                file=sys.stderr,
            )
            sys.exit(1)

        if by_id is not None:
            by_id.telegram_id = telegram_id
            by_id.username = username
            by_id.first_name = first_name
            print(f"Updated users.id={user_id} → telegram_id={telegram_id}")
        else:
            session.add(
                User(
                    id=user_id,
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                )
            )
            print(f"Inserted users.id={user_id}, telegram_id={telegram_id}")

        await session.commit()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('users', 'id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM users))"
            )
        )

    await engine.dispose()
    print("Done. Sequence users_id_seq adjusted.")


def main() -> None:
    p = argparse.ArgumentParser(description="Fix missing User row for refuels.user_id")
    p.add_argument("--user-id", type=int, required=True, help="users.id used in refuels (e.g. 1)")
    p.add_argument("--telegram-id", type=int, required=True, help="Your Telegram user id")
    p.add_argument("--username", default=None)
    p.add_argument("--first-name", default=None)
    p.add_argument(
        "--postgres-url",
        default=os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL"),
    )
    args = p.parse_args()
    if not args.postgres_url or "sqlite" in args.postgres_url:
        print("Set POSTGRES_URL or DATABASE_URL to PostgreSQL.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(
        fix(
            args.postgres_url,
            user_id=args.user_id,
            telegram_id=args.telegram_id,
            username=args.username,
            first_name=args.first_name,
        )
    )


if __name__ == "__main__":
    main()
