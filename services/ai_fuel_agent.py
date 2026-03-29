"""
AI-агент з інструментами (Gemini automatic function calling) — без повного дампу заправок у промпт.
"""
from __future__ import annotations

import logging

from google.genai import types as genai_types

from config.settings import settings
from services.ai_fuel_tools import make_fuel_tools
from services.ai_vision.gemini import client

logger = logging.getLogger(__name__)

_AGENT_SYSTEM = """Ти — аналітик витрат на паливо в Telegram-боті FuelBot.

ПОВЕДІНКА (економія токенів):
1) Спочатку коротко сформулюй <b>План</b> (2–4 речення): що потрібно зʼясувати та які інструменти варто викликати. Не вигадуй цифри до викликів.
2) Викликай лише потрібні інструменти; уникай зайвих повторних запитів. Якщо достатньо зведення — не тягни сотні рядків.
3) У <b>Відповіді</b> опирайся лише на результати інструментів. Якщо даних не вистачило — викликай інструмент ще раз з іншими параметрами.
4) Точні таблиці по місяцях за рік також доступні в боті командою /year — можна згадати, якщо доречно.

ІНСТРУМЕНТИ:
- fuel_account_overview — загальні суми та діапазон дат.
- fuel_monthly_for_year — помісячні агрегати за календарний рік.
- fuel_recent_refuels — останні N заправок.
- fuel_refuels_in_date_range — інтервал дат YYYY-MM-DD.
- fuel_search_stations — пошук АЗС за підрядком.
- fuel_refuels_by_ids — деталі за id записів.

ФОРМАТ ВИХОДУ (Telegram HTML):
- Лише теги: <b>, <i>, <u>, <code>. Без markdown **, без HTML-документа.
- Структура відповіді: <b>План</b> → (після інструментів) основна відповідь з цифрами та висновками.
- Будь стислим; орієнтир до ~2500 символів, якщо користувач не просить «все детально».
"""


async def run_fuel_agent(
    user_question: str,
    history_contents: list[genai_types.Content],
    user_id: int,
) -> str:
    """
    Запускає Gemini з AFC: модель викликає Python-інструменти, поки не сформує текстову відповідь.

    Args:
        user_question: поточне питання користувача
        history_contents: попередні ходи діалогу (user/model), без поточного питання
        user_id: внутрішній id користувача в БД
    """
    tools = make_fuel_tools(user_id)
    config = genai_types.GenerateContentConfig(
        temperature=0.35,
        top_p=0.95,
        max_output_tokens=4096,
        system_instruction=_AGENT_SYSTEM,
        tools=tools,
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=8,
        ),
    )

    contents: list = list(history_contents)
    contents.append(
        genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_question)],
        )
    )

    logger.info(
        "Fuel agent: user_id=%s history_turns=%s q_len=%s",
        user_id,
        len(history_contents),
        len(user_question),
    )

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=config,
    )

    text = (response.text or "").strip()
    if not text:
        return "Не вдалося сформувати відповідь. Спробуйте коротше питання або /year для таблиці по місяцях."
    return text
