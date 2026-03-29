"""
Manual refuel entry - add refuel without photos
"""
import logging
from datetime import datetime
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards.inline import get_confirm_keyboard
from bot.keyboards.menu import get_back_to_menu_button, get_cancel_button
from bot.states.refuel_states import ManualRefuelStates
from models.database import async_session, User, Refuel
from models.schemas import RefuelCreate
from services.currency.exchange_rate import get_exchange_rate_service
from sqlalchemy import select

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "manual_add_refuel")
async def start_manual_refuel_callback(callback: CallbackQuery, state: FSMContext):
    """Start manual refuel entry from button"""
    await callback.answer()
    await start_manual_refuel(callback.message, state)


@router.message(Command("manual"))
async def cmd_manual_refuel(message: Message, state: FSMContext):
    """Start manual refuel entry from command"""
    await start_manual_refuel(message, state)


async def start_manual_refuel(message: Message, state: FSMContext):
    """Start manual refuel entry process"""
    await state.clear()

    await message.answer(
        "✏️ <b>Ручне додавання заправки</b>\n\n"
        "Введіть дані заправки без фото.\n\n"
        "📍 <b>Крок 1/6:</b> Введіть назву АЗС\n"
        "Наприклад: <code>АЗК №104</code>, <code>WOG</code>, <code>OKKO</code>\n\n"
        "Або натисніть /cancel для скасування",
        parse_mode="HTML",
        reply_markup=get_cancel_button()
    )
    await state.set_state(ManualRefuelStates.waiting_station)
    logger.info(f"User {message.from_user.id} started manual refuel entry")


@router.message(ManualRefuelStates.waiting_station)
async def receive_station(message: Message, state: FSMContext):
    """Receive station name"""
    station = message.text.strip()

    if not station or len(station) < 2:
        await message.answer(
            "⚠️ Назва АЗС занадто коротка. Спробуйте ще раз:",
            reply_markup=get_cancel_button()
        )
        return

    await state.update_data(station=station)

    await message.answer(
        f"✅ АЗС: <b>{station}</b>\n\n"
        f"⛽ <b>Крок 2/6:</b> Введіть кількість літрів\n"
        f"Наприклад: <code>45.5</code> або <code>50</code>",
        parse_mode="HTML",
        reply_markup=get_cancel_button()
    )
    await state.set_state(ManualRefuelStates.waiting_liters)


@router.message(ManualRefuelStates.waiting_liters)
async def receive_liters(message: Message, state: FSMContext):
    """Receive liters"""
    try:
        liters = float(message.text.strip().replace(',', '.'))

        if liters <= 0 or liters > 100:
            await message.answer(
                "⚠️ Некоректна кількість літрів (має бути від 0 до 100).\n"
                "Спробуйте ще раз:",
                reply_markup=get_cancel_button()
            )
            return

        await state.update_data(liters=liters)

        await message.answer(
            f"✅ Літри: <b>{liters} л</b>\n\n"
            f"💵 <b>Крок 3/6:</b> Введіть ціну за літр (грн)\n"
            f"Наприклад: <code>64.80</code> або <code>65</code>",
            parse_mode="HTML",
            reply_markup=get_cancel_button()
        )
        await state.set_state(ManualRefuelStates.waiting_price_per_liter)

    except ValueError:
        await message.answer(
            "⚠️ Невірний формат. Введіть число (наприклад: 45.5):",
            reply_markup=get_cancel_button()
        )


@router.message(ManualRefuelStates.waiting_price_per_liter)
async def receive_price_per_liter(message: Message, state: FSMContext):
    """Receive price per liter"""
    try:
        price = float(message.text.strip().replace(',', '.'))

        if price <= 0 or price > 200:
            await message.answer(
                "⚠️ Некоректна ціна (має бути від 0 до 200 грн).\n"
                "Спробуйте ще раз:",
                reply_markup=get_cancel_button()
            )
            return

        data = await state.get_data()
        liters = data['liters']
        total_cost = liters * price

        await state.update_data(price_per_liter=price, total_cost=total_cost)

        await message.answer(
            f"✅ Ціна за літр: <b>{price} грн/л</b>\n"
            f"💰 Загальна сума: <b>{total_cost:.2f} грн</b>\n\n"
            f"⛽ <b>Крок 4/6:</b> Введіть тип палива\n"
            f"Наприклад: <code>ДП</code>, <code>А-95</code>, <code>ДП-3-Євро5</code>",
            parse_mode="HTML",
            reply_markup=get_cancel_button()
        )
        await state.set_state(ManualRefuelStates.waiting_fuel_type)

    except ValueError:
        await message.answer(
            "⚠️ Невірний формат. Введіть число (наприклад: 64.80):",
            reply_markup=get_cancel_button()
        )


