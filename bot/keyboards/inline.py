"""
Inline keyboards for the Telegram bot
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Get confirmation keyboard with Yes/No buttons"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, верно", callback_data="confirm"),
                InlineKeyboardButton(text="❌ Нет, повторить", callback_data="retry")
            ],
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit")
            ]
        ]
    )
    return keyboard


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Get cancel keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")
            ]
        ]
    )
    return keyboard


def get_stats_period_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for selecting statistics period"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Этот месяц", callback_data="stats_month"),
                InlineKeyboardButton(text="📆 Этот год", callback_data="stats_year")
            ],
            [
                InlineKeyboardButton(text="📊 Последние 10", callback_data="stats_last10"),
                InlineKeyboardButton(text="📈 Все время", callback_data="stats_all")
            ]
        ]
    )
    return keyboard


def get_full_tank_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for asking if tank was filled completely"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⛽ Так, до повного", callback_data="full_yes"),
                InlineKeyboardButton(text="📊 Ні, частково", callback_data="full_no")
            ]
        ]
    )
    return keyboard
