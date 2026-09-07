"""Протоколы репозиториев: контракт хранения для сервисного слоя.

Строгий mypy на этом модуле специально: сигнатуры оперируют только доменными
типами (`JobPosting`, `FilterSet`, `Draft`, ...), без `Any` — иначе граница
между доменом и хранилищем размывается и утечки деталей БД в сервисы не
будут пойманы типами.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from upwork_assistant.domain.filters import FilterSet
from upwork_assistant.domain.models import Draft, DraftStatus, JobPosting, JobStatus, Score
from upwork_assistant.ports.llm import LLMUsageRecord


class JobRepository(Protocol):
    """Хранение вакансий."""

    async def upsert(self, job: JobPosting) -> None:
        """Вставить вакансию или обновить существующую по `external_id`."""
        ...

    async def get_by_external_id(self, external_id: str) -> JobPosting | None: ...

    async def list_all(self) -> list[JobPosting]: ...

    async def list_by_status(self, status: JobStatus) -> list[JobPosting]: ...

    async def exists(self, external_id: str) -> bool: ...

    async def set_status(self, external_id: str, status: JobStatus) -> None: ...

    async def save_score(self, external_id: str, score: Score) -> None: ...

    async def get_score(self, external_id: str) -> Score | None:
        """Прочитать сохранённую оценку. `JobPosting` её не несёт: оценка —
        это суждение о вакансии, а не её собственный факт с биржи."""
        ...


class FilterSetRepository(Protocol):
    """Хранение пресетов фильтров."""

    async def list_active(self) -> list[FilterSet]: ...

    async def get_by_name(self, name: str) -> FilterSet | None: ...

    async def save(self, filter_set: FilterSet) -> None:
        """Создать пресет или полностью заменить его правила (по имени)."""
        ...

    async def delete(self, name: str) -> None: ...


class DraftRepository(Protocol):
    """Хранение черновиков откликов."""

    async def add(self, job_external_id: str, draft: Draft) -> None: ...

    async def get_by_job(self, job_external_id: str) -> Draft | None: ...

    async def set_status(self, job_external_id: str, status: DraftStatus) -> None: ...


class LLMUsageRepository(Protocol):
    """Учёт расходов на LLM — база для дневного бюджета (следующая фаза)."""

    async def add(self, record: LLMUsageRecord) -> None: ...

    async def total_cost_since(self, since: datetime) -> float:
        """Сумма `cost_usd` по записям с `created_at >= since`. `0.0`, если записей нет."""
        ...


class UpworkJobFactsRepository(Protocol):
    """Архив сырого payload источника вакансии — материал для реплея при дрейфе схемы.

    Сигнатура — только примитивы (`str`, `dict`), не адаптер-специфичный
    `UpworkJobFacts`: порт остаётся про домен и не тянет за собой знание о
    формате конкретной площадки.
    """

    async def add(self, job_external_id: str, raw_payload: dict[str, object]) -> None:
        """Сохранить/заменить сырой payload по вакансии (upsert по job_external_id)."""
        ...

    async def get_by_job(self, job_external_id: str) -> dict[str, object] | None: ...
