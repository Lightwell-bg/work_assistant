"""Настройки интервала опроса, живущие в `app_state` поверх `.env`.

Та же таблица key/value, что и отметка разового засева поисков
(`search_seed.SEARCH_SEED_MARKER_KEY`) — общее хранилище системных
настроек процесса, не привязанных к доменной сущности. Два независимых
ключа, а не один составной: правка через панель всегда отправляет оба
значения разом (`save_polling_settings`), но при чтении на старте
(`load_polling_overrides`) сохранённый только один ключ не должен сбрасывать
второй к значению из `.env` — так же, как `set_interval_minutes`/
`set_jitter_pct` у `PollingPolicy` меняют каждый своё поле независимо.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.uow import UnitOfWork, unit_of_work
from upwork_assistant.adapters.upwork.polling import PollingPolicy

POLL_INTERVAL_MINUTES_KEY = "poll_interval_minutes"
POLL_JITTER_PCT_KEY = "poll_jitter_pct"


async def load_polling_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    policy: PollingPolicy,
) -> None:
    """Применить сохранённые в `app_state` override'ы к уже собранному `policy`.

    Вызывается один раз при старте процесса, до `polling_runner.start()` —
    ровно как `seed_searches_from_env`, по той же причине: `build_container()`
    не должен трогать БД, иначе тесты, строящие контейнер через `TestClient`,
    делали бы это на каждый запуск.
    """
    async with unit_of_work(session_factory) as uow:
        interval_raw = await uow.app_state.get(POLL_INTERVAL_MINUTES_KEY)
        jitter_raw = await uow.app_state.get(POLL_JITTER_PCT_KEY)

    if interval_raw is not None:
        policy.set_interval_minutes(int(interval_raw))
    if jitter_raw is not None:
        policy.set_jitter_pct(int(jitter_raw))


async def save_polling_settings(uow: UnitOfWork, *, interval_minutes: int, jitter_pct: int) -> None:
    """Сохранить оба значения разом — форма панели всегда отправляет их вместе."""
    await uow.app_state.set(POLL_INTERVAL_MINUTES_KEY, str(interval_minutes))
    await uow.app_state.set(POLL_JITTER_PCT_KEY, str(jitter_pct))
