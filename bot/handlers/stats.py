"""
Statistics and history handlers
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from bot.keyboards.menu import get_main_menu, get_back_to_menu_button
from sqlalchemy import select, func

from models.database import async_session, Refuel
from services.refuel_calculator import recalculate_refuel_stats
from bot.utils.user_helpers import get_user_id_by_telegram_id

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "show_stats")
async def show_stats_callback(callback: CallbackQuery):
    """Show stats from menu button"""
    await callback.answer()
    # Get internal user.id from telegram_id
    u = callback.from_user
    user_id = await get_user_id_by_telegram_id(u.id, u.username, u.first_name)
    logger.info(f"Stats requested via callback by telegram_id={callback.from_user.id}, user_id={user_id}")
    await show_stats_for_user(callback.message, user_id)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Show statistics for current month"""
    # Get internal user.id from telegram_id
    u = message.from_user
    user_id = await get_user_id_by_telegram_id(u.id, u.username, u.first_name)
    logger.info(f"Stats requested via command by telegram_id={message.from_user.id}, user_id={user_id}")
    await show_stats_for_user(message, user_id)


async def show_stats_for_user(message: Message, user_id: int):
    """Show statistics for current month for a specific user"""
    logger.info(f"Generating stats for user {user_id}")

    try:
        # Recalculate all refuel stats before showing statistics
        logger.info(f"Recalculating refuel statistics for user {user_id}")
        updated_count = await recalculate_refuel_stats(user_id)
        logger.info(f"Recalculated {updated_count} refuels for user {user_id}")

        # Get current month start
        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)
        logger.info(f"Checking stats for month starting {month_start}")

        async with async_session() as session:
            # Query refuels for current month
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .where(Refuel.date >= month_start)
                .order_by(Refuel.date.desc())
            )
            refuels = result.scalars().all()

        logger.info(f"Found {len(refuels)} refuels for user {user_id} in current month")

        if not refuels:
            await message.answer(
                "📊 У вас поки немає заправок за цей місяць.",
                reply_markup=get_main_menu()
            )
            return

        # Calculate statistics in UAH
        total_liters = sum(r.liters for r in refuels)
        total_cost = sum(r.total_cost for r in refuels)
        avg_price = total_cost / total_liters if total_liters > 0 else 0

        # Calculate USD totals
        refuels_with_usd = [r for r in refuels if r.total_cost_usd]
        total_cost_usd = sum(r.total_cost_usd for r in refuels_with_usd) if refuels_with_usd else None

        # Calculate consumption
        refuels_with_consumption = [r for r in refuels if r.consumption]
        avg_consumption = (
            sum(r.consumption for r in refuels_with_consumption) / len(refuels_with_consumption)
            if refuels_with_consumption else None
        )

        # Calculate distance
        total_distance = sum(r.distance_from_last for r in refuels if r.distance_from_last)

        # Month name in Ukrainian
        month_names_uk = {
            1: 'січень', 2: 'лютий', 3: 'березень', 4: 'квітень',
            5: 'травень', 6: 'червень', 7: 'липень', 8: 'серпень',
            9: 'вересень', 10: 'жовтень', 11: 'листопад', 12: 'грудень'
        }
        month_name = month_names_uk[now.month]

        stats_text = (
            f"📊 <b>Статистика за {month_name} {now.year}</b>\n\n"
            f"📝 Заправок: <b>{len(refuels)}</b>\n"
            f"⛽ Всього літрів: <b>{total_liters:.2f} л</b>\n"
            f"💵 Всього витрачено: <b>{total_cost:.2f} грн</b>"
        )

        if total_cost_usd:
            stats_text += f" (${total_cost_usd:.2f})"

        stats_text += f"\n💰 Середня ціна: <b>{avg_price:.2f} грн/л</b>\n"

        if total_distance > 0:
            stats_text += f"🛣 Пробіг: <b>{total_distance} км</b>\n"
            cost_per_km = total_cost / Decimal(str(total_distance))
            stats_text += f"💸 Вартість км: <b>{cost_per_km:.2f} грн/км</b>\n"

        if avg_consumption:
            stats_text += f"⛽ Середня витрата: <b>{avg_consumption:.2f} л/100км</b>\n"

        await message.answer(stats_text, parse_mode="HTML", reply_markup=get_back_to_menu_button())

        logger.info(f"Stats shown for user {user_id}: {len(refuels)} refuels")

    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        await message.answer(
            f"❌ Помилка при отриманні статистики: {str(e)}",
            reply_markup=get_back_to_menu_button()
        )


