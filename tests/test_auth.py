"""Тесты `is_logged_in`/`ensure_logged_in` на фейковой Patchright `Page`.

Без реального браузера: `goto()` подставляет управляемый `page.url`,
`get_by_text()` возвращает фейковый локатор с управляемым `count()`.
"""

from __future__ import annotations

import pytest

from upwork_assistant.adapters.upwork.auth import (
    DASHBOARD_URL,
    LOGIN_URL_FRAGMENT,
    ensure_logged_in,
    is_logged_in,
)
from upwork_assistant.domain.errors import SessionInvalidError

LOGIN_URL = f"https://www.upwork.com{LOGIN_URL_FRAGMENT}"


class FakeLocator:
    def __init__(self, count: int) -> None:
        self._count = count

    async def count(self) -> int:
        return self._count


class FakePage:
    """`goto_url` — куда редиректит Upwork; `challenge_count` — что найдёт `get_by_text`."""

    def __init__(self, *, goto_url: str, challenge_count: int = 0) -> None:
        self._goto_url = goto_url
        self._challenge_count = challenge_count
        self.url = ""
        self.goto_calls: list[str] = []

    async def goto(self, url: str, wait_until: str | None = None) -> None:
        self.goto_calls.append(url)
        self.url = self._goto_url

    def get_by_text(self, pattern: str, exact: bool = False) -> FakeLocator:
        return FakeLocator(self._challenge_count)


async def test_is_logged_in_false_when_redirected_to_login() -> None:
    page = FakePage(goto_url=LOGIN_URL)

    assert await is_logged_in(page) is False  # type: ignore[arg-type]


async def test_is_logged_in_false_when_dashboard_but_challenge_present() -> None:
    page = FakePage(goto_url=DASHBOARD_URL, challenge_count=1)

    assert await is_logged_in(page) is False  # type: ignore[arg-type]


async def test_is_logged_in_true_when_dashboard_and_no_challenge() -> None:
    page = FakePage(goto_url=DASHBOARD_URL, challenge_count=0)

    assert await is_logged_in(page) is True  # type: ignore[arg-type]


async def test_ensure_logged_in_raises_when_not_logged_in() -> None:
    page = FakePage(goto_url=LOGIN_URL)

    with pytest.raises(SessionInvalidError):
        await ensure_logged_in(page)  # type: ignore[arg-type]


async def test_ensure_logged_in_returns_none_when_logged_in() -> None:
    page = FakePage(goto_url=DASHBOARD_URL, challenge_count=0)

    await ensure_logged_in(page)  # type: ignore[arg-type]  # не должно бросать
