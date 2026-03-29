"""
Start and help command handlers
"""
import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.keyboards.menu import get_main_menu, get_back_to_menu_button

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    await state.clear()

    welcome_text = (
        "🚗 <b>Ласкаво просимо до FuelBot!</b>\n\n"
        "Я допоможу вам вести облік витрат палива.\n\n"
        "<b>Що я вмію:</b>\n"
        "• Розпізнавати чеки з АЗС 📸\n"
        "• Зчитувати показання одометра 🔢\n"
        "• Розраховувати витрату палива ⛽\n"
        "• Конвертувати в USD 💵\n"
        "• Показувати статистику 📊\n\n"
        "Оберіть дію з меню нижче:"
    )

    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_menu())
    logger.info(f"User {message.from_user.id} started the bot")


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    """Show main menu"""
    await state.clear()

    menu_text = (
        "🏠 <b>Головне меню</b>\n\n"
        "Оберіть дію:"
    )

    await callback.message.edit_text(menu_text, parse_mode="HTML", reply_markup=get_main_menu())
    await callback.answer()


@router.callback_query(F.data == "show_help")
async def show_help(callback: CallbackQuery):
    """Show help"""
    help_text = (
        "📖 <b>Довідка по використанню бота</b>\n\n"
        "<b>Як додати заправку:</b>\n"
        "1. Натисніть «⛽ Додати заправку»\n"
        "2. Сфотографуйте чек з АЗС\n"
        "3. Перевірте розпізнані дані\n"
        "4. Сфотографуйте одометр\n"
        "5. Підтвердіть показання\n"
        "6. Готово! Дані збережені ✅\n\n"
        "<b>Поради для кращого розпізнавання:</b>\n"
        "• Знімайте при хорошому освітленні 💡\n"
        "• Тримайте камеру рівно 📱\n"
        "• Переконайтеся що текст читабельний\n"
        "• Уникайте бліків та тіней\n"
        "• Надсилайте як файл (📎), а не як стиснуте фото - це збереже дату та GPS\n\n"
        "<b>Функції:</b>\n"
        "⛽ <b>Додати заправку</b> - зберегти нову заправку\n"
        "📊 <b>Статистика</b> - витрати за поточний місяць\n"
        "📅 <b>Рік по місяцях</b> - пробіг, л/100км, грн, USD, літри по кожному місяцю\n"
        "📜 <b>Історія</b> - список заправок\n"
        "🚗 <b>Мої авто</b> - керувати автомобілями\n\n"
        "<b>Команди:</b> /stats /year /year 2025 /history /dashboard /ai\n\n"
        "Підтримувані АЗС: ОККО, WOG, БРСМ, UPG, Socar, Shell, ANP та інші"
    )

    await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=get_back_to_menu_button())
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    help_text = (
        "📖 <b>Довідка по використанню бота</b>\n\n"
        "<b>Як додати заправку:</b>\n"
        "1. Натисніть «⛽ Додати заправку»\n"
        "2. Сфотографуйте чек з АЗС\n"
        "3. Перевірте розпізнані дані\n"
        "4. Сфотографуйте одометр\n"
        "5. Підтвердіть показання\n"
        "6. Готово! Дані збережені ✅\n\n"
        "<b>Команди:</b> /stats · /year · /year 2025 · /history · /dashboard · /ai\n\n"
        "Підтримувані АЗС: ОККО, WOG, БРСМ, UPG, Socar, Shell, ANP та інші"
    )

    await message.answer(help_text, parse_mode="HTML", reply_markup=get_main_menu())


@router.callback_query(F.data == "my_vehicles")
async def show_my_vehicles(callback: CallbackQuery):
    """Show user vehicles"""
    text = (
        "🚗 <b>Мої автомобілі</b>\n\n"
        "Функція в розробці...\n\n"
        "Незабаром ви зможете:\n"
        "• Додавати декілька автомобілів\n"
        "• Переключатись між ними\n"
        "• Вести окрему статистику для кожного авто"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_button())
    await callback.answer()


@router.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    """Show settings"""
    text = (
        "⚙️ <b>Налаштування</b>\n\n"
        "Функція в розробці...\n\n"
        "Незабаром ви зможете налаштувати:\n"
        "• Одиниці виміру\n"
        "• Мову інтерфейсу\n"
        "• Сповіщення\n"
        "• Експорт даних"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_button())
    await callback.answer()


@router.callback_query(F.data == "cancel")
@router.message(Command("cancel"))
async def cmd_cancel(event, state: FSMContext):
    """Handle cancel"""
    current_state = await state.get_state()

    if current_state is None:
        text = "Нічого скасовувати. Оберіть дію з меню:"
        markup = get_main_menu()
    else:
        await state.clear()
        text = "❌ Дію скасовано. Дані не збережені.\n\nОберіть дію з меню:"
        markup = get_main_menu()
        user_id = event.from_user.id if hasattr(event, 'from_user') else event.message.from_user.id if hasattr(event, 'message') else 'unknown'
        logger.info(f"User {user_id} cancelled operation from state {current_state}")

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=markup)
