"""
AI Assistant for analyzing refuel data
"""
import html
import logging
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from google.genai import types as genai_types
from sqlalchemy import select

from models.database import async_session, ChatHistory
from bot.keyboards.menu import get_back_to_menu_button, get_ai_chat_buttons
from bot.utils.user_helpers import get_user_id_for_refuels
from services.ai_fuel_agent import run_fuel_agent

router = Router()
logger = logging.getLogger(__name__)

# Історія діалогу в Gemini: обмеження розміру повідомлень асистента
_AI_HISTORY_MESSAGES = 12
_MAX_ASSISTANT_CHARS = 2500

# Telegram Bot API: максимум 4096 символів на повідомлення
_TELEGRAM_MAX_MESSAGE_LEN = 4096
# Тіло plain при розбитті — з запасом під заголовок «частина i/n»
_AI_PLAIN_CHUNK = 3500


def _ai_response_to_plain(html_text: str) -> str:
    """Прибирає HTML для безпечного багатоповідомленого виводу (без обрізаних тегів)."""
    t = re.sub(r"<[^>]+>", "", html_text)
    return html.unescape(t).strip()


def _split_plain_text(text: str, max_chunk: int) -> list[str]:
    """Розбиває текст по абзацах/рядках; жорстко ріже, якщо рядок довший за max_chunk."""
    if not text:
        return []
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_chunk:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, max_chunk)
        if cut < max_chunk // 4:
            cut = rest.rfind("\n", 0, max_chunk)
        if cut <= 0:
            cut = max_chunk
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks


async def _send_ai_response_telegram(
    message: Message, processing_msg: Message, ai_response_html: str
) -> None:
    """Одне HTML-повідомлення або кілька plain — без MESSAGE_TOO_LONG."""
    full = f"🤖 <b>AI Асистент:</b>\n\n{ai_response_html}"
    if len(full) <= _TELEGRAM_MAX_MESSAGE_LEN:
        await processing_msg.edit_text(
            full,
            parse_mode="HTML",
            reply_markup=get_ai_chat_buttons(),
        )
        return

    plain = _ai_response_to_plain(ai_response_html)
    bodies = _split_plain_text(plain, _AI_PLAIN_CHUNK)
    n = len(bodies)
    if n == 0:
        await processing_msg.edit_text(
            "❌ Порожня відповідь AI.",
            reply_markup=get_back_to_menu_button(),
        )
        return

    # Довгий HTML при короткому тексті — одне plain-повідомлення без «1/1»
    if n == 1:
        text = f"🤖 AI Асистент\n\n{plain}"
        if len(text) > _TELEGRAM_MAX_MESSAGE_LEN:
            text = text[: _TELEGRAM_MAX_MESSAGE_LEN - 1] + "…"
        await processing_msg.edit_text(text, reply_markup=get_ai_chat_buttons())
        return

    for i, body in enumerate(bodies):
        if i == 0:
            text = (
                f"🤖 AI Асистент (1/{n})\n\n"
                f"⚠️ Відповідь розбита на {n} частин (ліміт Telegram 4096 симв.).\n\n"
                f"{body}"
            )
        else:
            text = f"🤖 AI Асистент ({i + 1}/{n})\n\n{body}"

        if len(text) > _TELEGRAM_MAX_MESSAGE_LEN:
            logger.warning("AI chunk overflow %s, truncating one part", len(text))
            text = text[: _TELEGRAM_MAX_MESSAGE_LEN - 1] + "…"

        if i == 0:
            await processing_msg.edit_text(
                text,
                reply_markup=get_ai_chat_buttons() if n == 1 else None,
            )
        elif i == n - 1:
            await message.answer(text, reply_markup=get_ai_chat_buttons())
        else:
            await message.answer(text)


def _history_records_to_contents(history_records) -> list:
    """Діалог для Gemini: укорочені відповіді асистента, щоб не роздувати токени."""
    out = []
    for record in history_records:
        role = "user" if record.role == "user" else "model"
        text = record.message or ""
        if role == "model" and len(text) > _MAX_ASSISTANT_CHARS:
            text = text[:_MAX_ASSISTANT_CHARS] + "\n…"
        out.append(
            genai_types.Content(
                role=role,
                parts=[genai_types.Part(text=text)],
            )
        )
    return out


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
        "• Порівняй витрати за два роки\n"
        "• Дай поради щодо економії\n\n"
        "🤖 Асистент працює як <b>агент</b>: сам обирає запити до бази (інструменти), "
        "спочатку коротко планує відповідь — <b>не завантажує всі заправки в промпт</b> "
        "(менше токенів).\n\n"
        "💡 <i>Пам'ятаю останні репліки діалогу — можна уточнювати</i>\n"
        "📅 Точна таблиця по місяцях без AI: <code>/year</code> або <code>/year 2025</code>\n"
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
        fu = message.from_user
        db_user_id = await get_user_id_for_refuels(
            telegram_id, username=fu.username, first_name=fu.first_name
        )

        # Історія діалогу (ChatHistory.user_id = telegram_id)
        async with async_session() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.user_id == telegram_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(_AI_HISTORY_MESSAGES)
            )
            history_records = list(reversed(result.scalars().all()))

        history_contents = _history_records_to_contents(history_records)

        ai_response = await run_fuel_agent(
            user_question,
            history_contents,
            db_user_id,
        )

        if not ai_response:
            await processing_msg.edit_text(
                "❌ На жаль, не вдалося отримати відповідь від AI. Спробуйте пізніше.",
                reply_markup=get_back_to_menu_button()
            )
            return

        # Clean response from unsupported HTML tags
        # Telegram supports only: b, strong, i, em, u, ins, s, strike, del, code, pre, a
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

        await _send_ai_response_telegram(message, processing_msg, ai_response)

        logger.info(
            "AI response sent to user telegram_id=%s for question: %s",
            telegram_id,
            user_question[:50],
        )

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
