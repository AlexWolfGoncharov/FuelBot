"""
Refuel validation logic
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import select, desc
from models.database import async_session, Refuel

logger = logging.getLogger(__name__)


async def validate_and_determine_full_tank(
    user_id: int,
    odometer: int,
    liters: float,
    refuel_date: datetime
) -> Tuple[bool, Optional[str]]:
    """
    Validate refuel data and determine if tank was full

    Args:
        user_id: User ID
        odometer: Current odometer reading
        liters: Liters refueled
        refuel_date: Date of refuel

    Returns:
        Tuple of (full_tank: bool, error_message: Optional[str])
        If error_message is not None, refuel should be rejected
    """

    async with async_session() as session:
        # Get last refuel by odometer
        result = await session.execute(
            select(Refuel)
            .where(Refuel.user_id == user_id)
            .where(Refuel.odometer < odometer)
            .order_by(desc(Refuel.odometer))
            .limit(1)
        )
        last_refuel = result.scalar_one_or_none()

        if not last_refuel:
            # First refuel - assume full tank
            logger.info(f"First refuel for user {user_id}, assuming full tank")
            return True, None

        # Validate odometer progression
        distance = odometer - last_refuel.odometer

        if distance <= 0:
            error_msg = (
                f"❌ <b>Помилка одометра</b>\n\n"
                f"Одометр не може зменшуватись!\n"
                f"Попередня заправка: {last_refuel.odometer} км\n"
                f"Поточна: {odometer} км\n\n"
                f"Перевірте фото одометра або введіть правильне значення."
            )
            logger.warning(f"Odometer validation failed: {odometer} <= {last_refuel.odometer}")
            return False, error_msg

        if distance > 2000:
            # Very large distance - warn but don't block
            logger.warning(
                f"Large distance detected: {distance}km between refuels "
                f"(last: {last_refuel.odometer}, current: {odometer})"
            )

        # Calculate consumption to determine full_tank
        consumption = (liters / distance) * 100  # л/100км

        # Typical diesel consumption: 6-10 л/100км
        # If consumption < 4 л/100км - physically impossible, tank was NOT full
        if consumption < 4.0:
            logger.info(
                f"Low consumption detected ({consumption:.2f} л/100км): "
                f"{liters}L for {distance}km - tank was not full"
            )
            return False, None  # Not full tank, but no error

        # Normal consumption - tank was full
        logger.info(
            f"Normal consumption ({consumption:.2f} л/100км): "
            f"{liters}L for {distance}km - full tank"
        )
        return True, None


async def estimate_refuel_date(
    user_id: int,
    odometer: int,
    recognized_date: Optional[datetime] = None,
    trusted_datetime: bool = False,
) -> datetime:
    """
    Estimate correct refuel date based on odometer if date is missing/incorrect

    Args:
        user_id: User ID
        odometer: Odometer reading
        recognized_date: Date from OCR (if available)
        trusted_datetime: If True, recognized_date comes from EXIF / Telegram message time —
            do not replace it with datetime.now() when odometer heuristics disagree.

    Returns:
        Estimated refuel date
    """
    if trusted_datetime and recognized_date is not None:
        logger.info(f"Keeping trusted capture/message datetime: {recognized_date}")
        return recognized_date

    async with async_session() as session:
        # Get refuel before and after this odometer
        result_before = await session.execute(
            select(Refuel)
            .where(Refuel.user_id == user_id)
            .where(Refuel.odometer < odometer)
            .order_by(desc(Refuel.odometer))
            .limit(1)
        )
        before = result_before.scalar_one_or_none()

        result_after = await session.execute(
            select(Refuel)
            .where(Refuel.user_id == user_id)
            .where(Refuel.odometer > odometer)
            .order_by(Refuel.odometer)
            .limit(1)
        )
        after = result_after.scalar_one_or_none()

        # If we have recognized_date and it's between before and after - use it
        if recognized_date:
            if before and after:
                if before.date <= recognized_date <= after.date:
                    logger.info(f"Using recognized date {recognized_date} (valid between refuels)")
                    return recognized_date
            elif before and not after:
                if recognized_date >= before.date:
                    logger.info(f"Using recognized date {recognized_date} (after last refuel)")
                    return recognized_date
            elif not before and after:
                if recognized_date <= after.date:
                    logger.info(f"Using recognized date {recognized_date} (before first refuel)")
                    return recognized_date

        # Estimate date based on odometer
        if before and after:
            # Interpolate between two refuels
            total_dist = after.odometer - before.odometer
            dist_from_before = odometer - before.odometer
            time_diff = after.date - before.date

            estimated_offset = (dist_from_before / total_dist) * time_diff.total_seconds()
            estimated_date = before.date + timedelta(seconds=estimated_offset)

            logger.info(
                f"Estimated date {estimated_date} based on odometer {odometer} "
                f"(between {before.odometer} and {after.odometer})"
            )
            return estimated_date

        elif before:
            # After last known refuel - use current time
            logger.info(f"Odometer {odometer} after last refuel, using current time")
            return datetime.now()

        elif after:
            # Before first known refuel - use date before first
            estimated_date = after.date - timedelta(days=7)
            logger.info(f"Odometer {odometer} before first refuel, using {estimated_date}")
            return estimated_date

        else:
            # No other refuels - use current time
            logger.info(f"First refuel, using current time")
            return datetime.now()
