"""
User helper utilities
"""
import logging
from typing import Optional

from sqlalchemy import func, select, update

from models.database import Refuel, User, async_session

logger = logging.getLogger(__name__)


async def get_user_id_by_telegram_id(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> int:
    """
    Internal users.id for this Telegram account. Creates User row if missing
    (e.g. user opened Statistics before ever saving a refuel).
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user.id
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("Created User row for telegram_id=%s internal_db_id=%s", telegram_id, user.id)
        return user.id


async def get_user_id_for_refuels(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> int:
    """
    Like get_user_id_by_telegram_id, but if refuels were migrated under another
    user_id (e.g. only user_id=1) while this Telegram account maps to users.id=2,
    reassign those refuels once (single-user / recovery after bad migration).
    """
    uid = await get_user_id_by_telegram_id(telegram_id, username, first_name)
    async with async_session() as session:
        mine = (
            await session.execute(
                select(func.count()).select_from(Refuel).where(Refuel.user_id == uid)
            )
        ).scalar_one()
        if mine > 0:
            return uid

        total = (
            await session.execute(select(func.count()).select_from(Refuel))
        ).scalar_one()
        if total == 0:
            return uid

        distinct_uids = (
            await session.execute(select(Refuel.user_id).distinct())
        ).scalars().all()

        if len(distinct_uids) == 1 and distinct_uids[0] != uid:
            old = distinct_uids[0]
            await session.execute(
                update(Refuel).where(Refuel.user_id == old).values(user_id=uid)
            )
            await session.commit()
            logger.warning(
                "Reassigned refuels from user_id=%s to user_id=%s (telegram_id=%s)",
                old,
                uid,
                telegram_id,
            )
            return uid

        for ouid in distinct_uids:
            if ouid == uid:
                continue
            row = await session.get(User, ouid)
            if row is None:
                await session.execute(
                    update(Refuel).where(Refuel.user_id == ouid).values(user_id=uid)
                )
                await session.commit()
                logger.warning(
                    "Reassigned orphan refuels user_id=%s -> %s (telegram_id=%s)",
                    ouid,
                    uid,
                    telegram_id,
                )
                break

    return uid
