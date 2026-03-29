"""
Тимчасовий HTML-дашборд за посиланням (/dashboard).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from bot.keyboards.menu import get_back_to_menu_button
from bot.utils.user_helpers import get_user_id_for_refuels
from config.settings import settings
from models.database import Refuel, async_session
from services.dashboard_html import build_dashboard_page
from services.refuel_calculator import recalculate_refuel_stats
from services.temp_dashboard_store import store

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("dashboard"))
async def cmd_dashboard(message: Message) -> None:
    """Згенерувати тимчасовий HTML-дашборд і надіслати посилання (живе до 24 год)."""
    if not settings.enable_web_dashboard:
        await message.answer(
            "Веб-дашборд вимкнено (enable_web_dashboard).",
            reply_markup=get_back_to_menu_button(),
        )
        return

    u = message.from_user
    user_id = await get_user_id_for_refuels(u.id, u.username, u.first_name)

    try:
        await recalculate_refuel_stats(user_id)
        async with async_session() as session:
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(Refuel.date.desc())
            )
            refuels = result.scalars().all()

        if not refuels:
            await message.answer(
                "Немає заправок — дашборд порожній.",
                reply_markup=get_back_to_menu_button(),
            )
            return

        year = datetime.now().year
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=settings.dashboard_ttl_seconds)

        html = build_dashboard_page(
            list(refuels),
            generated_at=now,
            expires_at=expires,
            year=year,
        )
        token = await store.put_html(html)

        base = (settings.public_base_url or "").strip().rstrip("/")
        if not base:
            await message.answer(
                "⚠️ Дашборд збережено, але в змінних середовища не задано "
                "<b>PUBLIC_BASE_URL</b> (публічний URL вашого сервісу на Railway, "
                "наприклад <code>https://xxx.up.railway.app</code> без слешу в кінці). "
                "Після додавання змінної перезапустіть сервіс і викличте /dashboard знову.",
                parse_mode="HTML",
                reply_markup=get_back_to_menu_button(),
            )
            return

        url = f"{base}/d/{token}"
        ttl_h = settings.dashboard_ttl_seconds // 3600
        await message.answer(
            f"📊 <b>Тимчасовий дашборд</b> (до ~{ttl_h} год)\n\n"
            f"<a href=\"{url}\">Відкрити в браузері</a>\n\n"
            f"<code>{url}</code>\n\n"
            f"Посилання одноразове за токеном; не публікуйте публічно.",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_back_to_menu_button(),
        )
        logger.info("Dashboard issued for user_id=%s", user_id)

    except Exception as e:
        logger.error("dashboard: %s", e, exc_info=True)
        await message.answer(
            f"❌ Помилка: {e}",
            reply_markup=get_back_to_menu_button(),
        )
