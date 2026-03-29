"""
Main menu keyboards
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu() -> InlineKeyboardMarkup:
    """Get main menu keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📸 Додати з фото", callback_data="add_refuel")
        ],
        [
            InlineKeyboardButton(text="✏️ Ввести вручну", callback_data="manual_add_refuel")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats"),
            InlineKeyboardButton(text="📜 Історія", callback_data="show_history")
        ],
        [
            InlineKeyboardButton(text="🔧 Управління заправками", callback_data="manage_refuels")
        ],
        [
            InlineKeyboardButton(text="🚗 Мої авто", callback_data="my_vehicles"),
            InlineKeyboardButton(text="⚙️ Налаштування", callback_data="settings")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Довідка", callback_data="show_help")
        ]
    ])
    return keyboard


def get_back_to_menu_button() -> InlineKeyboardMarkup:
    """Get back to menu button"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
    ])
    return keyboard


def get_cancel_button() -> InlineKeyboardMarkup:
    """Get cancel button"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])
    return keyboard


def get_ai_chat_buttons() -> InlineKeyboardMarkup:
    """Get AI chat buttons with clear history option"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистити діалог", callback_data="clear_chat")],
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
    ])
    return keyboard
