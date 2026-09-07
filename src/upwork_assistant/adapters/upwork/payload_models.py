"""Pydantic-модели сырого payload вакансии из `state.jobsSearch.jobs`.

Поля и их формы выверены по реальному захвату (headful, залогиненный
профиль, поиск `q=python`, 2026-09-07) — см.
`tests/fixtures/upwork/nuxt_state_search_python.json`. Не документированы
Upwork публично, поэтому `extra="ignore"`: новое поле не должно ронять
парсинг, а вот пропажа/смена типа известного поля — должна (это и есть
дрейф схемы, который нужно ловить, а не маскировать).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawJobClientLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    country: str | None = None


class RawJobClient(BaseModel):
    model_config = ConfigDict(extra="ignore")

    location: RawJobClientLocation | None = None
    isPaymentVerified: bool = False
    totalSpent: str = "0"
    totalReviews: int = 0
    totalFeedback: float | None = None
    hasFinancialPrivacy: bool = False


class RawJobAmount(BaseModel):
    """Бюджет фиксированной цены. `amount == 0` на почасовых вакансиях."""

    model_config = ConfigDict(extra="ignore")

    amount: float = 0


class RawJobHourlyBudget(BaseModel):
    """Диапазон почасовой ставки. `min == max == 0` на вакансиях с фикс. ценой."""

    model_config = ConfigDict(extra="ignore")

    min: float = 0
    max: float = 0


class RawJobSkill(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prefLabel: str


class RawJob(BaseModel):
    """Одна вакансия из `state.jobsSearch.jobs`."""

    model_config = ConfigDict(extra="ignore")

    uid: str
    ciphertext: str
    title: str
    description: str
    publishedOn: datetime
    createdOn: datetime | None = None
    type: int
    durationLabel: str | None = None
    engagement: str | None = None
    amount: RawJobAmount = RawJobAmount()
    hourlyBudget: RawJobHourlyBudget = RawJobHourlyBudget()
    client: RawJobClient = RawJobClient()
    tierText: str | None = None
    proposalsTier: str | None = None
    attrs: list[RawJobSkill] = []
