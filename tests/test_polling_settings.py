"""Тесты применения override'ов интервала опроса из `app_state` при старте."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.adapters.upwork.polling import PollingPolicy
from upwork_assistant.services.polling_settings import (
    POLL_INTERVAL_MINUTES_KEY,
    POLL_JITTER_PCT_KEY,
    load_polling_overrides,
    save_polling_settings,
)


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'polling_settings_test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


def _make_policy(interval_minutes: int = 10, jitter_pct: int = 40) -> PollingPolicy:
    return PollingPolicy(
        interval_minutes=interval_minutes,
        jitter_pct=jitter_pct,
        max_page_loads_per_hour=20,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_load_overrides_does_nothing_when_app_state_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    policy = _make_policy(interval_minutes=10, jitter_pct=40)

    await load_polling_overrides(session_factory, policy)

    assert policy.interval_minutes == 10
    assert policy.jitter_pct == 40


async def test_save_then_load_applies_both_overrides(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await save_polling_settings(uow, interval_minutes=25, jitter_pct=15)

    policy = _make_policy(interval_minutes=10, jitter_pct=40)
    await load_polling_overrides(session_factory, policy)

    assert policy.interval_minutes == 25
    assert policy.jitter_pct == 15


async def test_load_applies_only_the_override_that_is_present(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ключи независимы: если сохранён только один, второй остаётся из .env."""
    async with unit_of_work(session_factory) as uow:
        await uow.app_state.set(POLL_INTERVAL_MINUTES_KEY, "25")

    policy = _make_policy(interval_minutes=10, jitter_pct=40)
    await load_polling_overrides(session_factory, policy)

    assert policy.interval_minutes == 25
    assert policy.jitter_pct == 40


async def test_save_persists_values_as_strings_reloadable_after_process_restart(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Имитация рестарта процесса: новый PollingPolicy с настройками из .env,
    override из app_state применяется поверх них при следующем старте."""
    async with unit_of_work(session_factory) as uow:
        await save_polling_settings(uow, interval_minutes=5, jitter_pct=0)

    fresh_policy = _make_policy(interval_minutes=10, jitter_pct=40)
    await load_polling_overrides(session_factory, fresh_policy)

    assert fresh_policy.interval_minutes == 5
    assert fresh_policy.jitter_pct == 0


def test_key_names() -> None:
    """Ключи app_state — стабильные строки; их смена без миграции потеряет
    уже сохранённые пользователем настройки на существующих установках."""
    assert POLL_INTERVAL_MINUTES_KEY == "poll_interval_minutes"
    assert POLL_JITTER_PCT_KEY == "poll_jitter_pct"
