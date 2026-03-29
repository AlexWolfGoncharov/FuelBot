"""
User helper utilities
"""
from sqlalchemy import select
from models.database import async_session, User


async def get_user_id_by_telegram_id(telegram_id: int) -> int:
    """
    Get internal user.id by telegram_id

    Args:
        telegram_id: Telegram user ID

    Returns:
        Internal database user.id
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one()
        return user.id
