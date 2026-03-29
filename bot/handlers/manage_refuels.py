"""
Manage refuels - edit and delete functionality
"""
import logging
from datetime import datetime
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, delete

from models.database import async_session, Refuel
from bot.keyboards.menu import get_main_menu, get_back_to_menu_button
from bot.states.edit_refuel_states import EditRefuelStates
from services.refuel_calculator import recalculate_refuel_stats
from bot.utils.user_helpers import get_user_id_for_refuels

router = Router()
logger = logging.getLogger(__name__)


def get_refuel_actions_keyboard(refuel_id: int) -> InlineKeyboardMarkup:
    """Get keyboard with actions for a refuel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit_refuel_{refuel_id}"),
            InlineKeyboardButton(text="🗑 Видалити", callback_data=f"delete_refuel_{refuel_id}")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад до списку", callback_data="manage_refuels")
        ]
    ])


def get_manage_refuels_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    """Get keyboard for managing refuels list"""
    buttons = [
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")]
    ]

    # Add pagination if needed
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"manage_refuels_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text="➡️ Далі", callback_data=f"manage_refuels_page_{page+1}"))

    if len(nav_buttons) > 0:
        buttons.insert(0, nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_confirmation_keyboard(refuel_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for delete confirmation"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"confirm_delete_{refuel_id}"),
            InlineKeyboardButton(text="❌ Скасувати", callback_data=f"refuel_details_{refuel_id}")
        ]
    ])


@router.message(Command("manage"))
async def cmd_manage_refuels(message: Message):
    """Show list of refuels to manage"""
    user_id = await get_user_id_for_refuels(message.from_user.id)
    await show_manage_refuels(message, user_id)


@router.callback_query(F.data == "manage_refuels")
async def manage_refuels_callback(callback: CallbackQuery):
    """Show manage refuels from callback"""
    await callback.answer()
    user_id = await get_user_id_for_refuels(callback.from_user.id)
    await show_manage_refuels(callback.message, user_id, edit_message=True)


@router.callback_query(F.data.startswith("manage_refuels_page_"))
async def manage_refuels_page_callback(callback: CallbackQuery):
    """Handle pagination"""
    await callback.answer()
    page = int(callback.data.split("_")[-1])
    user_id = await get_user_id_for_refuels(callback.from_user.id)
    await show_manage_refuels(callback.message, user_id, page=page, edit_message=True)


async def show_manage_refuels(message: Message, user_id: int, page: int = 0, edit_message: bool = False):
    """Show list of refuels to manage"""
    try:
        page_size = 10
        offset = page * page_size

        async with async_session() as session:
            # Get total count
            count_result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
            )
            total_count = len(count_result.scalars().all())

            # Get page of refuels
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(Refuel.date.desc())
                .limit(page_size)
                .offset(offset)
            )
            refuels = result.scalars().all()

        if not refuels:
            text = "📝 У вас поки немає заправок для управління."
            if edit_message:
                await message.edit_text(text, reply_markup=get_main_menu())
            else:
                await message.answer(text, reply_markup=get_main_menu())
            return

        # Build list of refuels with inline buttons
        text = f"📝 <b>Управління заправками</b> (сторінка {page + 1})\n\n"
        text += f"Всього заправок: {total_count}\n\n"

        buttons = []
        for i, refuel in enumerate(refuels, 1):
            date_str = refuel.date.strftime("%d.%m.%Y %H:%M")

            # Short summary for list
            summary = f"{i}. {date_str} | {refuel.station_name} | {refuel.liters}л | {refuel.total_cost}грн"
            text += f"{summary}\n"

            # Add button for this refuel
            buttons.append([
                InlineKeyboardButton(
                    text=f"#{i} - {date_str[:10]}",
                    callback_data=f"refuel_details_{refuel.id}"
                )
            ])

        text += "\n👇 Оберіть заправку для редагування або видалення:"

        # Add navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Попередня", callback_data=f"manage_refuels_page_{page-1}"))
        if (page + 1) * page_size < total_count:
            nav_buttons.append(InlineKeyboardButton(text="Наступна ➡️", callback_data=f"manage_refuels_page_{page+1}"))

        if nav_buttons:
            buttons.append(nav_buttons)

        buttons.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        if edit_message:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing manage refuels: {e}", exc_info=True)
        error_text = f"❌ Помилка: {str(e)}"
        if edit_message:
            await message.edit_text(error_text, reply_markup=get_back_to_menu_button())
        else:
            await message.answer(error_text, reply_markup=get_back_to_menu_button())


@router.callback_query(F.data.startswith("refuel_details_"))
async def show_refuel_details(callback: CallbackQuery):
    """Show detailed info about a refuel"""
    await callback.answer()

    refuel_id = int(callback.data.split("_")[-1])

    # Get internal user_id from telegram_id
    user_id = await get_user_id_for_refuels(callback.from_user.id)

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

        if not refuel:
            await callback.message.edit_text(
                "❌ Заправка не знайдена",
                reply_markup=get_manage_refuels_keyboard()
            )
            return

        # Check if user owns this refuel
        if refuel.user_id != user_id:
            await callback.message.edit_text(
                "❌ У вас немає доступу до цієї заправки",
                reply_markup=get_manage_refuels_keyboard()
            )
            return

        date_str = refuel.date.strftime("%d.%m.%Y %H:%M")

        text = (
            f"📝 <b>Деталі заправки #{refuel.id}</b>\n\n"
            f"📅 Дата: <b>{date_str}</b>\n"
            f"📍 АЗС: <b>{refuel.station_name}</b>\n"
            f"⛽ Паливо: <b>{refuel.fuel_type}</b>\n"
            f"📊 Кількість: <b>{refuel.liters} л</b>\n"
            f"💰 Ціна за літр: <b>{refuel.price_per_liter} грн</b>\n"
            f"💵 Загальна вартість: <b>{refuel.total_cost} грн</b>"
        )

        if refuel.total_cost_usd:
            text += f" (${refuel.total_cost_usd:.2f})"

        text += f"\n🔢 Пробіг: <b>{refuel.odometer} км</b>\n"

        if refuel.distance_from_last:
            text += f"🛣 Відстань від попередньої: <b>{refuel.distance_from_last} км</b>\n"

        if refuel.consumption:
            text += f"⛽ Витрата: <b>{refuel.consumption:.2f} л/100км</b>\n"

        text += f"\n{'✅' if refuel.full_tank else '⚠️'} {'Повний бак' if refuel.full_tank else 'Неповний бак'}"

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_refuel_actions_keyboard(refuel.id)
        )

    except Exception as e:
        logger.error(f"Error showing refuel details: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Помилка: {str(e)}",
            reply_markup=get_manage_refuels_keyboard()
        )


def get_edit_field_keyboard(refuel_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for choosing field to edit"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Дата і час", callback_data=f"edit_field_date_{refuel_id}"),
            InlineKeyboardButton(text="⛽ Літри", callback_data=f"edit_field_liters_{refuel_id}")
        ],
        [
            InlineKeyboardButton(text="💰 Ціна за літр", callback_data=f"edit_field_price_{refuel_id}"),
            InlineKeyboardButton(text="🔢 Пробіг", callback_data=f"edit_field_odometer_{refuel_id}")
        ],
        [
            InlineKeyboardButton(text="📍 АЗС", callback_data=f"edit_field_station_{refuel_id}"),
            InlineKeyboardButton(text="🛢 Тип палива", callback_data=f"edit_field_fuel_{refuel_id}")
        ],
        [
            InlineKeyboardButton(text="✅ Готово", callback_data=f"refuel_details_{refuel_id}"),
            InlineKeyboardButton(text="❌ Скасувати", callback_data=f"refuel_details_{refuel_id}")
        ]
    ])


@router.callback_query(F.data.startswith("edit_refuel_"))
async def edit_refuel(callback: CallbackQuery, state: FSMContext):
    """Edit refuel - show edit options"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    # Get internal user_id from telegram_id
    user_id = await get_user_id_for_refuels(callback.from_user.id)

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

        if not refuel or refuel.user_id != user_id:
            await callback.message.edit_text(
                "❌ Заправка не знайдена",
                reply_markup=get_manage_refuels_keyboard()
            )
            return

        # Save refuel_id to state
        await state.update_data(editing_refuel_id=refuel_id)
        await state.set_state(EditRefuelStates.choosing_field)

        await callback.message.edit_text(
            "✏️ <b>Редагування заправки</b>\n\n"
            "Оберіть поле для редагування:",
            parse_mode="HTML",
            reply_markup=get_edit_field_keyboard(refuel_id)
        )

    except Exception as e:
        logger.error(f"Error starting edit: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Помилка: {str(e)}",
            reply_markup=get_refuel_actions_keyboard(refuel_id)
        )


