"""Проверка залогиненности и детект challenge (устройство/капча/Cloudflare).

Эвристики (URL после редиректа, наличие текста подтверждения) — первое
приближение. Правятся по факту первого реального ассистированного входа
(`tools/login.py`) — Upwork не документирует эти состояния публично.
"""

from __future__ import annotations

import logging

from patchright.async_api import Page

from upwork_assistant.domain.errors import SessionInvalidError

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://www.upwork.com/nx/find-work/"
LOGIN_URL_FRAGMENT = "/ab/account-security/login"
CHALLENGE_TEXT_PATTERN = "verify|confirm your identity|enter the code|security check"


def looks_authenticated(current_url: str) -> bool:
    """Пассивная проверка по текущему URL, без навигации.

    Для поллинга во время ассистированного входа: пока человек логинится,
    страницу нельзя дёргать `goto()` на каждой проверке — это сбрасывает
    форму и фокус ввода. `is_logged_in()` (с навигацией) вызывается только
    один раз, когда эта пассивная проверка уже похожа на успех.
    """
    return LOGIN_URL_FRAGMENT not in current_url


async def is_logged_in(page: Page) -> bool:
    """Перейти на дашборд и проверить, что нас не отбросило на логин.

    Навигирует переданную страницу — для активного входа человека вызывать
    на отдельной вкладке (`context.new_page()`), а не на той, где он вводит
    логин/пароль или код подтверждения.
    """
    await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
    if LOGIN_URL_FRAGMENT in page.url:
        return False
    return not await _looks_like_challenge(page)


async def _looks_like_challenge(page: Page) -> bool:
    try:
        count = await page.get_by_text(CHALLENGE_TEXT_PATTERN, exact=False).count()
    except Exception:
        logger.debug("Не удалось проверить страницу на challenge", exc_info=True)
        return False
    return count > 0


async def ensure_logged_in(page: Page) -> None:
    """Для headless-циклов опроса: сессия должна быть уже валидна.

    В отличие от ассистированного входа здесь нет человека, который введёт
    код — если сессия невалидна, это `SessionInvalidError`, требующая
    повторного запуска `tools.login` вручную, а не тихого зависания.
    """
    if not await is_logged_in(page):
        raise SessionInvalidError(
            "Сессия Upwork невалидна или требует подтверждения устройства. "
            "Запустите `python -m upwork_assistant.tools.login` для повторного входа."
        )
