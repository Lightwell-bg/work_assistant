"""BrowserSession: владеет persistent-профилем Chromium через Patchright.

Стелс работает только через `launch_persistent_context` с каталогом профиля
на диске — обычный `launch()` открывает новый контекст каждый раз и не
хранит cookies и clearance-куку Cloudflare между запусками, из-за чего
каждый цикл выглядел бы для Cloudflare как новое устройство.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import TracebackType

from patchright.async_api import BrowserContext, Playwright, ProxySettings, async_playwright

logger = logging.getLogger(__name__)


class BrowserSession:
    """Асинхронный контекст-менеджер: on-enter даёт persistent `BrowserContext`."""

    def __init__(self, profile_dir: Path, headless: bool, proxy: str | None = None) -> None:
        self._profile_dir = profile_dir
        self._headless = headless
        self._proxy = proxy
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> BrowserContext:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()

        proxy: ProxySettings | None = (
            {"server": self._proxy} if self._proxy is not None else None
        )

        logger.info("Открываю persistent-профиль браузера: %s", self._profile_dir)
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir),
            headless=self._headless,
            # Реальный канал Chrome, а не бандленный Chromium — часть стелса
            # Patchright: у бандленного Chromium детектируемые артефакты сборки.
            channel="chrome",
            proxy=proxy,
        )
        return self._context

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
