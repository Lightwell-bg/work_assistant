"""Конкретные репозитории поверх SQLAlchemy `AsyncSession`.

Маппинг строка<->домен пишется явно (`_to_domain`/`_to_row_values`), а не
прячется в ORM-события или гибридные свойства — при расхождении домена и
схемы это должно падать в одном явном месте, а не размазываться по коду.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from upwork_assistant.adapters.db.tables import (
    AppStateRow,
    DraftRow,
    FilterRuleRow,
    FilterSetRow,
    JobPostingRow,
    LLMUsageRow,
    SearchQueryRow,
    UpworkJobFactsRow,
)
from upwork_assistant.domain.errors import PermanentError
from upwork_assistant.domain.filters import FilterRule, FilterSet
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    ExperienceLevel,
    JobPosting,
    JobSourceName,
    JobStatus,
    JobType,
    Money,
    ProposalTier,
    RateRange,
    Score,
    SearchQuery,
)
from upwork_assistant.ports.llm import LLMUsageRecord


class UnknownJobError(PermanentError):
    """Операция адресована вакансии, которой нет в БД."""


class UnknownFilterSetError(PermanentError):
    """Операция адресована пресету фильтров, которого нет в БД."""


class UnknownSearchQueryError(PermanentError):
    """Операция адресована поиску, которого нет в БД."""


def _job_to_domain(row: JobPostingRow) -> JobPosting:
    """Собрать доменную `JobPosting` из плоской строки таблицы."""
    budget = (
        Money(amount=row.budget_amount, currency=row.budget_currency or "USD")
        if row.budget_amount is not None
        else None
    )
    rate_range = (
        RateRange(min_rate=row.rate_min, max_rate=row.rate_max, currency=row.rate_currency or "USD")
        if row.rate_min is not None or row.rate_max is not None
        else None
    )
    client = ClientProfile(
        country=row.client_country,
        payment_verified=row.client_payment_verified,
        total_spend=row.client_total_spend,
        hire_rate=row.client_hire_rate,
        avg_rating=row.client_avg_rating,
        reviews_count=row.client_reviews_count,
    )
    return JobPosting(
        external_id=row.external_id,
        url=row.url,
        title=row.title,
        description=row.description,
        skills=tuple(row.skills),
        job_type=JobType(row.job_type),
        budget=budget,
        rate_range=rate_range,
        duration=row.duration,
        experience_level=ExperienceLevel(row.experience_level)
        if row.experience_level is not None
        else None,
        posted_at=row.posted_at,
        client=client,
        competition=ProposalTier(row.competition),
        entry_cost=row.entry_cost,
        status=JobStatus(row.status),
    )


def _job_to_row_values(job: JobPosting) -> dict[str, object]:
    """Разложить `JobPosting` в значения колонок `job_postings`."""
    return {
        "external_id": job.external_id,
        "url": job.url,
        "title": job.title,
        "description": job.description,
        "skills": list(job.skills),
        "job_type": job.job_type.value,
        "budget_amount": job.budget.amount if job.budget is not None else None,
        "budget_currency": job.budget.currency if job.budget is not None else None,
        "rate_min": job.rate_range.min_rate if job.rate_range is not None else None,
        "rate_max": job.rate_range.max_rate if job.rate_range is not None else None,
        "rate_currency": job.rate_range.currency if job.rate_range is not None else None,
        "duration": job.duration,
        "experience_level": (
            job.experience_level.value if job.experience_level is not None else None
        ),
        "posted_at": job.posted_at,
        "client_country": job.client.country,
        "client_payment_verified": job.client.payment_verified,
        "client_total_spend": job.client.total_spend,
        "client_hire_rate": job.client.hire_rate,
        "client_avg_rating": job.client.avg_rating,
        "client_reviews_count": job.client.reviews_count,
        "competition": job.competition.value,
        "entry_cost": job.entry_cost,
        "status": job.status.value,
    }


class SqlAlchemyJobRepository:
    """Реализация `JobRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_row(self, external_id: str) -> JobPostingRow | None:
        result = await self._session.execute(
            select(JobPostingRow).where(JobPostingRow.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, job: JobPosting) -> None:
        row = await self._get_row(job.external_id)
        values = _job_to_row_values(job)
        if row is None:
            self._session.add(JobPostingRow(**values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await self._session.flush()

    async def get_by_external_id(self, external_id: str) -> JobPosting | None:
        row = await self._get_row(external_id)
        return _job_to_domain(row) if row is not None else None

    async def list_all(self) -> list[JobPosting]:
        result = await self._session.execute(select(JobPostingRow))
        return [_job_to_domain(row) for row in result.scalars().all()]

    async def list_by_status(self, status: JobStatus) -> list[JobPosting]:
        result = await self._session.execute(
            select(JobPostingRow).where(JobPostingRow.status == status.value)
        )
        return [_job_to_domain(row) for row in result.scalars().all()]

    async def exists(self, external_id: str) -> bool:
        return await self._get_row(external_id) is not None

    async def set_status(self, external_id: str, status: JobStatus) -> None:
        row = await self._get_row(external_id)
        if row is None:
            raise UnknownJobError(f"Вакансия {external_id!r} не найдена")
        row.status = status.value
        await self._session.flush()

    async def save_score(self, external_id: str, score: Score) -> None:
        row = await self._get_row(external_id)
        if row is None:
            raise UnknownJobError(f"Вакансия {external_id!r} не найдена")
        row.score_value = score.value
        row.score_reasoning = score.reasoning
        await self._session.flush()

    async def get_score(self, external_id: str) -> Score | None:
        row = await self._get_row(external_id)
        if row is None or row.score_value is None:
            return None
        return Score(value=row.score_value, reasoning=row.score_reasoning or "")


def _filter_rule_to_domain(row: FilterRuleRow) -> FilterRule:
    # `FilterRule` сама коэрсит list -> tuple в своём валидаторе, поэтому
    # достаточно передать сырое значение из JSON-колонки как есть.
    return FilterRule(field=row.field, operator=row.operator, value=row.value)


def _filter_set_to_domain(row: FilterSetRow) -> FilterSet:
    return FilterSet(
        name=row.name,
        rules=tuple(_filter_rule_to_domain(rule) for rule in row.rules),
        match_mode=row.match_mode,
        is_active=row.is_active,
    )


class SqlAlchemyFilterSetRepository:
    """Реализация `FilterSetRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_row(self, name: str) -> FilterSetRow | None:
        result = await self._session.execute(
            select(FilterSetRow)
            .options(selectinload(FilterSetRow.rules))
            .where(FilterSetRow.name == name)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[FilterSet]:
        result = await self._session.execute(
            select(FilterSetRow).options(selectinload(FilterSetRow.rules)).where(FilterSetRow.is_active)
        )
        return [_filter_set_to_domain(row) for row in result.scalars().all()]

    async def get_by_name(self, name: str) -> FilterSet | None:
        row = await self._get_row(name)
        return _filter_set_to_domain(row) if row is not None else None

    async def save(self, filter_set: FilterSet) -> None:
        row = await self._get_row(filter_set.name)
        new_rules = [
            FilterRuleRow(
                position=position,
                field=rule.field.value,
                operator=rule.operator.value,
                value=_value_to_json(rule.value),
            )
            for position, rule in enumerate(filter_set.rules)
        ]
        if row is None:
            row = FilterSetRow(
                name=filter_set.name,
                match_mode=filter_set.match_mode.value,
                is_active=filter_set.is_active,
                rules=new_rules,
            )
            self._session.add(row)
        else:
            row.match_mode = filter_set.match_mode.value
            row.is_active = filter_set.is_active
            # Присваивание всей коллекции при `cascade="all, delete-orphan"`
            # удаляет старые строки правил и вставляет новые — без дублей.
            row.rules = new_rules
        await self._session.flush()

    async def delete(self, name: str) -> None:
        row = await self._get_row(name)
        if row is None:
            raise UnknownFilterSetError(f"Пресет {name!r} не найден")
        await self._session.delete(row)
        await self._session.flush()


def _value_to_json(value: object) -> object:
    """Привести значение правила к JSON-совместимому виду (tuple -> list)."""
    if isinstance(value, tuple):
        return list(value)
    return value


def _draft_to_domain(row: DraftRow, job_external_id: str) -> Draft:
    return Draft(
        job_external_id=job_external_id,
        content=row.content,
        status=DraftStatus(row.status),
        created_at=row.created_at,
    )


class SqlAlchemyDraftRepository:
    """Реализация `DraftRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_job_row(self, job_external_id: str) -> JobPostingRow:
        result = await self._session.execute(
            select(JobPostingRow).where(JobPostingRow.external_id == job_external_id)
        )
        job_row = result.scalar_one_or_none()
        if job_row is None:
            raise UnknownJobError(f"Вакансия {job_external_id!r} не найдена")
        return job_row

    async def _get_draft_row(self, job_external_id: str) -> DraftRow | None:
        result = await self._session.execute(
            select(DraftRow)
            .join(JobPostingRow, DraftRow.job_posting_id == JobPostingRow.id)
            .where(JobPostingRow.external_id == job_external_id)
        )
        return result.scalar_one_or_none()

    async def add(self, job_external_id: str, draft: Draft) -> None:
        job_row = await self._get_job_row(job_external_id)
        existing = await self._get_draft_row(job_external_id)
        if existing is None:
            self._session.add(
                DraftRow(
                    job_posting_id=job_row.id,
                    content=draft.content,
                    status=draft.status.value,
                )
            )
        else:
            existing.content = draft.content
            existing.status = draft.status.value
        await self._session.flush()

    async def get_by_job(self, job_external_id: str) -> Draft | None:
        row = await self._get_draft_row(job_external_id)
        return _draft_to_domain(row, job_external_id) if row is not None else None

    async def set_status(self, job_external_id: str, status: DraftStatus) -> None:
        row = await self._get_draft_row(job_external_id)
        if row is None:
            raise UnknownJobError(f"Черновик для вакансии {job_external_id!r} не найден")
        row.status = status.value
        await self._session.flush()


class SqlAlchemyLLMUsageRepository:
    """Реализация `LLMUsageRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: LLMUsageRecord) -> None:
        self._session.add(
            LLMUsageRow(
                purpose=record.purpose,
                job_external_id=record.job_external_id,
                model=record.model,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                cost_usd=record.cost_usd,
            )
        )
        await self._session.flush()

    async def total_cost_since(self, since: datetime) -> float:
        result = await self._session.execute(
            select(func.sum(LLMUsageRow.cost_usd)).where(LLMUsageRow.created_at >= since)
        )
        total = result.scalar_one_or_none()
        return float(total) if total is not None else 0.0


class SqlAlchemyUpworkJobFactsRepository:
    """Реализация `UpworkJobFactsRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_row(self, job_external_id: str) -> UpworkJobFactsRow | None:
        result = await self._session.execute(
            select(UpworkJobFactsRow).where(UpworkJobFactsRow.job_external_id == job_external_id)
        )
        return result.scalar_one_or_none()

    async def add(self, job_external_id: str, raw_payload: dict[str, object]) -> None:
        row = await self._get_row(job_external_id)
        if row is None:
            self._session.add(
                UpworkJobFactsRow(job_external_id=job_external_id, raw_payload=raw_payload)
            )
        else:
            row.raw_payload = raw_payload
        await self._session.flush()

    async def get_by_job(self, job_external_id: str) -> dict[str, object] | None:
        row = await self._get_row(job_external_id)
        return row.raw_payload if row is not None else None


def _search_to_domain(row: SearchQueryRow) -> SearchQuery:
    return SearchQuery(
        source=JobSourceName(row.source),
        name=row.name,
        query=row.query,
        is_active=row.is_active,
    )


class SqlAlchemySearchQueryRepository:
    """Реализация `SearchQueryRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_row(self, source: JobSourceName, name: str) -> SearchQueryRow | None:
        result = await self._session.execute(
            select(SearchQueryRow).where(
                SearchQueryRow.source == source.value, SearchQueryRow.name == name
            )
        )
        return result.scalar_one_or_none()

    async def save(self, search: SearchQuery) -> None:
        row = await self._get_row(search.source, search.name)
        if row is None:
            self._session.add(
                SearchQueryRow(
                    source=search.source.value,
                    name=search.name,
                    query=search.query,
                    is_active=search.is_active,
                )
            )
        else:
            row.query = search.query
            row.is_active = search.is_active
        await self._session.flush()

    async def list_all(self) -> list[SearchQuery]:
        result = await self._session.execute(
            select(SearchQueryRow).order_by(SearchQueryRow.source, SearchQueryRow.name)
        )
        return [_search_to_domain(row) for row in result.scalars().all()]

    async def list_active(self, source: JobSourceName) -> list[SearchQuery]:
        result = await self._session.execute(
            select(SearchQueryRow)
            .where(SearchQueryRow.source == source.value, SearchQueryRow.is_active)
            .order_by(SearchQueryRow.name)
        )
        return [_search_to_domain(row) for row in result.scalars().all()]

    async def delete(self, source: JobSourceName, name: str) -> None:
        row = await self._get_row(source, name)
        if row is None:
            raise UnknownSearchQueryError(f"Поиск {name!r} источника {source.value!r} не найден")
        await self._session.delete(row)
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(SearchQueryRow))
        return int(result.scalar_one())


class SqlAlchemyAppStateRepository:
    """Реализация `AppStateRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_row(self, key: str) -> AppStateRow | None:
        result = await self._session.execute(select(AppStateRow).where(AppStateRow.key == key))
        return result.scalar_one_or_none()

    async def get(self, key: str) -> str | None:
        row = await self._get_row(key)
        return row.value if row is not None else None

    async def set(self, key: str, value: str) -> None:
        row = await self._get_row(key)
        if row is None:
            self._session.add(AppStateRow(key=key, value=value))
        else:
            row.value = value
        await self._session.flush()
