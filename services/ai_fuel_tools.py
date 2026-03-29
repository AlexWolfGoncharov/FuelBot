"""
Інструменти AI-агента: запити до refuels без повного дампу в промпт.

Схеми для Gemini задаються явно (FunctionDeclaration + Schema), без
FunctionDeclaration.from_callable — щоб не залежати від PEP 563 / inspect.
Виконання — async-обробники; виклики збирає run_fuel_agent (ручний цикл).
"""
from datetime import datetime, timedelta
from decimal import Decimal
import json
from typing import Any, Awaitable, Callable, Dict, Optional

from google.genai import types as genai_types

from sqlalchemy import func, select
from models.database import Refuel, async_session
from services.yearly_monthly_stats import aggregate_refuels_by_month


def _num(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return float(x)
    return float(x)


def _clamp_calendar_year(y: int) -> int:
    if y < 1990 or y > 2100:
        raise ValueError(f"Рік поза діапазоном: {y}")
    return y


def _clamp_int_limit(value: Any, default: int, cap: int) -> int:
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        v = default
    return max(1, min(v, cap))


def _parse_id_list_csv(raw: str) -> list[int]:
    s = (raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                out = []
                for x in arr[:25]:
                    out.append(int(x))
                return out
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    ids = []
    for part in s.replace(" ", "").split(","):
        if part.isdigit():
            ids.append(int(part))
    return ids[:25]


def _row_compact(r: Refuel) -> dict[str, Any]:
    return {
        "id": r.id,
        "date": r.date.isoformat(timespec="minutes"),
        "station": r.station_name[:120],
        "fuel": r.fuel_type[:60],
        "liters": _num(r.liters),
        "uah": _num(r.total_cost),
        "usd": _num(r.total_cost_usd),
        "odometer": r.odometer,
        "km_segment": r.distance_from_last,
        "l_per_100km": _num(r.consumption),
        "full_tank": bool(r.full_tank),
    }


def _schema_int(desc: str) -> genai_types.Schema:
    return genai_types.Schema(
        type=genai_types.Type.INTEGER,
        description=desc,
    )


def _schema_str(desc: str) -> genai_types.Schema:
    return genai_types.Schema(
        type=genai_types.Type.STRING,
        description=desc,
    )


def _build_fuel_gemini_tool() -> genai_types.Tool:
    """Один Tool з усіма function_declarations (OpenAPI-подібна схема)."""
    decls: list[genai_types.FunctionDeclaration] = [
        genai_types.FunctionDeclaration(
            name="fuel_account_overview",
            description=(
                "Підсумок обліку заправок: кількість, перша/остання дата, суми літрів, "
                "грн, км між заправками, USD (якщо є). Без списку всіх рядків."
            ),
        ),
        genai_types.FunctionDeclaration(
            name="fuel_monthly_current_year",
            description=(
                "Помісячні агрегати за поточний календарний рік: км, л/100км, грн, USD, "
                "літри, кількість заправок. Без параметрів — для «за цей рік» помісячно."
            ),
        ),
        genai_types.FunctionDeclaration(
            name="fuel_monthly_for_y",
            description=(
                "Помісячні агрегати за вказаний календарний рік (конкретний рік, наприклад 2024)."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "yr": _schema_int("Календарний рік, наприклад 2024"),
                },
                required=["yr"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="fuel_recent_refuels",
            description="Останні заправки (новіші спочатку). Обовʼязково вкажи limit.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "limit": _schema_int("Скільки записів, 1–40 (типово 15)"),
                },
                required=["limit"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="fuel_refuels_in_date_range",
            description=(
                "Заправки в інтервалі дат inclusive, формат YYYY-MM-DD. До 100 рядків."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "start_date": _schema_str("Початок YYYY-MM-DD"),
                    "end_date": _schema_str("Кінець YYYY-MM-DD"),
                },
                required=["start_date", "end_date"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="fuel_search_stations",
            description="Пошук АЗС за підрядком у назві станції.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "query": _schema_str("Підрядок у назві (мінімум 2 символи)"),
                    "limit": _schema_int("Скільки результатів, 1–20 (типово 12)"),
                },
                required=["query", "limit"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="fuel_refuels_by_ids",
            description=(
                "Деталі записів за id: через кому «340,341» або JSON-масив «[340,341]». До 25 id."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "refuel_ids": _schema_str("Список id одним рядком"),
                },
                required=["refuel_ids"],
            ),
        ),
    ]
    return genai_types.Tool(function_declarations=decls)


# Статична схема для API (не залежить від user_id)
FUEL_GEMINI_TOOL = _build_fuel_gemini_tool()

FuelHandler = Callable[..., Awaitable[dict[str, Any]]]


def make_fuel_tool_handlers(user_id: int) -> Dict[str, FuelHandler]:
    """Async-обробники за іменем функції (для ручного циклу function calling)."""

    async def fuel_account_overview() -> dict[str, Any]:
        async with async_session() as session:
            row = await session.execute(
                select(
                    func.count(Refuel.id),
                    func.min(Refuel.date),
                    func.max(Refuel.date),
                    func.coalesce(func.sum(Refuel.liters), 0),
                    func.coalesce(func.sum(Refuel.total_cost), 0),
                    func.coalesce(func.sum(Refuel.distance_from_last), 0),
                    func.coalesce(func.sum(Refuel.total_cost_usd), 0),
                    func.count(Refuel.total_cost_usd),
                ).where(Refuel.user_id == user_id)
            )
            one = row.one()
            n, dmin, dmax, liters, uah, km, usd_sum, usd_n = one
        if not n:
            return {"empty": True, "message": "Немає заправок"}
        return {
            "refuels": int(n),
            "first_date": dmin.isoformat(timespec="minutes") if dmin else None,
            "last_date": dmax.isoformat(timespec="minutes") if dmax else None,
            "total_liters": _num(liters),
            "total_uah": _num(uah),
            "total_km_between_refuels": int(km or 0),
            "total_usd": _num(usd_sum) if usd_n else None,
            "rows_with_usd": int(usd_n or 0),
        }

    async def _monthly_report(y: int) -> dict[str, Any]:
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .where(Refuel.date >= datetime(y, 1, 1))
                .where(Refuel.date < datetime(y + 1, 1, 1))
                .order_by(Refuel.date.asc())
            )
            refuels = result.scalars().all()
        rep = aggregate_refuels_by_month(list(refuels), y)
        months = []
        names = [
            "",
            "січ",
            "лют",
            "бер",
            "кві",
            "тра",
            "чер",
            "лип",
            "сер",
            "вер",
            "жов",
            "лис",
            "гру",
        ]
        for m in rep.months:
            months.append(
                {
                    "month": m.month,
                    "name": names[m.month],
                    "km": m.km,
                    "avg_l_per_100km": _num(m.avg_consumption),
                    "uah": _num(m.total_uah),
                    "usd": _num(m.total_usd) if m.usd_rows else None,
                    "liters": _num(m.liters),
                    "refuels": m.refuels_count,
                }
            )
        return {
            "year": y,
            "months": months,
            "year_totals": {
                "km": rep.total_km,
                "uah": _num(rep.total_uah),
                "usd": _num(rep.total_usd) if rep.usd_rows else None,
                "liters": _num(rep.total_liters),
                "refuels": rep.total_refuels,
                "avg_l_per_100km": _num(rep.avg_consumption_year),
            },
        }

    async def fuel_monthly_current_year() -> dict[str, Any]:
        y = datetime.now().year
        return await _monthly_report(y)

    async def fuel_monthly_for_y(yr: int) -> dict[str, Any]:
        try:
            y = _clamp_calendar_year(int(yr))
        except (TypeError, ValueError) as e:
            return {"error": str(e)}
        return await _monthly_report(y)

    async def fuel_recent_refuels(limit: int) -> dict[str, Any]:
        lim = _clamp_int_limit(limit, 15, 40)
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(Refuel.date.desc(), Refuel.id.desc())
                .limit(lim)
            )
            rows = result.scalars().all()
        return {"count": len(rows), "items": [_row_compact(r) for r in rows]}

    async def fuel_refuels_in_date_range(
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        try:
            start_dt = datetime.strptime(start_date[:10], "%Y-%m-%d")
            end_dt = datetime.strptime(end_date[:10], "%Y-%m-%d") + timedelta(days=1)
        except ValueError as e:
            return {"error": f"Невірний формат дати: {e}"}
        if end_dt <= start_dt:
            return {"error": "end_date має бути після start_date"}
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .where(Refuel.date >= start_dt)
                .where(Refuel.date < end_dt)
                .order_by(Refuel.date.asc(), Refuel.id.asc())
                .limit(100)
            )
            rows = result.scalars().all()
        return {
            "range": {"start": start_date[:10], "end": end_date[:10]},
            "returned": len(rows),
            "truncated": len(rows) >= 100,
            "items": [_row_compact(r) for r in rows],
        }

    async def fuel_search_stations(
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        q = (query or "").strip()[:80]
        if len(q) < 2:
            return {"error": "Занадто короткий запит (мінімум 2 символи)"}
        lim = _clamp_int_limit(limit, 12, 20)
        pattern = f"%{q}%"
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .where(Refuel.station_name.ilike(pattern))
                .order_by(Refuel.date.desc())
                .limit(lim)
            )
            rows = result.scalars().all()
        return {"query": q, "items": [_row_compact(r) for r in rows]}

    async def fuel_refuels_by_ids(refuel_ids: str) -> dict[str, Any]:
        ids = _parse_id_list_csv(refuel_ids)
        if not ids:
            return {"error": "Передайте непустий список id (через кому)"}
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .where(Refuel.id.in_(ids))
                .order_by(Refuel.date.asc())
            )
            rows = result.scalars().all()
        return {"items": [_row_compact(r) for r in rows]}

    return {
        "fuel_account_overview": fuel_account_overview,
        "fuel_monthly_current_year": fuel_monthly_current_year,
        "fuel_monthly_for_y": fuel_monthly_for_y,
        "fuel_recent_refuels": fuel_recent_refuels,
        "fuel_refuels_in_date_range": fuel_refuels_in_date_range,
        "fuel_search_stations": fuel_search_stations,
        "fuel_refuels_by_ids": fuel_refuels_by_ids,
    }

