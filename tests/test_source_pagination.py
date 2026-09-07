"""Тесты чистой логики пагинации `adapters/upwork/source.py`.

`_poll_search`/`_poll_one`/`poll()` требуют живой браузер (Patchright) и по
условиям задачи production-код менять нельзя ради тестируемости без
браузера — как и раньше для `UpworkJobSource.poll()`. Здесь проверяется
только то, что тестируемо без браузера: `_has_more_pages` (чистая функция)
и настройка лимита страниц.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from upwork_assistant.adapters.upwork.source import _has_more_pages
from upwork_assistant.config import Settings


def test_has_more_pages_true_when_offset_plus_count_below_total() -> None:
    assert _has_more_pages({"total": 25, "offset": 10, "count": 10}, 10) is True


def test_has_more_pages_false_when_offset_plus_count_reaches_total() -> None:
    assert _has_more_pages({"total": 20, "offset": 10, "count": 10}, 10) is False


def test_has_more_pages_false_on_missing_keys() -> None:
    assert _has_more_pages({}, 10) is False


def test_has_more_pages_false_on_non_numeric_values() -> None:
    assert _has_more_pages({"total": "not-a-number", "offset": "also-not"}, 10) is False


def test_upwork_max_pages_per_search_defaults_to_three(settings: Settings) -> None:
    assert settings.upwork_max_pages_per_search == 3


def test_upwork_max_pages_per_search_rejects_values_below_one(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            upwork_email="test@example.com",
            upwork_password=SecretStr("upwork-password"),
            openrouter_api_key=SecretStr("sk-or-test"),
            telegram_bot_token=SecretStr("123456:test-token"),
            telegram_user_id=42,
            upwork_profile_dir=tmp_path / "browser_profile",
            freelancer_profile_path=tmp_path / "profile.md",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
            log_file=tmp_path / "test.log",
            upwork_max_pages_per_search=0,
        )