@router.callback_query(F.data == "show_history")
async def show_history_callback(callback: CallbackQuery):
    """Show history from menu button"""
    await callback.answer()
    # Get internal user.id from telegram_id
    u = callback.from_user
    user_id = await get_user_id_by_telegram_id(u.id, u.username, u.first_name)
    logger.info(f"History requested via callback by telegram_id={callback.from_user.id}, user_id={user_id}")
    await show_history_for_user(callback.message, user_id, page=0, edit=False)


@router.callback_query(F.data.startswith("history_page_"))
async def history_page_callback(callback: CallbackQuery):
    """Handle history pagination"""
    await callback.answer()
    page = int(callback.data.split("_")[2])
    # Get internal user.id from telegram_id
    u = callback.from_user
    user_id = await get_user_id_by_telegram_id(u.id, u.username, u.first_name)
    logger.info(f"History page {page} requested by telegram_id={callback.from_user.id}, user_id={user_id}")
    await show_history_for_user(callback.message, user_id, page=page, edit=True)


@router.message(Command("history"))
async def cmd_history(message: Message):
    """Show last 10 refuels"""
    # Get internal user.id from telegram_id
    u = message.from_user
    user_id = await get_user_id_by_telegram_id(u.id, u.username, u.first_name)
    logger.info(f"History requested via command by telegram_id={message.from_user.id}, user_id={user_id}")
    await show_history_for_user(message, user_id, page=0, edit=False)


async def show_history_for_user(message: Message, user_id: int, page: int = 0, edit: bool = False):
    """Show refuels history with pagination

    Args:
        message: Message object
        user_id: Internal user ID
        page: Page number (0-indexed)
        edit: If True, edit existing message instead of sending new one
    """
    logger.info(f"Generating history for user {user_id}, page {page}")

    try:
        # Recalculate all refuel stats before showing history
        logger.info(f"Recalculating refuel statistics for user {user_id}")
        updated_count = await recalculate_refuel_stats(user_id)
        logger.info(f"Recalculated {updated_count} refuels for user {user_id}")

        # Get total count
        async with async_session() as session:
            count_result = await session.execute(
                select(func.count(Refuel.id))
                .where(Refuel.user_id == user_id)
            )
            total_count = count_result.scalar()

        if total_count == 0:
            await message.answer(
                "📝 У вас поки немає заправок.",
                reply_markup=get_main_menu()
            )
            return

        # Calculate pagination
        per_page = 10
        total_pages = (total_count + per_page - 1) // per_page  # Ceiling division

        # Ensure page is within bounds
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        offset = page * per_page

        # Get refuels for current page
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(Refuel.date.desc())
                .limit(per_page)
                .offset(offset)
            )
            refuels = result.scalars().all()

        logger.info(f"Found {len(refuels)} refuels for user {user_id} on page {page}")

        # Build history text
        history_text = f"📝 <b>Історія заправок (сторінка {page + 1} з {total_pages}):</b>\n"
        history_text += f"Всього заправок: {total_count}\n\n"

        for i, refuel in enumerate(refuels, offset + 1):
            date_str = refuel.date.strftime("%d.%m.%Y %H:%M")

            cost_text = f"{refuel.total_cost} грн"
            if refuel.total_cost_usd:
                cost_text += f" (${refuel.total_cost_usd:.2f})"

            history_text += (
                f"{i}. <b>{date_str}</b>\n"
                f"   📍 {refuel.station_name}\n"
                f"   ⛽ {refuel.fuel_type}: {refuel.liters} л × {refuel.price_per_liter} грн = {cost_text}\n"
                f"   🔢 Пробіг: {refuel.odometer} км"
            )

            if refuel.distance_from_last:
                history_text += f" (+{refuel.distance_from_last} км)"

            if refuel.consumption:
                history_text += f"\n   ⛽ Витрата: {refuel.consumption:.2f} л/100км"

            history_text += "\n\n"

        # Build pagination keyboard
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        buttons = []
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Попередні", callback_data=f"history_page_{page - 1}"))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="➡️ Наступні", callback_data=f"history_page_{page + 1}"))

        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        if edit:
            await message.edit_text(history_text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(history_text, parse_mode="HTML", reply_markup=keyboard)

        logger.info(f"History shown for user {user_id}: {len(refuels)} refuels on page {page}")

    except Exception as e:
        logger.error(f"Error getting history: {e}", exc_info=True)
        await message.answer(
            f"❌ Помилка при отриманні історії: {str(e)}",
            reply_markup=get_back_to_menu_button()
        )
