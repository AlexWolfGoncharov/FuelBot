"""
AI Assistant for analyzing refuel data
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from models.database import async_session, Refuel, ChatHistory
from bot.keyboards.menu import get_back_to_menu_button, get_ai_chat_buttons
from bot.utils.user_helpers import get_user_id_by_telegram_id
from services.ai_vision.gemini import get_gemini_ai_response

router = Router()
logger = logging.getLogger(__name__)


async def get_user_refuels_summary(user_id: int, days: int = None) -> str:
    """Get summary of user's refuels for AI context"""
    try:
        # Get refuels for last N days, or ALL if days is None
        async with async_session() as session:
            query = (
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(Refuel.date.desc())
            )

            # Apply date filter only if days is specified
            if days:
                since_date = datetime.now() - timedelta(days=days)
                query = query.where(Refuel.date >= since_date)

            result = await session.execute(query)
            refuels = result.scalars().all()

        if not refuels:
            return "У користувача немає заправок."

        # Build summary
        period_text = f"за останні {days} днів" if days else "за весь період"
        summary = f"Дані про заправки користувача {period_text}:\n\n"

        # Overall stats
        total_liters = sum(r.liters for r in refuels)
        total_cost = sum(r.total_cost for r in refuels)
        total_distance = sum(r.distance_from_last for r in refuels if r.distance_from_last)

        summary += f"Загальна статистика:\n"
        summary += f"- Всього заправок: {len(refuels)}\n"
        summary += f"- Всього літрів: {total_liters:.2f} л\n"
        summary += f"- Загальна вартість: {total_cost:.2f} грн\n"
        summary += f"- Пробіг: {total_distance} км\n"
        summary += f"- Середня ціна: {total_cost/total_liters:.2f} грн/л\n\n"

        # Consumption stats
        refuels_with_consumption = [r for r in refuels if r.consumption]
        if refuels_with_consumption:
            avg_consumption = sum(r.consumption for r in refuels_with_consumption) / len(refuels_with_consumption)
            summary += f"- Середня витрата: {avg_consumption:.2f} л/100км\n\n"

        # Stats by year and month for better context
        from collections import defaultdict
        by_year_month = defaultdict(list)

        for refuel in refuels:
            year_month = refuel.date.strftime("%Y-%m")
            by_year_month[year_month].append(refuel)

        summary += "Розподіл по місяцях:\n"
        for year_month in sorted(by_year_month.keys(), reverse=True)[:12]:  # Last 12 months
            month_refuels = by_year_month[year_month]
            month_liters = sum(r.liters for r in month_refuels)
            month_cost = sum(r.total_cost for r in month_refuels)
            month_name = datetime.strptime(year_month, "%Y-%m").strftime("%m.%Y")
            summary += f"  {month_name}: {len(month_refuels)} заправок, {month_liters:.1f}л, {month_cost:.0f}грн\n"

        summary += "\n"

        # Recent refuels
        summary += "Останні 15 заправок:\n"
        for i, refuel in enumerate(refuels[:15], 1):
            date_str = refuel.date.strftime("%d.%m.%Y")
            summary += f"{i}. {date_str}: {refuel.liters}л × {refuel.price_per_liter}грн = {refuel.total_cost}грн"
            summary += f" | {refuel.station_name} | {refuel.fuel_type}"
            if refuel.distance_from_last:
                summary += f" | +{refuel.distance_from_last}км"
            if refuel.consumption:
                summary += f" | {refuel.consumption:.2f}л/100км"
            summary += "\n"

        return summary

    except Exception as e:
        logger.error(f"Error getting refuels summary: {e}", exc_info=True)
        return f"Помилка отримання даних: {str(e)}"