# Edit date
@router.callback_query(F.data.startswith("edit_field_date_"))
async def edit_field_date(callback: CallbackQuery, state: FSMContext):
    """Start editing date"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    await state.update_data(editing_refuel_id=refuel_id)
    await state.set_state(EditRefuelStates.editing_date)

    await callback.message.edit_text(
        "📅 <b>Редагування дати і часу</b>\n\n"
        "Введіть нову дату і час у форматі:\n"
        "<code>ДД.ММ.РРРР ГГ:ХХ</code>\n\n"
        "Наприклад: <code>24.01.2026 14:30</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"edit_refuel_{refuel_id}")]
        ])
    )


@router.message(EditRefuelStates.editing_date)
async def process_edit_date(message: Message, state: FSMContext):
    """Process date edit"""
    try:
        data = await state.get_data()
        refuel_id = data.get('editing_refuel_id')

        # Get internal user_id from telegram_id
        user_id = await get_user_id_for_refuels(message.from_user.id)

        # Parse date
        new_date = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")

        # Update in database
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

            if refuel and refuel.user_id == user_id:
                refuel.date = new_date
                await session.commit()

                # Recalculate stats
                await recalculate_refuel_stats(user_id)

                await message.answer(
                    f"✅ Дата оновлена: {new_date.strftime('%d.%m.%Y %H:%M')}",
                    reply_markup=get_edit_field_keyboard(refuel_id)
                )
            else:
                await message.answer("❌ Помилка: заправка не знайдена")

        await state.set_state(EditRefuelStates.choosing_field)

    except ValueError:
        await message.answer(
            "❌ Невірний формат дати. Використовуйте: ДД.ММ.РРРР ГГ:ХХ\n"
            "Наприклад: 24.01.2026 14:30"
        )
    except Exception as e:
        logger.error(f"Error editing date: {e}", exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")


# Edit liters
@router.callback_query(F.data.startswith("edit_field_liters_"))
async def edit_field_liters(callback: CallbackQuery, state: FSMContext):
    """Start editing liters"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    await state.update_data(editing_refuel_id=refuel_id)
    await state.set_state(EditRefuelStates.editing_liters)

    await callback.message.edit_text(
        "⛽ <b>Редагування кількості літрів</b>\n\n"
        "Введіть нову кількість літрів:\n"
        "Наприклад: <code>45.5</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"edit_refuel_{refuel_id}")]
        ])
    )


