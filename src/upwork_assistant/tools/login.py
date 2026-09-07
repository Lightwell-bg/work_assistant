"""Разовый ассистированный вход в Upwork.

Запуск: `python -m upwork_assistant.tools.login`.

Открывает headful Chromium на persistent-профиле (`Settings.upwork_profile_dir`).
Человек логинится сам и, если Upwork это потребует, вводит код подтверждения
устройства прямо в открывшемся окне. Скрипт лишь ждёт и проверяет результат —
он не вводит логин/пароль автоматически и не имитирует ввод кода: страница
для человека полностью реальна, что и снижает шанс сработать как бот.

После успеха профиль на диске хранит сессию и Cloudflare-clearance куку —
headless-циклы опроса переиспользуют его без повторного входа, пока сессия
не протухнет (тогда `adapters.upwork.auth.ensure_logged_in` поднимет
`SessionInvalidError` и попросит перезапустить эту команду).
"""

from __future__ import annotations

import asyncio
import logging

from upwork_assistant.adapters.upwork.auth import DASHBOARD_URL, is_logged_in, looks_authenticated
from upwork_assistant.adapters.upwork.browser import BrowserSession
from upwork_assistant.config import get_settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3
CONFIRM_DEBOUNCE_SECONDS = 2
TIMEOUT_SECONDS = 600


async def run() -> None:
    settings = get_settings()
    async with BrowserSession(
        profile_dir=settings.upwork_profile_dir,
        headless=False,
        proxy=settings.upwork_proxy,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DASHBOARD_URL)

        print("Войдите в Upwork в этом окне сами.")
        print("Если Upwork запросит код подтверждения устройства — введите его там же.")
        print(f"Жду подтверждения входа до {TIMEOUT_SECONDS} секунд...")
        print("Эта вкладка больше не будет перезагружаться — вводите спокойно.")

        elapsed = 0
        while elapsed < TIMEOUT_SECONDS:
            # Пассивная проверка по URL текущей вкладки — без навигации,
            # чтобы не сбрасывать форму логина, пока человек её заполняет.
            if looks_authenticated(page.url):
                await asyncio.sleep(CONFIRM_DEBOUNCE_SECONDS)
                # Подтверждаем на отдельной вкладке: is_logged_in() делает
                # goto(), а трогать вкладку человека навигацией нельзя.
                check_page = await context.new_page()
                try:
                    confirmed = await is_logged_in(check_page)
                finally:
                    await check_page.close()
                if confirmed:
                    print(f"Вход выполнен. Профиль сохранён в {settings.upwork_profile_dir}")
                    return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

        raise TimeoutError(
            f"Вход не подтверждён за {TIMEOUT_SECONDS} секунд. Запустите команду заново."
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