@router.message(ManualRefuelStates.waiting_fuel_type)
async def receive_fuel_type(message: Message, state: FSMContext):
    """Receive fuel type"""
    fuel_type = message.text.strip()

    if not fuel_type or len(fuel_type) < 2:
        await message.answer(
            "⚠️ Тип палива занадто короткий. Спробуйте ще раз:",
            reply_markup=get_cancel_button()
        )
        return

    await state.update_data(fuel_type=fuel_type)

    await message.answer(
        f"✅ Паливо: <b>{fuel_type}</b>\n\n"
        f"🔢 <b>Крок 5/6:</b> Введіть показання одометра (км)\n"
        f"Наприклад: <code>150000</code>",
        parse_mode="HTML",
        reply_markup=get_cancel_button()
    )
    await state.set_state(ManualRefuelStates.waiting_odometer)


@router.message(ManualRefuelStates.waiting_odometer)
async def receive_odometer(message: Message, state: FSMContext):
    """Receive odometer reading"""
    try:
        odometer = int(message.text.strip().replace(' ', ''))

        if odometer < 0 or odometer > 1000000:
            await message.answer(
                "⚠️ Некоректний пробіг (має бути від 0 до 1,000,000 км).\n"
                "Спробуйте ще раз:",
                reply_markup=get_cancel_button()
            )
            return

        await state.update_data(odometer=odometer)

        # Show buttons for date/time input
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Поточна дата/час", callback_data="manual_use_current_datetime")],
            [InlineKeyboardButton(text="✏️ Ввести вручну", callback_data="manual_enter_datetime")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
        ])

        await message.answer(
            f"✅ Одометр: <b>{odometer} км</b>\n\n"
            f"📅 <b>Крок 6/6:</b> Дата та час заправки\n"
            f"Виберіть опцію:",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    except ValueError:
        await message.answer(
            "⚠️ Невірний формат. Введіть ціле число (наприклад: 150000):",
            reply_markup=get_cancel_button()
        )


@router.callback_query(F.data == "manual_use_current_datetime")
async def use_current_datetime(callback: CallbackQuery, state: FSMContext):
    """Use current date/time for refuel"""
    await callback.answer()

    refuel_datetime = datetime.now()
    await state.update_data(refuel_datetime=refuel_datetime)

    # Show confirmation
    await show_manual_confirmation(callback.message, state)


@router.callback_query(F.data == "manual_enter_datetime")
async def enter_datetime_manually(callback: CallbackQuery, state: FSMContext):
    """Ask user to enter date/time manually"""
    await callback.answer()

    await callback.message.edit_text(
        "✏️ <b>Введіть дату та час заправки</b>\n\n"
        "Формат: <code>YYYY-MM-DD HH:MM</code>\n"
        "Наприклад: <code>2026-01-25 14:30</code>",
        parse_mode="HTML"
    )
    await state.set_state(ManualRefuelStates.waiting_datetime)


@router.message(ManualRefuelStates.waiting_datetime)
async def receive_datetime(message: Message, state: FSMContext):
    """Receive manually entered date/time"""
    try:
        user_input = message.text.strip()
        refuel_datetime = datetime.strptime(user_input, "%Y-%m-%d %H:%M")

        await state.update_data(refuel_datetime=refuel_datetime)

        # Show confirmation
        await show_manual_confirmation(message, state)

    except ValueError:
        await message.answer(
            "❌ <b>Невірний формат дати</b>\n\n"
            "Використайте формат: <code>YYYY-MM-DD HH:MM</code>\n"
            "Наприклад: <code>2026-01-25 14:30</code>",
            parse_mode="HTML"
        )


async def show_manual_confirmation(message: Message, state: FSMContext):
    """Show confirmation of manually entered refuel"""
    data = await state.get_data()

    station = data['station']
    liters = data['liters']
    price_per_liter = data['price_per_liter']
    total_cost = data['total_cost']
    fuel_type = data['fuel_type']
    odometer = data['odometer']
    refuel_datetime = data['refuel_datetime']

    text = (
        "📋 <b>Перевірте дані заправки:</b>\n\n"
        f"📍 АЗС: <b>{station}</b>\n"
        f"⛽ Паливо: <b>{fuel_type}</b>\n"
        f"📊 Літри: <b>{liters} л</b>\n"
        f"💵 Ціна: <b>{price_per_liter} грн/л</b>\n"
        f"💰 Сума: <b>{total_cost:.2f} грн</b>\n"
        f"🔢 Одометр: <b>{odometer} км</b>\n"
        f"📅 Дата: <b>{refuel_datetime.strftime('%Y-%m-%d %H:%M')}</b>\n\n"
        "Все вірно?"
    )

    await state.set_state(ManualRefuelStates.confirm_manual)

    if isinstance(message, Message):
        await message.answer(text, parse_mode="HTML", reply_markup=get_confirm_keyboard())
    else:
        # It's a callback query message
        await message.answer(text, parse_mode="HTML", reply_markup=get_confirm_keyboard())


@router.callback_query(ManualRefuelStates.confirm_manual, F.data == "confirm")
async def save_manual_refuel(callback: CallbackQuery, state: FSMContext):
    """Save manually entered refuel to database"""
    await callback.answer()

    data = await state.get_data()

    try:
        # Get user
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            user = result.scalar_one()

            # Get USD exchange rate
            exchange_service = get_exchange_rate_service()
            refuel_datetime = data['refuel_datetime']
            usd_rate = await exchange_service.get_usd_rate(refuel_datetime)

            total_cost_usd = None
            price_per_liter_usd = None

            if usd_rate:
                total_cost_dec = Decimal(str(data['total_cost']))
                price_per_liter_dec = Decimal(str(data['price_per_liter']))
                usd_rate_dec = Decimal(str(usd_rate))

                total_cost_usd = float(total_cost_dec / usd_rate_dec)
                price_per_liter_usd = float(price_per_liter_dec / usd_rate_dec)

            # Create refuel record
            refuel = Refuel(
                user_id=user.id,
                date=refuel_datetime,
                station_name=data['station'],
                fuel_type=data['fuel_type'],
                liters=Decimal(str(data['liters'])),
                price_per_liter=Decimal(str(data['price_per_liter'])),
                total_cost=Decimal(str(data['total_cost'])),
                odometer=data['odometer'],
                usd_rate=Decimal(str(usd_rate)) if usd_rate else None,
                total_cost_usd=Decimal(str(total_cost_usd)) if total_cost_usd else None,
                price_per_liter_usd=Decimal(str(price_per_liter_usd)) if price_per_liter_usd else None,
                full_tank=True,  # Assume full tank for manual entry
                receipt_file_id="manual_entry",  # Required field, mark as manual
                ai_confidence=100,  # Manual entry = 100% confidence
            )

            session.add(refuel)
            await session.commit()

            logger.info(
                f"Manual refuel saved for user {user.telegram_id}: "
                f"{data['liters']}L, {data['total_cost']}грн, {data['odometer']}km, date={refuel_datetime}"
            )

        await callback.message.edit_text(
            "✅ <b>Заправка успішно додана!</b>\n\n"
            f"📍 {data['station']}\n"
            f"⛽ {data['fuel_type']}: {data['liters']}л × {data['price_per_liter']}грн = {data['total_cost']:.2f}грн\n"
            f"🔢 Одометр: {data['odometer']} км\n"
            f"📅 {refuel_datetime.strftime('%Y-%m-%d %H:%M')}",
            parse_mode="HTML",
            reply_markup=get_back_to_menu_button()
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Error saving manual refuel: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Помилка збереження: {str(e)}",
            reply_markup=get_back_to_menu_button()
        )
        await state.clear()


@router.callback_query(ManualRefuelStates.confirm_manual, F.data == "retry")
async def retry_manual_refuel(callback: CallbackQuery, state: FSMContext):
    """Restart manual refuel entry"""
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await start_manual_refuel(callback.message, state)
