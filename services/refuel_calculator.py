"""
Service for recalculating refuel statistics
"""
import logging
from decimal import Decimal
from sqlalchemy import select
from models.database import async_session, Refuel

logger = logging.getLogger(__name__)


async def recalculate_refuel_stats(user_id: int) -> int:
    """
    Recalculate distance_from_last and consumption for all refuels of a user.
    Processes refuels in chronological order (oldest first).

    Args:
        user_id: Telegram user ID

    Returns:
        Number of refuels updated
    """
    try:
        async with async_session() as session:
            # Get all user refuels ordered by date (oldest first)
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(Refuel.date.asc())
            )
            refuels = result.scalars().all()

            if not refuels:
                logger.info(f"No refuels found for user {user_id}")
                return 0

            logger.info(f"Recalculating stats for {len(refuels)} refuels for user {user_id}")

            # Track the last full tank refuel
            last_full_tank = None
            updated_count = 0

            for refuel in refuels:
                distance_from_last = None
                consumption = None

                # Calculate distance from last full tank
                if last_full_tank:
                    distance = refuel.odometer - last_full_tank.odometer
                    if distance > 0:
                        distance_from_last = distance

                        # Calculate consumption ONLY if current refuel is also full tank
                        if refuel.full_tank and distance_from_last > 0:
                            consumption = (refuel.liters / Decimal(str(distance_from_last))) * 100
                            logger.debug(
                                f"Refuel {refuel.id}: distance={distance_from_last}km, "
                                f"consumption={consumption:.2f}L/100km"
                            )

                # Update refuel if values changed
                if (refuel.distance_from_last != distance_from_last or
                    refuel.consumption != consumption):
                    refuel.distance_from_last = distance_from_last
                    refuel.consumption = consumption
                    updated_count += 1

                # Update last full tank reference
                if refuel.full_tank:
                    last_full_tank = refuel

            # Commit all changes
            await session.commit()

            logger.info(
                f"Recalculation complete for user {user_id}: "
                f"{updated_count} refuels updated out of {len(refuels)} total"
            )

            return updated_count

    except Exception as e:
        logger.error(f"Error recalculating refuel stats for user {user_id}: {e}", exc_info=True)
        raise