@router.message(Command("ai"))
async def cmd_ai_help(message: Message):
    """Show AI assistant help"""
    help_text = (
        "🤖 <b>AI Асистент</b>\n\n"
        "Я можу проаналізувати ваші дані про заправки та відповісти на питання:\n\n"
        "📊 <b>Приклади питань:</b>\n"
        "• Яка середня витрата палива?\n"
        "• Скільки я витратив за останній місяць?\n"
        "• На якій АЗС найдешевше?\n"
        "• Як змінюється витрата палива?\n"
        "• Коли найкраще заправлятись?\n"
        "• Порівняй витрати за різні місяці\n"
        "• Дай поради щодо економії\n\n"
        "💬 Просто напишіть ваше питання, і я відповім на основі ваших даних!\n\n"
        "💡 <i>Я пам'ятаю контекст розмови - можете ставити уточнюючі питання</i>\n"
        "🗑 Команда /clear_chat - очистити історію діалогу"
    )

    await message.answer(help_text, parse_mode="HTML", reply_markup=get_back_to_menu_button())


@router.message(Command("clear_chat"))
async def cmd_clear_chat(message: Message):
    """Clear chat history with AI assistant"""
    user_id = message.from_user.id

    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(
            delete(ChatHistory).where(ChatHistory.user_id == user_id)
        )
        await session.commit()

    await message.answer(
        "🗑 Історію діалогу очищено. Почніть нову розмову!",
        reply_markup=get_back_to_menu_button()
    )


