"""
Легкий HTTP-сервер (aiohttp) для тимчасових HTML-дашбордів на тому ж PORT, що й Railway.
"""
from __future__ import annotations

import logging
import os

from aiohttp import web

from config.settings import settings
from services.temp_dashboard_store import store

logger = logging.getLogger(__name__)


async def _handle_dashboard(request: web.Request) -> web.Response:
    token = request.match_info.get("token", "")
    html = await store.get_html(token)
    if html is None:
        body = """<!DOCTYPE html>
<html lang="uk"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Недійсне посилання</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f1419;color:#e7ecf3;padding:2rem;line-height:1.5;max-width:36rem;margin:0 auto;}
</style></head><body>
<h1>Посилання недійсне або прострочене</h1>
<p>Дашборд зберігається до 24 годин після створення. Згенеруйте новий у боті: <code>/dashboard</code></p>
</body></html>"""
        return web.Response(text=body, content_type="text/html", charset="utf-8")

    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def _health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _root(_request: web.Request) -> web.Response:
    """Корінь для перевірок провайдера; без HTML."""
    return web.Response(text="FuelBot: use /health or bot /dashboard link.")


async def start_web_server() -> None:
    if not settings.enable_web_dashboard:
        logger.info("Web dashboard disabled (enable_web_dashboard=false)")
        return

    app = web.Application()
    app.router.add_get("/", _root)
    app.router.add_get("/d/{token}", _handle_dashboard)
    app.router.add_get("/health", _health)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Dashboard HTTP listening on 0.0.0.0:%s (/d/{{token}}, /health)", port)