@router.message(EditRefuelStates.editing_liters)
async def process_edit_liters(message: Message, state: FSMContext):
    """Process liters edit"""
    try:
        data = await state.get_data()
        refuel_id = data.get('editing_refuel_id')

        # Get internal user_id from telegram_id
        user_id = await get_user_id_for_refuels(message.from_user.id)

        # Parse liters
        new_liters = Decimal(message.text.strip().replace(',', '.'))

        if new_liters <= 0:
            await message.answer("❌ Кількість літрів повинна бути більше 0")
            return

        # Update in database
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

            if refuel and refuel.user_id == user_id:
                refuel.liters = new_liters
                # Recalculate total cost
                refuel.total_cost = refuel.price_per_liter * new_liters
                await session.commit()

                # Recalculate stats
                await recalculate_refuel_stats(user_id)

                await message.answer(
                    f"✅ Кількість оновлена: {new_liters} л\n"
                    f"💵 Нова загальна вартість: {refuel.total_cost} грн",
                    reply_markup=get_edit_field_keyboard(refuel_id)
                )
            else:
                await message.answer("❌ Помилка: заправка не знайдена")

        await state.set_state(EditRefuelStates.choosing_field)

    except (ValueError, ArithmeticError):
        await message.answer("❌ Невірний формат числа. Введіть число, наприклад: 45.5")
    except Exception as e:
        logger.error(f"Error editing liters: {e}", exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")


# Edit price
@router.callback_query(F.data.startswith("edit_field_price_"))
async def edit_field_price(callback: CallbackQuery, state: FSMContext):
    """Start editing price per liter"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    await state.update_data(editing_refuel_id=refuel_id)
    await state.set_state(EditRefuelStates.editing_price)

    await callback.message.edit_text(
        "💰 <b>Редагування ціни за літр</b>\n\n"
        "Введіть нову ціну за літр (грн):\n"
        "Наприклад: <code>64.50</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"edit_refuel_{refuel_id}")]
        ])
    )


@router.message(EditRefuelStates.editing_price)
async def process_edit_price(message: Message, state: FSMContext):
    """Process price edit"""
    try:
        data = await state.get_data()
        refuel_id = data.get('editing_refuel_id')

        # Get internal user_id from telegram_id
        user_id = await get_user_id_for_refuels(message.from_user.id)

        # Parse price
        new_price = Decimal(message.text.strip().replace(',', '.'))

        if new_price <= 0:
            await message.answer("❌ Ціна повинна бути більше 0")
            return

        # Update in database
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

            if refuel and refuel.user_id == user_id:
                refuel.price_per_liter = new_price
                # Recalculate total cost
                refuel.total_cost = new_price * refuel.liters
                await session.commit()

                await message.answer(
                    f"✅ Ціна оновлена: {new_price} грн/л\n"
                    f"💵 Нова загальна вартість: {refuel.total_cost} грн",
                    reply_markup=get_edit_field_keyboard(refuel_id)
                )
            else:
                await message.answer("❌ Помилка: заправка не знайдена")

        await state.set_state(EditRefuelStates.choosing_field)

    except (ValueError, ArithmeticError):
        await message.answer("❌ Невірний формат числа. Введіть число, наприклад: 64.50")
    except Exception as e:
        logger.error(f"Error editing price: {e}", exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")


# Edit odometer
@router.callback_query(F.data.startswith("edit_field_odometer_"))
async def edit_field_odometer(callback: CallbackQuery, state: FSMContext):
    """Start editing odometer"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    await state.update_data(editing_refuel_id=refuel_id)
    await state.set_state(EditRefuelStates.editing_odometer)

    await callback.message.edit_text(
        "🔢 <b>Редагування пробігу</b>\n\n"
        "Введіть новий пробіг (км):\n"
        "Наприклад: <code>108915</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"edit_refuel_{refuel_id}")]
        ])
    )


