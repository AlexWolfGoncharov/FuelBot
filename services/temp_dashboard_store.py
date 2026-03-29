"""
Тимчасове зберігання HTML-дашбордів у пам'яті процесу (TTL за замовчуванням 24 год).
Підходить для одного інстансу (Railway). Після рестарту посилання не дійсні.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Optional

logger = logging.getLogger(__name__)


class TempDashboardStore:
    def __init__(self, ttl_seconds: int = 86400):
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    def _purge_sync(self) -> None:
        now = time.time()
        dead = [k for k, (exp, _) in self._data.items() if exp < now]
        for k in dead:
            del self._data[k]
        if dead:
            logger.info("Temp dashboard: purged %s expired token(s)", len(dead))

    async def put_html(self, html: str) -> str:
        token = secrets.token_urlsafe(24)
        expires = time.time() + self._ttl
        async with self._lock:
            self._purge_sync()
            self._data[token] = (expires, html)
        logger.info("Temp dashboard: stored token, expires in %ss", self._ttl)
        return token

    async def get_html(self, token: str) -> Optional[str]:
        async with self._lock:
            self._purge_sync()
            item = self._data.get(token)
            if not item:
                return None
            exp, html = item
            if time.time() > exp:
                del self._data[token]
                return None
            return html


from config.settings import settings

store = TempDashboardStore(settings.dashboard_ttl_seconds)
