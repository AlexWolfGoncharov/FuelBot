"""
Точна агрегація заправок по місяцях за календарний рік (Python/Decimal, не AI).
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from models.database import Refuel


@dataclass
class MonthBucket:
    month: int
    refuels_count: int
    liters: Decimal
    total_uah: Decimal
    total_usd: Decimal
    usd_rows: int
    km: int
    avg_consumption: Optional[Decimal]


@dataclass
class YearlyReport:
    year: int
    months: List[MonthBucket]
    total_refuels: int
    total_liters: Decimal
    total_uah: Decimal
    total_usd: Decimal
    usd_rows: int
    total_km: int
    avg_consumption_year: Optional[Decimal]


def aggregate_refuels_by_month(refuels: List[Refuel], year: int) -> YearlyReport:
    """
    Групує заправки за полем date (календарний місяць у зазначеному році).
    Середня витрата — середнє арифметичне по заправках, де consumption не NULL.
    """
    buckets: dict[int, list] = {m: [] for m in range(1, 13)}

    for r in refuels:
        if r.date.year != year:
            continue
        buckets[r.date.month].append(r)

    months_out: List[MonthBucket] = []
    total_refuels = 0
    total_liters = Decimal("0")
    total_uah = Decimal("0")
    total_usd = Decimal("0")
    usd_rows_year = 0
    total_km = 0
    all_consumptions: List[Decimal] = []

    for month in range(1, 13):
        rows = buckets[month]
        if not rows:
            continue

        liters = sum((x.liters for x in rows), Decimal("0"))
        uah = sum((x.total_cost for x in rows), Decimal("0"))
        usd_sum = Decimal("0")
        usd_n = 0
        for x in rows:
            if x.total_cost_usd is not None:
                usd_sum += x.total_cost_usd
                usd_n += 1
        km = sum((x.distance_from_last or 0 for x in rows))
        cons_vals = [x.consumption for x in rows if x.consumption is not None]
        avg_c: Optional[Decimal] = None
        if cons_vals:
            avg_c = sum(cons_vals, Decimal("0")) / Decimal(len(cons_vals))

        months_out.append(
            MonthBucket(
                month=month,
                refuels_count=len(rows),
                liters=liters,
                total_uah=uah,
                total_usd=usd_sum,
                usd_rows=usd_n,
                km=km,
                avg_consumption=avg_c,
            )
        )

        total_refuels += len(rows)
        total_liters += liters
        total_uah += uah
        total_usd += usd_sum
        usd_rows_year += usd_n
        total_km += km
        all_consumptions.extend(cons_vals)

    avg_year: Optional[Decimal] = None
    if all_consumptions:
        avg_year = sum(all_consumptions, Decimal("0")) / Decimal(len(all_consumptions))

    return YearlyReport(
        year=year,
        months=months_out,
        total_refuels=total_refuels,
        total_liters=total_liters,
        total_uah=total_uah,
        total_usd=total_usd,
        usd_rows=usd_rows_year,
        total_km=total_km,
        avg_consumption_year=avg_year,
    )


def format_yearly_report_html(report: YearlyReport) -> str:
    """Текст відповіді для Telegram (HTML)."""
    names = {
        1: "Січень",
        2: "Лютий",
        3: "Березень",
        4: "Квітень",
        5: "Травень",
        6: "Червень",
        7: "Липень",
        8: "Серпень",
        9: "Вересень",
        10: "Жовтень",
        11: "Листопад",
        12: "Грудень",
    }

    lines = [
        f"📅 <b>Статистика за {report.year} рік</b> (кожен місяць окремо)\n",
        "Колонки: місяць · проїхав км · середня витрата л/100км · грн · USD · літри · заправок\n",
    ]

    for m in report.months:
        name = names[m.month]
        cons = f"{m.avg_consumption:.2f}" if m.avg_consumption is not None else "—"
        usd_part = f"${m.total_usd:.2f}" if m.usd_rows > 0 else "—"
        lines.append(
            f"\n<b>{name}</b>\n"
            f"🛣 Проїхав: <b>{m.km}</b> км\n"
            f"⛽ Середня витрата: <b>{cons}</b> л/100км\n"
            f"💵 Витрати: <b>{m.total_uah:.2f}</b> грн · <b>{usd_part}</b> USD\n"
            f"⛽ Літри: <b>{m.liters:.2f}</b> л · 📝 Заправок: <b>{m.refuels_count}</b>"
        )

    if not report.months:
        lines.append("\n<i>Немає заправок за цей рік.</i>")
        return "\n".join(lines)

    lines.append("\n──────────────")
    y_cons = (
        f"{report.avg_consumption_year:.2f}"
        if report.avg_consumption_year is not None
        else "—"
    )
    y_usd = f"${report.total_usd:.2f}" if report.usd_rows > 0 else "—"
    lines.append(
        f"\n<b>Разом за рік:</b>\n"
        f"🛣 Проїхав: <b>{report.total_km}</b> км\n"
        f"⛽ Середня витрата (по заправках з даними): <b>{y_cons}</b> л/100км\n"
        f"💵 Витрати: <b>{report.total_uah:.2f}</b> грн · <b>{y_usd}</b> USD\n"
        f"⛽ Літри: <b>{report.total_liters:.2f}</b> л · 📝 Заправок: <b>{report.total_refuels}</b>"
    )

    return "\n".join(lines)