@router.message(F.text & ~F.text.startswith("/"))
async def ai_chat(message: Message):
    """Handle AI chat messages"""
    user_question = message.text.strip()

    # Ignore if message is too short or looks like a number/edit
    if len(user_question) < 5 or user_question.replace('.', '').replace(',', '').isdigit():
        return

    processing_msg = await message.answer("🤖 Аналізую ваші дані...")

    try:
        telegram_id = message.from_user.id
        # Refuel.user_id is internal users.id, not Telegram id
        try:
            db_user_id = await get_user_id_by_telegram_id(telegram_id)
        except NoResultFound:
            await processing_msg.edit_text(
                "Спочатку натисніть /start, щоб бот зареєстрував вас у системі.",
                reply_markup=get_back_to_menu_button(),
            )
            return

        # Get user's refuel data summary
        data_summary = await get_user_refuels_summary(db_user_id)

        # Get chat history (last 10 messages to keep context manageable)
        # ChatHistory.user_id is stored as Telegram id (legacy column usage)
        async with async_session() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.user_id == telegram_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(10)
            )
            history_records = result.scalars().all()
            history_records = list(reversed(history_records))  # Oldest first

        # Build Gemini chat history format
        gemini_history = []
        for record in history_records:
            gemini_history.append({
                "role": "user" if record.role == "user" else "model",
                "parts": [record.message]
            })

        # Build system instruction with data and formatting rules
        system_instruction = f"""Ти - експерт-аналітик по витратам на паливо та економії палива в межах цього Telegram-бота.

КРИТИЧНО: Нижче вже передано зріз даних з обліку заправок цього користувача з бази бота. Ти НЕ маєш казати, що «немає доступу до бази» або що ти «не бачиш дані» — якщо блок порожній або написано що заправок немає, відповідай з цього факту (наприклад запропонуй додати заправки), а не відмовляйся.

{data_summary}

Проаналізуй дані та дай детальну, корисну відповідь українською мовою.
Якщо в даних є тренди - вкажи їх. Якщо можеш дати поради - дай їх.
Використовуй конкретні цифри з даних.

ВАЖЛИВО - ФОРМАТУВАННЯ:
- Використовуй ТІЛЬКИ ці HTML теги: <b>, <i>, <u>, <code>
- НЕ використовуй: DOCTYPE, html, head, body, div, span, p, h1-h6, ul, ol, li
- Заголовки: <b>Заголовок</b>
- Списки: використовуй емоджі (📊, 📈, 💡, ⚠️, ✅) замість маркерів
- Для важливих цифр: <b>123</b>
- Розділяй розділи порожнім рядком (використовуй \n\n)
- НЕ використовуй markdown **, #, - тощо
- Роби відповідь короткою і чіткою, без зайвих слів
- Відповідай ЧИСТИМ ТЕКСТОМ з простими тегами, БЕЗ HTML-документа

Приклад формату:
<b>📊 Аналіз частоти заправок:</b>

За 90 днів - <b>5 заправок</b>
Це приблизно раз на <b>18 днів</b>

<b>💡 Рекомендації:</b>

✅ Моніторте витрату палива
⚠️ Перевірте тиск у шинах

Якщо питання не стосується заправок або автомобілів, ввічливо скажи, що ти спеціалізуєшся тільки на аналізі витрат на паливо."""

        # Get AI response with chat history and system instruction
        ai_response = await get_gemini_ai_response(user_question, gemini_history, system_instruction)

        if not ai_response:
            await processing_msg.edit_text(
                "❌ На жаль, не вдалося отримати відповідь від AI. Спробуйте пізніше.",
                reply_markup=get_back_to_menu_button()
            )
            return

        # Clean response from unsupported HTML tags
        # Telegram supports only: b, strong, i, em, u, ins, s, strike, del, code, pre, a
        import re

        # Remove DOCTYPE, html, head, body tags and their content
        ai_response = re.sub(r'<!DOCTYPE[^>]*>', '', ai_response, flags=re.IGNORECASE)
        ai_response = re.sub(r'<html[^>]*>|</html>', '', ai_response, flags=re.IGNORECASE)
        ai_response = re.sub(r'<head[^>]*>.*?</head>', '', ai_response, flags=re.IGNORECASE | re.DOTALL)
        ai_response = re.sub(r'<body[^>]*>|</body>', '', ai_response, flags=re.IGNORECASE)

        # Remove other unsupported tags but keep their content
        ai_response = re.sub(r'</?(?:div|span|p|h[1-6]|ul|ol|li)[^>]*>', '', ai_response, flags=re.IGNORECASE)

        # Clean up extra whitespace
        ai_response = re.sub(r'\n\s*\n\s*\n', '\n\n', ai_response)
        ai_response = ai_response.strip()

        # Save conversation to history
        async with async_session() as session:
            # Save user message
            user_msg = ChatHistory(
                user_id=telegram_id,
                role="user",
                message=user_question
            )
            session.add(user_msg)

            # Save assistant response
            assistant_msg = ChatHistory(
                user_id=telegram_id,
                role="assistant",
                message=ai_response
            )
            session.add(assistant_msg)

            await session.commit()

        # Send response
        await processing_msg.edit_text(
            f"🤖 <b>AI Асистент:</b>\n\n{ai_response}",
            parse_mode="HTML",
            reply_markup=get_ai_chat_buttons()
        )

        logger.info(f"AI response sent to user telegram_id={telegram_id} for question: {user_question[:50]}")

    except Exception as e:
        logger.error(f"Error in AI chat: {e}", exc_info=True)
        await processing_msg.edit_text(
            f"❌ Помилка: {str(e)}",
            reply_markup=get_back_to_menu_button()
        )


@router.callback_query(F.data == "ai_assistant")
async def ai_assistant_callback(callback: CallbackQuery):
    """Show AI assistant from menu"""
    await callback.answer()
    await cmd_ai_help(callback.message)


@router.callback_query(F.data == "clear_chat")
async def clear_chat_callback(callback: CallbackQuery):
    """Clear chat history via button"""
    user_id = callback.from_user.id

    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(
            delete(ChatHistory).where(ChatHistory.user_id == user_id)
        )
        await session.commit()

    await callback.answer("Історію діалогу очищено!", show_alert=True)
    await callback.message.edit_text(
        "🗑 Історію діалогу очищено. Почніть нову розмову!",
        reply_markup=get_back_to_menu_button()
    )
