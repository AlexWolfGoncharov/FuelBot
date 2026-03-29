"""
User helper utilities
"""
import logging
from typing import Optional

from sqlalchemy import select

from models.database import async_session, User

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
