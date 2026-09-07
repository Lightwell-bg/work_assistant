"""Тест конструктора `UpworkJobSource` на приём общего `PollingPolicy`.

`test_polling.py` уже полностью покрывает саму логику `PollingPolicy`
(`can_load_page()`/`record_page_load()`/часовое окно/circuit breaker) —
дублировать её здесь незачем. `UpworkJobSource.poll()`/`_poll_one()`
требуют живой `BrowserContext` (Patchright) и по условиям задачи
production-код менять нельзя, чтобы облегчить тестирование без браузера,
поэтому единственное, что здесь имеет смысл проверить без реального
браузера — что конструктор действительно принимает и сохраняет переданный
экземпляр `PollingPolicy` (тот же самый, что получает и `PollingRunner` —
см. `container.py`), а не создаёт свой собственный.
"""

from __future__ import annotations

from upwork_assistant.adapters.upwork.polling import PollingPolicy
from upwork_assistant.adapters.upwork.source import UpworkJobSource
from upwork_assistant.config import Settings


def test_constructor_stores_the_shared_policy_instance(settings: Settings) -> None:
    policy = PollingPolicy(
        interval_minutes=settings.poll_interval_minutes,
        jitter_pct=settings.poll_jitter_pct,
        max_page_loads_per_hour=1,
    )

    source = UpworkJobSource(settings, policy)

    assert source._policy is policy
