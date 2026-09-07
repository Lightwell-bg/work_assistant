"""Тесты разбора конфигурации."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from upwork_assistant.config import Settings


def test_search_urls_split_on_semicolon(settings: Settings) -> None:
    settings = settings.model_copy(update={"upwork_search_urls": "https://a/ ; https://b/ ;"})

    assert settings.search_urls == ["https://a/", "https://b/"]


def test_empty_proxy_becomes_none(settings: Settings) -> None:
    assert (
        Settings.model_validate({**settings.model_dump(), "upwork_proxy": "   "}).upwork_proxy
        is None
    )


def test_log_level_is_normalised(settings: Settings) -> None:
    assert (
        Settings.model_validate({**settings.model_dump(), "log_level": "debug"}).log_level
        == "DEBUG"
    )


def test_unknown_log_level_is_rejected(settings: Settings) -> None:
    with pytest.raises(ValidationError, match="LOG_LEVEL"):
        Settings.model_validate({**settings.model_dump(), "log_level": "LOUD"})


def test_secrets_are_not_exposed_in_repr(settings: Settings) -> None:
    """Секреты не должны утекать в логи через repr модели."""
    assert "upwork-password" not in repr(settings)
    assert "sk-or-test" not in repr(settings)
