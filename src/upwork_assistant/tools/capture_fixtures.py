"""Разовая утилита: перехватить реальные ответы поиска Upwork и сохранить как фикстуры.

Запуск: `python -m upwork_assistant.tools.capture_fixtures`.

Не часть обычного жизненного цикла приложения. Нужна для того, чтобы
`payload_models.py`/`mapper.py` писались по реальной структуре ответа
Upwork, а не по предположению — угадывать схему недокументированного
внутреннего API было бы тем самым риском дрейфа схемы, который отдельно
оговорён в плане. Полезна и позже: если Upwork поменяет эндпоинты, этим же
скриптом переснимаются свежие фикстуры для теста маппера.

Требует уже выполненного `tools.login` (использует тот же persistent-профиль).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from upwork_assistant.adapters.upwork.browser import BrowserSession
from upwork_assistant.adapters.upwork.interceptor import ResponseCapture, search_response_predicate
from upwork_assistant.config import get_settings

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path("tests/fixtures/upwork")
WAIT_SECONDS = 15


async def run() -> None:
    settings = get_settings()
    capture = ResponseCapture(search_response_predicate)

    async with BrowserSession(
        profile_dir=settings.upwork_profile_dir,
        headless=settings.upwork_headless,
        proxy=settings.upwork_proxy,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        capture.attach(page)

        for url in settings.search_urls:
            print(f"Открываю {url}")
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(WAIT_SECONDS)

        paths = capture.dump_fixtures(FIXTURES_DIR, prefix="search")
        print(f"Сохранено {len(paths)} фикстур в {FIXTURES_DIR}")
        if not paths:
            print(
                "Перехват не дал ни одного JSON-ответа. Откройте вкладку Network в "
                "DevTools на этой же странице вручную и уточните search_response_predicate "
                "в adapters/upwork/interceptor.py под реальные эндпоинты."
            )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
