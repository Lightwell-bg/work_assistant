"""Настройки приложения.

Читаются из окружения и `.env`. Модуль не выполняет ввод-вывод при импорте:
`get_settings()` вызывается явно из точки входа и из тестов.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация из переменных окружения."""

    # extra="forbid" ловит опечатки в .env и расхождение с .env.example,
    # вместо того чтобы молча их проглотить.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    # --- Upwork ---
    upwork_email: str
    upwork_password: SecretStr
    upwork_search_urls: str = Field(
        default="https://www.upwork.com/nx/search/jobs/?q=python&sort=recency",
        description='URL сохранённых поисков, разделённые ";"',
    )
    upwork_profile_dir: Path = Path("data/browser_profile")
    upwork_headless: bool = True
    upwork_proxy: str | None = None
    upwork_max_pages_per_search: int = Field(
        default=3,
        ge=1,
        description="Сколько страниц поиска (по 10 вакансий) листать за один цикл на каждый URL",
    )

    # --- OpenRouter ---
    openrouter_api_key: SecretStr
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_scoring_model: str = "openai/gpt-5-mini"
    openrouter_proposal_model: str = "openai/gpt-5"
    openrouter_daily_budget_usd: float = Field(default=2.0, gt=0)

    # --- Telegram ---
    telegram_bot_token: SecretStr
    telegram_user_id: int

    # --- Профиль фрилансера ---
    freelancer_profile_path: Path = Path("data/profile.md")

    # --- Фильтры ---
    min_score_to_notify: float = Field(default=7.0, ge=0, le=10)

    # --- Планировщик ---
    poll_interval_minutes: int = Field(default=10, ge=1)
    poll_jitter_pct: int = Field(default=40, ge=0, le=100)
    max_page_loads_per_hour: int = Field(default=20, ge=1)

    # --- База данных ---
    database_url: str = "sqlite+aiosqlite:///data/upwork_assistant.db"

    # --- Логирование ---
    log_level: str = "INFO"
    log_file: Path = Path("logs/assistant.log")
    log_json: bool = False

    # --- HTTP-сервер ---
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8077, ge=1, le=65535)

    @field_validator("upwork_proxy", mode="before")
    @classmethod
    def _empty_proxy_is_none(cls, value: str | None) -> str | None:
        """Пустая строка в .env означает «прокси не используется»."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if level not in allowed:
            raise ValueError(
                f"LOG_LEVEL должен быть одним из {sorted(allowed)}, получено {value!r}"
            )
        return level

    @property
    def search_urls(self) -> list[str]:
        """Список URL сохранённых поисков."""
        return [url.strip() for url in self.upwork_search_urls.split(";") if url.strip()]


@lru_cache
def get_settings() -> Settings:
    """Настройки приложения (кэшируются на процесс)."""
    return Settings()
