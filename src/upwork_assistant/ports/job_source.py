"""Порт источника вакансий.

Сервисы зависят только от этого протокола, не от того, как вакансии на
самом деле добываются. Если Upwork закроет скрейпинг, адаптер на
официальный GraphQL API или на парсинг email-алертов подключается заменой
одной реализации `JobSource` — без единой правки в сервисах.
"""

from __future__ import annotations

from collections.abc import Sequence
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

    async def poll(self, searches: Sequence[str]) -> list[PolledJob]:
        """Получить вакансии по переданным сохранённым поискам.

        Поиски приходят снаружи, а не читаются адаптером: они лежат в БД, а
        адаптер площадки не должен знать про наше хранилище — ровно так же,
        как пресеты фильтров загружает `IngestService`, а не сам источник.
        """
        ...
