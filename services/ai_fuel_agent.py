"""
AI-агент з інструментами Gemini: явні FunctionDeclaration + ручний цикл async-викликів.

Вбудований automatic function calling вимкнено: він покладається на from_callable
і не підходить для наших async-обробників; виконання — у циклі після кожного generate_content.
"""
from __future__ import annotations

import logging
from typing import Any

from google.genai import types as genai_types

from config.settings import settings
from services.ai_fuel_tools import FUEL_GEMINI_TOOL, make_fuel_tool_handlers
from services.ai_vision.gemini import client

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 8

_AGENT_SYSTEM = """Ти — аналітик витрат на паливо в Telegram-боті FuelBot.

ПОВЕДІНКА (економія токенів):
1) Спочатку коротко сформулюй <b>План</b> (2–4 речення): що потрібно зʼясувати та які інструменти варто викликати. Не вигадуй цифри до викликів.
2) Викликай лише потрібні інструменти; уникай зайвих повторних запитів. Якщо достатньо зведення — не тягни сотні рядків.
3) У <b>Відповіді</b> опирайся лише на результати інструментів. Якщо даних не вистачило — викликай інструмент ще раз з іншими параметрами.
4) Точні таблиці по місяцях за рік також доступні в боті командою /year — можна згадати, якщо доречно.

ІНСТРУМЕНТИ (ліміти — цілі числа; дати та id — рядки):
- fuel_account_overview — загальні суми та діапазон дат.
- fuel_monthly_current_year — помісячно за поточний календарний рік, без параметрів.
- fuel_monthly_for_y(yr) — помісячно за конкретний рік; yr — ціле число (наприклад 2024).
- fuel_recent_refuels(limit) — limit цілим числом, наприклад 15.
- fuel_refuels_in_date_range — інтервал дат YYYY-MM-DD.
- fuel_search_stations(query, limit) — limit цілим числом, наприклад 12.
- fuel_refuels_by_ids — id через кому "340,341" або JSON "[340,341]".

ФОРМАТ ВИХОДУ (Telegram HTML):
- Лише теги: <b>, <i>, <u>, <code>. Без markdown **, без HTML-документа.
- Структура відповіді: <b>План</b> → (після інструментів) основна відповідь з цифрами та висновками.
- Будь стислим; орієнтир до ~2500 символів, якщо користувач не просить «все детально».
"""


def _function_call_args_to_dict(args: Any) -> dict[str, Any]:
    if args is None:
        return {}
    if isinstance(args, dict):
        return dict(args)
    try:
        return dict(args)
    except (TypeError, ValueError):
        return {}


def _extract_function_calls(
    response: genai_types.GenerateContentResponse,
) -> list[genai_types.FunctionCall]:
    out: list[genai_types.FunctionCall] = []
    if not response.candidates:
        return out
    cand0 = response.candidates[0]
    if not cand0.content or not cand0.content.parts:
        return out
    for part in cand0.content.parts:
        if part.function_call:
            out.append(part.function_call)
    return out


async def _dispatch_fuel_tool(
    name: str,
    raw_args: Any,
    handlers: dict[str, Any],
) -> dict[str, Any]:
    fn = handlers.get(name)
    if not fn:
        return {"error": f"Невідомий інструмент: {name}"}
    args = _function_call_args_to_dict(raw_args)
    try:
        if name == "fuel_account_overview":
            return await fn()
        if name == "fuel_monthly_current_year":
            return await fn()
        if name == "fuel_monthly_for_y":
            yr = args.get("yr", 0)
            return await fn(int(float(yr)))
        if name == "fuel_recent_refuels":
            lim = args.get("limit", 15)
            return await fn(int(float(lim)))
        if name == "fuel_refuels_in_date_range":
            return await fn(
                str(args.get("start_date", "")),
                str(args.get("end_date", "")),
            )
        if name == "fuel_search_stations":
            return await fn(
                str(args.get("query", "")),
                int(float(args.get("limit", 12))),
            )
        if name == "fuel_refuels_by_ids":
            return await fn(str(args.get("refuel_ids", "")))
    except Exception as e:
        logger.warning("Fuel tool %s failed: %s", name, e)
        return {"error": str(e)}
    return {"error": f"Немає маршруту для {name}"}


async def run_fuel_agent(
    user_question: str,
    history_contents: list[genai_types.Content],
    user_id: int,
) -> str:
    """
    Цикл: generate_content → якщо є function_call, async-виконання → function_response → знову.
    """
    handlers = make_fuel_tool_handlers(user_id)
    config = genai_types.GenerateContentConfig(
        temperature=0.35,
        top_p=0.95,
        max_output_tokens=4096,
        system_instruction=_AGENT_SYSTEM,
        tools=[FUEL_GEMINI_TOOL],
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
            disable=True,
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

    last_text = ""
    for round_i in range(_MAX_TOOL_ROUNDS):
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=config,
        )
        last_text = (response.text or "").strip()
        fcalls = _extract_function_calls(response)
        if not fcalls:
            if last_text:
                return last_text
            break

        response_parts: list[genai_types.Part] = []
        for fc in fcalls:
            name = fc.name or ""
            result = await _dispatch_fuel_tool(name, fc.args, handlers)
            response_parts.append(
                genai_types.Part.from_function_response(
                    name=name,
                    response={"result": result},
                )
            )

        if not response.candidates or not response.candidates[0].content:
            break
        contents.append(response.candidates[0].content)
        contents.append(
            genai_types.Content(role="user", parts=response_parts),
        )
        logger.info(
            "Fuel agent: tool round=%s calls=%s",
            round_i + 1,
            [fc.name for fc in fcalls],
        )

    if last_text:
        return last_text
    return "Не вдалося сформувати відповідь. Спробуйте коротше питання або /year для таблиці по місяцях."
