"""Порт источника вакансий.

Сервисы зависят только от этого протокола, не от того, как вакансии на
самом деле добываются. Если Upwork закроет скрейпинг, адаптер на
официальный GraphQL API или на парсинг email-алертов подключается заменой
одной реализации `JobSource` — без единой правки в сервисах.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from upwork_assistant.domain.models import JobPosting


class PolledJob(BaseModel):
    """Вакансия одного цикла опроса вместе с сырым payload источника.

    `raw_payload` — материал для реплея, если маппер разойдётся со схемой
    источника (см. риск дрейфа схемы в плане); сервисы его не читают, только
    сохраняют через `UnitOfWork.upwork_facts` — порт остаётся про домен, а не
    про формат конкретной площадки.
    """

    model_config = ConfigDict(frozen=True)

    job: JobPosting
    raw_payload: dict[str, object] | None = None


class JobSource(Protocol):
    """Источник вакансий для одного цикла опроса."""

    async def poll(self) -> list[PolledJob]:
        """Получить вакансии, появившиеся с прошлого цикла."""
        ...
