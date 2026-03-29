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

from models.database import async_session, Refuel, ChatHistory
from bot.keyboards.menu import get_back_to_menu_button, get_ai_chat_buttons
from bot.utils.user_helpers import get_user_id_for_refuels
from services.ai_vision.gemini import get_gemini_ai_response

router = Router()
logger = logging.getLogger(__name__)

# Максимальний розмір контексту заправок у символах (захист від гігантських облікових записів)
_AI_REFUEL_CONTEXT_MAX_CHARS = 900_000

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


def _sanitize_cell(value) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "/").replace("\n", " ").strip()


async def get_user_refuels_ai_context(user_id: int) -> str:
    """
    Повний набір заправок користувача для системного промпта AI: підсумок + таблиця
    всіх рядків (хронологія: від старіших до новіших).
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(Refuel.date.asc(), Refuel.id.asc())
            )
            refuels = result.scalars().all()

        if not refuels:
            return "У користувача немає жодної заправки в базі."

        total_liters = sum(r.liters for r in refuels)
        total_cost = sum(r.total_cost for r in refuels)
        total_km = sum(r.distance_from_last or 0 for r in refuels)
        with_usd = [r for r in refuels if r.total_cost_usd is not None]
        total_usd = sum(r.total_cost_usd for r in with_usd) if with_usd else None

        lines = [
            "=== ПІДСУМОК (усі записи цього користувача в базі) ===",
            (
                f"Заправок: {len(refuels)} | Літрів загалом: {total_liters:.2f} | "
                f"Сума грн: {total_cost:.2f} | Сумарний пробіг між заправками (км): {total_km}"
            ),
        ]
        if total_usd is not None:
            lines.append(
                f"USD по заправках де є курс: ${total_usd:.2f} (записів з USD: {len(with_usd)})"
            )
        lines.append("")
        lines.append(
            "Повний перелік (кожен рядок — одна заправка). Роздільник полів: | "
            "Колонки: id | дата_час | АЗС | паливо | л | грн_за_л | грн_всього | USD | "
            "одометр_км | км_від_попередньої_повної | л_на_100км | повний_бак(1/0)"
        )
        lines.append("---")

        for r in refuels:
            usd = f"{r.total_cost_usd:.2f}" if r.total_cost_usd is not None else ""
            dist = str(r.distance_from_last) if r.distance_from_last is not None else ""
            cons = f"{r.consumption:.2f}" if r.consumption is not None else ""
            ft = "1" if r.full_tank else "0"
            row = " | ".join(
                [
                    str(r.id),
                    r.date.strftime("%Y-%m-%d %H:%M"),
                    _sanitize_cell(r.station_name),
                    _sanitize_cell(r.fuel_type),
                    f"{r.liters:.2f}",
                    f"{r.price_per_liter:.2f}",
                    f"{r.total_cost:.2f}",
                    usd,
                    str(r.odometer),
                    dist,
                    cons,
                    ft,
                ]
            )
            lines.append(row)

        text = "\n".join(lines)
        if len(text) > _AI_REFUEL_CONTEXT_MAX_CHARS:
            text = text[:_AI_REFUEL_CONTEXT_MAX_CHARS] + (
                "\n\n[... обрізано: перевищено ліміт розміру контексту ...]"
            )
            logger.warning(
                "AI refuel context truncated: user_id=%s len>%s",
                user_id,
                _AI_REFUEL_CONTEXT_MAX_CHARS,
            )

        logger.info(
            "AI refuel context: user_id=%s refuels=%s chars=%s",
            user_id,
            len(refuels),
            len(text),
        )
        return text

    except Exception as e:
        logger.error(f"Error building refuel AI context: {e}", exc_info=True)
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
        "💬 Напишіть питання — у контексті для кожної відповіді передаються "
        "<b>усі ваші заправки з бази</b> (повний перелік + підсумок).\n\n"
        "💡 <i>Пам'ятаю останні репліки діалогу — можна уточнювати</i>\n"
        "📅 Точні суми по місяцях без AI: <code>/year</code> або <code>/year 2025</code>\n"
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

        # Повний набір заправок у системному промпті
        data_summary = await get_user_refuels_ai_context(db_user_id)

        # Історія діалогу (останні 20 повідомлень = до 10 пар)
        # ChatHistory.user_id is stored as Telegram id (legacy column usage)
        async with async_session() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.user_id == telegram_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(20)
            )
            history_records = result.scalars().all()
            history_records = list(reversed(history_records))  # Oldest first

        # google-genai expects types.Content, not dicts (dict has no .role for the SDK)
        gemini_history: list = []
        for record in history_records:
            role = "user" if record.role == "user" else "model"
            gemini_history.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part(text=record.message)],
                )
            )

        # Build system instruction with data and formatting rules
        system_instruction = f"""Ти — повноцінний AI-асистент з обліку палива в цьому Telegram-боті.

КРИТИЧНО: Нижче — ПОВНИЙ перелік УСІХ заправок цього користувача з бази (таблиця + підсумок). Це актуальні дані обліку. Не кажи, що «немає доступу до бази» чи «не бачиш дані»: опирайся лише на цей блок. Якщо заправок немає — відповідай відповідно (наприклад, запропонуй додати перші записи).

Можеш рахувати будь-які агрегати (по місяцях, роках, АЗС, витраті), порівнювати періоди, знаходити аномалії, тренди, середні значення — усе це вже є в таблиці нижче.

{data_summary}

Відповідай детально й по суті українською. Опирайся на конкретні id/дати/суми з таблиці, коли це доречно.
Якщо в даних є тренди чи закономірності — назви їх. Поради щодо економії — лише якщо доречно.

ВАЖЛИВО - ФОРМАТУВАННЯ:
- Використовуй ТІЛЬКИ ці HTML теги: <b>, <i>, <u>, <code>
- НЕ використовуй: DOCTYPE, html, head, body, div, span, p, h1-h6, ul, ol, li
- Заголовки: <b>Заголовок</b>
- Списки: використовуй емоджі (📊, 📈, 💡, ⚠️, ✅) замість маркерів
- Для важливих цифр: <b>123</b>
- Розділяй розділи порожнім рядком (використовуй \n\n)
- НЕ використовуй markdown **, #, - тощо
- Роби відповідь короткою і чіткою, без зайвих слів; орієнтир — до ~3000 символів, щоб вміститись в одне повідомлення Telegram (якщо користувач явно просить «повний звіт» — структуруй стисло таблицями).
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