@router.message(EditRefuelStates.editing_odometer)
async def process_edit_odometer(message: Message, state: FSMContext):
    """Process odometer edit"""
    try:
        data = await state.get_data()
        refuel_id = data.get('editing_refuel_id')

        # Get internal user_id from telegram_id
        user_id = await get_user_id_for_refuels(message.from_user.id)

        # Parse odometer
        new_odometer = int(message.text.strip())

        if new_odometer <= 0:
            await message.answer("❌ Пробіг повинен бути більше 0")
            return

        # Update in database
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

            if refuel and refuel.user_id == user_id:
                refuel.odometer = new_odometer
                await session.commit()

                # Recalculate stats (distance and consumption)
                await recalculate_refuel_stats(user_id)

                await message.answer(
                    f"✅ Пробіг оновлено: {new_odometer} км",
                    reply_markup=get_edit_field_keyboard(refuel_id)
                )
            else:
                await message.answer("❌ Помилка: заправка не знайдена")

        await state.set_state(EditRefuelStates.choosing_field)

    except ValueError:
        await message.answer("❌ Невірний формат числа. Введіть ціле число, наприклад: 108915")
    except Exception as e:
        logger.error(f"Error editing odometer: {e}", exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")


# Edit station
@router.callback_query(F.data.startswith("edit_field_station_"))
async def edit_field_station(callback: CallbackQuery, state: FSMContext):
    """Start editing station name"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    await state.update_data(editing_refuel_id=refuel_id)
    await state.set_state(EditRefuelStates.editing_station)

    await callback.message.edit_text(
        "📍 <b>Редагування назви АЗС</b>\n\n"
        "Введіть нову назву АЗС:\n"
        "Наприклад: <code>АЗК № 104</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"edit_refuel_{refuel_id}")]
        ])
    )


@router.message(EditRefuelStates.editing_station)
async def process_edit_station(message: Message, state: FSMContext):
    """Process station edit"""
    try:
        data = await state.get_data()
        refuel_id = data.get('editing_refuel_id')

        # Get internal user_id from telegram_id
        user_id = await get_user_id_for_refuels(message.from_user.id)

        new_station = message.text.strip()

        if len(new_station) == 0:
            await message.answer("❌ Назва АЗС не може бути порожньою")
            return

        # Update in database
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

            if refuel and refuel.user_id == user_id:
                refuel.station_name = new_station
                await session.commit()

                await message.answer(
                    f"✅ Назва АЗС оновлена: {new_station}",
                    reply_markup=get_edit_field_keyboard(refuel_id)
                )
            else:
                await message.answer("❌ Помилка: заправка не знайдена")

        await state.set_state(EditRefuelStates.choosing_field)

    except Exception as e:
        logger.error(f"Error editing station: {e}", exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")


# Edit fuel type
@router.callback_query(F.data.startswith("edit_field_fuel_"))
async def edit_field_fuel(callback: CallbackQuery, state: FSMContext):
    """Start editing fuel type"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    await state.update_data(editing_refuel_id=refuel_id)
    await state.set_state(EditRefuelStates.editing_fuel_type)

    await callback.message.edit_text(
        "🛢 <b>Редагування типу палива</b>\n\n"
        "Введіть новий тип палива:\n"
        "Наприклад: <code>ДП-3-Євро5</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"edit_refuel_{refuel_id}")]
        ])
    )


