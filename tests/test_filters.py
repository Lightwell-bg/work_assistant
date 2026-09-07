"""Табличные тесты движка фильтров."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from upwork_assistant.domain.filters import (
    FilterField,
    FilterMatchMode,
    FilterOperator,
    FilterRule,
    FilterSet,
    evaluate,
)
from upwork_assistant.domain.models import (
    ClientProfile,
    ExperienceLevel,
    JobPosting,
    JobType,
    Money,
    ProposalTier,
)


def make_job(**overrides: object) -> JobPosting:
    defaults: dict[str, object] = {
        "external_id": "job-1",
        "url": "https://www.upwork.com/jobs/job-1",
        "title": "Senior Python backend engineer",
        "description": "Нужен бэкенд на FastAPI и SQLAlchemy.",
        "skills": ("python", "fastapi", "postgresql"),
        "job_type": JobType.FIXED,
        "budget": Money(amount=Decimal("500")),
        "rate_range": None,
        "duration": None,
        "experience_level": ExperienceLevel.EXPERT,
        "posted_at": datetime(2026, 1, 1, tzinfo=UTC),
        "client": ClientProfile(
            country="US",
            payment_verified=True,
            total_spend=Decimal("10000"),
            hire_rate=0.6,
            avg_rating=4.8,
            reviews_count=25,
        ),
        "competition": ProposalTier.FIVE_TO_TEN,
        "entry_cost": 4,
    }
    defaults.update(overrides)
    return JobPosting(**defaults)


def rule(field: FilterField, operator: FilterOperator, value: object) -> FilterRule:
    return FilterRule(field=field, operator=operator, value=value)


CASES: list[tuple[str, JobPosting, FilterSet, bool]] = [
    (
        "пустой набор правил пропускает всё",
        make_job(),
        FilterSet(name="empty"),
        True,
    ),
    (
        "минимальный бюджет: проходит",
        make_job(budget=Money(amount=Decimal("500"))),
        FilterSet(
            name="min-budget",
            rules=(rule(FilterField.BUDGET_AMOUNT, FilterOperator.GTE, 300),),
        ),
        True,
    ),
    (
        "минимальный бюджет: не проходит",
        make_job(budget=Money(amount=Decimal("100"))),
        FilterSet(
            name="min-budget",
            rules=(rule(FilterField.BUDGET_AMOUNT, FilterOperator.GTE, 300),),
        ),
        False,
    ),
    (
        "почасовая ставка отсутствует у fixed-заказа: include-правило не проходит",
        make_job(job_type=JobType.FIXED, rate_range=None),
        FilterSet(
            name="hourly-min",
            rules=(rule(FilterField.HOURLY_MIN_RATE, FilterOperator.GTE, 20),),
        ),
        False,
    ),
    (
        "верифицированный платёж — обязателен",
        make_job(client=ClientProfile(payment_verified=False)),
        FilterSet(
            name="verified",
            rules=(rule(FilterField.CLIENT_PAYMENT_VERIFIED, FilterOperator.EQ, True),),
        ),
        False,
    ),
    (
        "исключить заказчиков со слабым рейтингом",
        make_job(client=ClientProfile(avg_rating=3.0)),
        FilterSet(
            name="rating",
            rules=(rule(FilterField.CLIENT_AVG_RATING, FilterOperator.GTE, 4.0),),
        ),
        False,
    ),
    (
        "рейтинг не задан (новый заказчик) — include-правило не проходит",
        make_job(client=ClientProfile(avg_rating=None)),
        FilterSet(
            name="rating",
            rules=(rule(FilterField.CLIENT_AVG_RATING, FilterOperator.GTE, 4.0),),
        ),
        False,
    ),
    (
        "стоп-слово в заголовке исключает вакансию",
        make_job(title="WordPress fixes needed ASAP"),
        FilterSet(
            name="no-wordpress",
            rules=(rule(FilterField.TITLE, FilterOperator.NOT_CONTAINS, "wordpress"),),
        ),
        False,
    ),
    (
        "стоп-слово отсутствует — исключающее правило проходит",
        make_job(title="Senior Python backend engineer"),
        FilterSet(
            name="no-wordpress",
            rules=(rule(FilterField.TITLE, FilterOperator.NOT_CONTAINS, "wordpress"),),
        ),
        True,
    ),
    (
        "нужен хотя бы один из навыков",
        make_job(skills=("python", "django")),
        FilterSet(
            name="skills-any",
            rules=(
                rule(FilterField.SKILLS, FilterOperator.CONTAINS_ANY, ["django", "flask"]),
            ),
        ),
        True,
    ),
    (
        "нужны все навыки — не хватает одного",
        make_job(skills=("python", "django")),
        FilterSet(
            name="skills-all",
            rules=(
                rule(FilterField.SKILLS, FilterOperator.CONTAINS_ALL, ["python", "flask"]),
            ),
        ),
        False,
    ),
    (
        "тип занятости через IN",
        make_job(job_type=JobType.HOURLY),
        FilterSet(
            name="job-type-in",
            rules=(rule(FilterField.JOB_TYPE, FilterOperator.IN, ["hourly", "fixed"]),),
        ),
        True,
    ),
    (
        "ANY: достаточно одного совпавшего правила",
        make_job(budget=Money(amount=Decimal("10")), client=ClientProfile(avg_rating=4.9)),
        FilterSet(
            name="any-mode",
            match_mode=FilterMatchMode.ANY,
            rules=(
                rule(FilterField.BUDGET_AMOUNT, FilterOperator.GTE, 300),
                rule(FilterField.CLIENT_AVG_RATING, FilterOperator.GTE, 4.0),
            ),
        ),
        True,
    ),
    (
        "ALL: одно несовпавшее правило проваливает весь набор",
        make_job(budget=Money(amount=Decimal("10")), client=ClientProfile(avg_rating=4.9)),
        FilterSet(
            name="all-mode",
            match_mode=FilterMatchMode.ALL,
            rules=(
                rule(FilterField.BUDGET_AMOUNT, FilterOperator.GTE, 300),
                rule(FilterField.CLIENT_AVG_RATING, FilterOperator.GTE, 4.0),
            ),
        ),
        False,
    ),
    (
        "максимальная стоимость входа (Connects)",
        make_job(entry_cost=6),
        FilterSet(
            name="entry-cost",
            rules=(rule(FilterField.ENTRY_COST, FilterOperator.LTE, 4),),
        ),
        False,
    ),
    (
        "уровень опыта — конкретное значение",
        make_job(experience_level=ExperienceLevel.ENTRY),
        FilterSet(
            name="experience",
            rules=(rule(FilterField.EXPERIENCE_LEVEL, FilterOperator.NE, "entry"),),
        ),
        False,
    ),
]


@pytest.mark.parametrize(
    ("name", "job", "filter_set", "expected"), CASES, ids=[c[0] for c in CASES]
)
def test_evaluate(name: str, job: JobPosting, filter_set: FilterSet, expected: bool) -> None:
    assert evaluate(job, filter_set) is expected


def test_inactive_filter_set_is_still_evaluable() -> None:
    """`is_active` — забота вызывающего сервиса, не самой evaluate()."""
    filter_set = FilterSet(
        name="disabled",
        is_active=False,
        rules=(rule(FilterField.BUDGET_AMOUNT, FilterOperator.GTE, 300),),
    )
    assert evaluate(make_job(budget=Money(amount=Decimal("500"))), filter_set) is True
