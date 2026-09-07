"""Движок фильтров: чистая функция без сайд-эффектов и I/O.

Пресеты (`FilterSet`) хранятся в БД как строки `filter_sets`/`filter_rules`
(см. `adapters/db/tables.py`) и на каждый цикл опроса перечитываются в эти
неизменяемые value-объекты — в отличие от Kwork-версии, где пресеты жили
только в RAM-синглтоне и терялись при рестарте.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from upwork_assistant.domain.models import JobPosting

FilterValue = str | float | int | bool | tuple[str, ...]


class FilterField(StrEnum):
    """Поле вакансии, по которому можно фильтровать."""

    JOB_TYPE = "job_type"
    BUDGET_AMOUNT = "budget_amount"
    HOURLY_MIN_RATE = "hourly_min_rate"
    HOURLY_MAX_RATE = "hourly_max_rate"
    EXPERIENCE_LEVEL = "experience_level"
    CLIENT_PAYMENT_VERIFIED = "client_payment_verified"
    CLIENT_TOTAL_SPEND = "client_total_spend"
    CLIENT_HIRE_RATE = "client_hire_rate"
    CLIENT_AVG_RATING = "client_avg_rating"
    CLIENT_REVIEWS_COUNT = "client_reviews_count"
    ENTRY_COST = "entry_cost"
    COMPETITION = "competition"
    TITLE = "title"
    DESCRIPTION = "description"
    SKILLS = "skills"


class FilterOperator(StrEnum):
    """Способ сравнения значения поля с ожидаемым значением правила."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    CONTAINS_ANY = "contains_any"
    CONTAINS_ALL = "contains_all"


# Правила-исключения: если поле у вакансии отсутствует (None), нарушить
# исключение нечем — правило считается выполненным.
_EXCLUSION_OPERATORS = frozenset(
    {FilterOperator.NE, FilterOperator.NOT_IN, FilterOperator.NOT_CONTAINS}
)

_NUMERIC_OPERATORS = frozenset(
    {FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE}
)


class FilterMatchMode(StrEnum):
    """Как комбинировать результаты правил внутри одного пресета."""

    ALL = "all"
    ANY = "any"


class FilterRule(BaseModel):
    """Одно условие: поле сравнивается с значением через оператор."""

    model_config = ConfigDict(frozen=True)

    field: FilterField
    operator: FilterOperator
    value: FilterValue

    @field_validator("value", mode="before")
    @classmethod
    def _list_to_tuple(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class FilterSet(BaseModel):
    """Именованный набор правил — пресет пользователя."""

    model_config = ConfigDict(frozen=True)

    name: str
    rules: tuple[FilterRule, ...] = ()
    match_mode: FilterMatchMode = FilterMatchMode.ALL
    is_active: bool = True


def _extract(job: JobPosting, field: FilterField) -> FilterValue | None:
    """Достать значение поля вакансии для сравнения. `None` — поле не задано."""
    match field:
        case FilterField.JOB_TYPE:
            return job.job_type.value
        case FilterField.BUDGET_AMOUNT:
            return float(job.budget.amount) if job.budget is not None else None
        case FilterField.HOURLY_MIN_RATE:
            if job.rate_range is None or job.rate_range.min_rate is None:
                return None
            return float(job.rate_range.min_rate)
        case FilterField.HOURLY_MAX_RATE:
            if job.rate_range is None or job.rate_range.max_rate is None:
                return None
            return float(job.rate_range.max_rate)
        case FilterField.EXPERIENCE_LEVEL:
            return job.experience_level.value if job.experience_level is not None else None
        case FilterField.CLIENT_PAYMENT_VERIFIED:
            return job.client.payment_verified
        case FilterField.CLIENT_TOTAL_SPEND:
            return float(job.client.total_spend)
        case FilterField.CLIENT_HIRE_RATE:
            return job.client.hire_rate
        case FilterField.CLIENT_AVG_RATING:
            return job.client.avg_rating
        case FilterField.CLIENT_REVIEWS_COUNT:
            return job.client.reviews_count
        case FilterField.ENTRY_COST:
            return job.entry_cost
        case FilterField.COMPETITION:
            return job.competition.value
        case FilterField.TITLE:
            return job.title
        case FilterField.DESCRIPTION:
            return job.description
        case FilterField.SKILLS:
            return job.skills


def _as_keywords(expected: FilterValue) -> tuple[str, ...]:
    return expected if isinstance(expected, tuple) else (str(expected),)


def _apply(operator: FilterOperator, actual: FilterValue, expected: FilterValue) -> bool:
    if operator is FilterOperator.EQ:
        return actual == expected
    if operator is FilterOperator.NE:
        return actual != expected
    if operator in _NUMERIC_OPERATORS:
        if not isinstance(actual, int | float) or isinstance(actual, bool):
            raise TypeError(f"Оператор {operator} требует числовое поле, получено {actual!r}")
        if not isinstance(expected, int | float) or isinstance(expected, bool):
            raise TypeError(f"Оператор {operator} требует числовое значение, получено {expected!r}")
        expected_num = float(expected)
        if operator is FilterOperator.GT:
            return actual > expected_num
        if operator is FilterOperator.GTE:
            return actual >= expected_num
        if operator is FilterOperator.LT:
            return actual < expected_num
        return actual <= expected_num
    if operator in (FilterOperator.IN, FilterOperator.NOT_IN):
        options = _as_keywords(expected)
        is_in = actual in options
        return is_in if operator is FilterOperator.IN else not is_in
    # Операторы на подстроку/пересечение множеств: работают со str или tuple[str, ...].
    keywords = tuple(k.lower() for k in _as_keywords(expected))
    if isinstance(actual, tuple):
        haystack = {item.lower() for item in actual}
        if operator is FilterOperator.CONTAINS:
            return keywords[0] in haystack
        if operator is FilterOperator.NOT_CONTAINS:
            return keywords[0] not in haystack
        if operator is FilterOperator.CONTAINS_ANY:
            return any(keyword in haystack for keyword in keywords)
        return all(keyword in haystack for keyword in keywords)  # CONTAINS_ALL
    text = str(actual).lower()
    if operator is FilterOperator.CONTAINS:
        return keywords[0] in text
    if operator is FilterOperator.NOT_CONTAINS:
        return keywords[0] not in text
    if operator is FilterOperator.CONTAINS_ANY:
        return any(keyword in text for keyword in keywords)
    return all(keyword in text for keyword in keywords)  # CONTAINS_ALL


def evaluate_rule(job: JobPosting, rule: FilterRule) -> bool:
    """Проверить одно правило. Отсутствующее поле не проходит include-правила
    и автоматически проходит exclude-правила (нарушать исключение нечем)."""
    actual = _extract(job, rule.field)
    if actual is None:
        return rule.operator in _EXCLUSION_OPERATORS
    return _apply(rule.operator, actual, rule.value)


def evaluate(job: JobPosting, filter_set: FilterSet) -> bool:
    """Проверить вакансию против пресета. Пустой набор правил пропускает всё."""
    if not filter_set.rules:
        return True
    results = (evaluate_rule(job, rule) for rule in filter_set.rules)
    if filter_set.match_mode is FilterMatchMode.ALL:
        return all(results)
    return any(results)