@router.message(EditRefuelStates.editing_fuel_type)
async def process_edit_fuel_type(message: Message, state: FSMContext):
    """Process fuel type edit"""
    try:
        data = await state.get_data()
        refuel_id = data.get('editing_refuel_id')

        # Get internal user_id from telegram_id
        user_id = await get_user_id_for_refuels(message.from_user.id)

        new_fuel_type = message.text.strip()

        if len(new_fuel_type) == 0:
            await message.answer("❌ Тип палива не може бути порожнім")
            return

        # Update in database
        async with async_session() as session:
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

            if refuel and refuel.user_id == user_id:
                refuel.fuel_type = new_fuel_type
                await session.commit()

                await message.answer(
                    f"✅ Тип палива оновлено: {new_fuel_type}",
                    reply_markup=get_edit_field_keyboard(refuel_id)
                )
            else:
                await message.answer("❌ Помилка: заправка не знайдена")

        await state.set_state(EditRefuelStates.choosing_field)

    except Exception as e:
        logger.error(f"Error editing fuel type: {e}", exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")


@router.callback_query(F.data.startswith("delete_refuel_"))
async def delete_refuel_confirm(callback: CallbackQuery):
    """Ask for delete confirmation"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    await callback.message.edit_text(
        "⚠️ <b>Підтвердження видалення</b>\n\n"
        "Ви впевнені, що хочете видалити цю заправку?\n"
        "Цю дію неможливо відмінити!",
        parse_mode="HTML",
        reply_markup=get_delete_confirmation_keyboard(refuel_id)
    )


@router.callback_query(F.data.startswith("confirm_delete_"))
async def delete_refuel_confirmed(callback: CallbackQuery):
    """Delete refuel after confirmation"""
    await callback.answer()
    refuel_id = int(callback.data.split("_")[-1])

    # Get internal user_id from telegram_id
    user_id = await get_user_id_for_refuels(callback.from_user.id)

    try:
        async with async_session() as session:
            # Get refuel to check ownership
            result = await session.execute(
                select(Refuel).where(Refuel.id == refuel_id)
            )
            refuel = result.scalar_one_or_none()

            if not refuel:
                await callback.message.edit_text(
                    "❌ Заправка не знайдена",
                    reply_markup=get_manage_refuels_keyboard()
                )
                return

            # Check ownership
            if refuel.user_id != user_id:
                await callback.message.edit_text(
                    "❌ У вас немає доступу до цієї заправки",
                    reply_markup=get_manage_refuels_keyboard()
                )
                return

            # Delete
            await session.execute(
                delete(Refuel).where(Refuel.id == refuel_id)
            )
            await session.commit()

            logger.info(f"Refuel {refuel_id} deleted by user {callback.from_user.id}")

            await callback.message.edit_text(
                "✅ Заправка успішно видалена!\n\n"
                "Статистика буде автоматично пересчитана при наступному перегляді історії.",
                reply_markup=get_manage_refuels_keyboard()
            )

    except Exception as e:
        logger.error(f"Error deleting refuel: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Помилка при видаленні: {str(e)}",
            reply_markup=get_manage_refuels_keyboard()
        )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Go back to main menu"""
    await callback.answer()
    await callback.message.edit_text(
        "🏠 Головне меню\n\n"
        "Оберіть дію:",
        reply_markup=get_main_menu()
    )
