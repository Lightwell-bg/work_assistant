"""DTO HTTP-слоя. Намеренно отделены от доменных моделей."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from upwork_assistant.domain.filters import (
    FilterField,
    FilterMatchMode,
    FilterOperator,
    FilterRule,
    FilterSet,
)
from upwork_assistant.domain.models import (
    Draft,
    DraftStatus,
    ExperienceLevel,
    JobPosting,
    JobSourceName,
    JobStatus,
    JobType,
    ProposalTier,
    Score,
    SearchQuery,
)


class HealthResponse(BaseModel):
    """Ответ проверки живости."""

    status: str
    version: str


class FilterRuleIn(BaseModel):
    """Правило фильтра на входе. `value` — список, не кортеж: в JSON нет
    кортежей, а собственный валидатор `FilterRule` коэрсит list -> tuple."""

    field: FilterField
    operator: FilterOperator
    value: str | float | int | bool | list[str]


class FilterRuleOut(BaseModel):
    """Правило фильтра на выходе."""

    field: FilterField
    operator: FilterOperator
    value: str | float | int | bool | list[str]


class FilterSetIn(BaseModel):
    """Тело запроса на создание/полную замену пресета фильтров."""

    match_mode: FilterMatchMode = FilterMatchMode.ALL
    is_active: bool = True
    rules: list[FilterRuleIn] = []


class FilterSetOut(BaseModel):
    """Пресет фильтров на выходе."""

    name: str
    match_mode: FilterMatchMode
    is_active: bool
    rules: list[FilterRuleOut]


class MoneyOut(BaseModel):
    """Денежная сумма на выходе."""

    amount: Decimal
    currency: str


class RateRangeOut(BaseModel):
    """Диапазон почасовой ставки на выходе."""

    min_rate: Decimal | None
    max_rate: Decimal | None
    currency: str


class ClientOut(BaseModel):
    """Публичный профиль заказчика на выходе."""

    country: str | None
    payment_verified: bool
    total_spend: Decimal
    hire_rate: float | None
    avg_rating: float | None
    reviews_count: int


class JobOut(BaseModel):
    """Вакансия на выходе, вместе с сохранённой (опционально) оценкой."""

    external_id: str
    url: str
    title: str
    description: str
    skills: list[str]
    job_type: JobType
    budget: MoneyOut | None
    rate_range: RateRangeOut | None
    duration: str | None
    experience_level: ExperienceLevel | None
    posted_at: datetime
    client: ClientOut
    competition: ProposalTier
    entry_cost: int
    status: JobStatus
    score_value: float | None = None
    score_reasoning: str | None = None


class DraftOut(BaseModel):
    """Черновик отклика на выходе."""

    job_external_id: str
    content: str
    status: DraftStatus
    created_at: datetime


class StatsOut(BaseModel):
    """Сводная статистика по вакансиям и расходам на LLM."""

    jobs_by_status: dict[str, int]
    llm_cost_today_usd: float
    llm_cost_total_usd: float


class AdminStatusOut(BaseModel):
    """Состояние опроса — kill switch читает и переключает именно это."""

    scheduled: bool
    circuit_open: bool
    consecutive_failures: int


class SearchQueryIn(BaseModel):
    """Тело запроса на создание/замену поиска. Источник и имя — в пути URL."""

    query: str
    is_active: bool = True


class SearchQueryOut(BaseModel):
    """Сохранённый поиск на выходе."""

    source: JobSourceName
    name: str
    query: str
    is_active: bool


def search_query_out_from_domain(search: SearchQuery) -> SearchQueryOut:
    """Собрать выходной DTO поиска из доменной модели."""
    return SearchQueryOut(
        source=search.source,
        name=search.name,
        query=search.query,
        is_active=search.is_active,
    )


def filter_rule_in_to_domain(rule: FilterRuleIn) -> FilterRule:
    """Собрать доменное правило из входного DTO."""
    return FilterRule(
        field=rule.field,
        operator=rule.operator,
        value=tuple(rule.value) if isinstance(rule.value, list) else rule.value,
    )


def filter_set_out_from_domain(filter_set: FilterSet) -> FilterSetOut:
    """Собрать выходной DTO пресета из доменной модели."""
    return FilterSetOut(
        name=filter_set.name,
        match_mode=filter_set.match_mode,
        is_active=filter_set.is_active,
        rules=[
            FilterRuleOut(
                field=rule.field,
                operator=rule.operator,
                value=list(rule.value) if isinstance(rule.value, tuple) else rule.value,
            )
            for rule in filter_set.rules
        ],
    )


def job_out_from_domain(job: JobPosting, score: Score | None) -> JobOut:
    """Собрать выходной DTO вакансии из доменной модели и опциональной оценки."""
    return JobOut(
        external_id=job.external_id,
        url=job.url,
        title=job.title,
        description=job.description,
        skills=list(job.skills),
        job_type=job.job_type,
        budget=MoneyOut(amount=job.budget.amount, currency=job.budget.currency)
        if job.budget is not None
        else None,
        rate_range=RateRangeOut(
            min_rate=job.rate_range.min_rate,
            max_rate=job.rate_range.max_rate,
            currency=job.rate_range.currency,
        )
        if job.rate_range is not None
        else None,
        duration=job.duration,
        experience_level=job.experience_level,
        posted_at=job.posted_at,
        client=ClientOut(
            country=job.client.country,
            payment_verified=job.client.payment_verified,
            total_spend=job.client.total_spend,
            hire_rate=job.client.hire_rate,
            avg_rating=job.client.avg_rating,
            reviews_count=job.client.reviews_count,
        ),
        competition=job.competition,
        entry_cost=job.entry_cost,
        status=job.status,
        score_value=score.value if score is not None else None,
        score_reasoning=score.reasoning if score is not None else None,
    )


def draft_out_from_domain(draft: Draft) -> DraftOut:
    """Собрать выходной DTO черновика из доменной модели."""
    return DraftOut(
        job_external_id=draft.job_external_id,
        content=draft.content,
        status=draft.status,
        created_at=draft.created_at,
    )
