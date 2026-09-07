"""Доменные модели вакансии, независимые от площадки.

`JobPosting` — общая модель для любой биржи фриланса. Всё специфичное для
Upwork (ciphertext id, Connects, screening-вопросы, сырой payload) живёт
в `UpworkJobFacts` (адаптер `adapters/upwork`), а не здесь.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobType(StrEnum):
    """Тип оплаты вакансии."""

    FIXED = "fixed"
    HOURLY = "hourly"


class ExperienceLevel(StrEnum):
    """Требуемый уровень опыта."""

    ENTRY = "entry"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"


class ProposalTier(StrEnum):
    """Конкуренция по числу откликов, как её показывает биржа."""

    LESS_THAN_5 = "less_than_5"
    FIVE_TO_TEN = "5_to_10"
    TEN_TO_15 = "10_to_15"
    FIFTEEN_TO_20 = "15_to_20"
    TWENTY_TO_50 = "20_to_50"
    FIFTY_PLUS = "50_plus"
    UNKNOWN = "unknown"


class JobStatus(StrEnum):
    """Стадия обработки вакансии в пайплайне.

    `SCORING_FAILED` — явный статус сбоя ИИ, а не тихий откат на эвристику
    (в отличие от Kwork-версии): виден в БД и в `/health`.
    """

    NEW = "new"
    FILTERED_OUT = "filtered_out"
    SCORED = "scored"
    SCORING_FAILED = "scoring_failed"
    DRAFTED = "drafted"
    NOTIFIED = "notified"


class Money(BaseModel):
    """Денежная сумма. `Decimal` — чтобы не терять точность на бюджетах."""

    model_config = ConfigDict(frozen=True)

    amount: Decimal
    currency: str = "USD"


class RateRange(BaseModel):
    """Диапазон почасовой ставки для `JobType.HOURLY`."""

    model_config = ConfigDict(frozen=True)

    min_rate: Decimal | None = None
    max_rate: Decimal | None = None
    currency: str = "USD"


class ClientProfile(BaseModel):
    """Публичный профиль заказчика на бирже."""

    model_config = ConfigDict(frozen=True)

    country: str | None = None
    payment_verified: bool = False
    total_spend: Decimal = Decimal(0)
    hire_rate: float | None = Field(default=None, ge=0, le=1)
    avg_rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int = Field(default=0, ge=0)


class JobPosting(BaseModel):
    """Вакансия в терминах, общих для любой биржи фриланса."""

    model_config = ConfigDict(frozen=True)

    external_id: str
    url: str
    title: str
    description: str
    skills: tuple[str, ...] = ()
    job_type: JobType
    budget: Money | None = None
    rate_range: RateRange | None = None
    duration: str | None = None
    experience_level: ExperienceLevel | None = None
    posted_at: datetime
    client: ClientProfile
    competition: ProposalTier = ProposalTier.UNKNOWN
    entry_cost: int = Field(default=0, ge=0)
    status: JobStatus = JobStatus.NEW


class Score(BaseModel):
    """Результат скоринга вакансии моделью."""

    model_config = ConfigDict(frozen=True)

    value: float = Field(ge=0, le=10)
    reasoning: str


class DraftStatus(StrEnum):
    """Стадия черновика отклика."""

    PENDING = "pending"
    READY = "ready"
    GENERATION_FAILED = "generation_failed"
    SENT = "sent"


class Draft(BaseModel):
    """Черновик отклика на вакансию. Отправляет его человек, не бот."""

    model_config = ConfigDict(frozen=True)

    job_external_id: str
    content: str
    status: DraftStatus = DraftStatus.PENDING
    created_at: datetime


class JobSourceName(StrEnum):
    """Площадка, с которой пришла вакансия или для которой задан поиск.

    Значения попадают в БД и в пути API — менять их нельзя без миграции.
    """

    UPWORK = "upwork"
    LINKEDIN = "linkedin"


class SearchQuery(BaseModel):
    """Сохранённый поиск: то, что раньше лежало строкой в `UPWORK_SEARCH_URLS`.

    Живёт в БД, а не в `.env`, чтобы правиться через веб-панель без
    перезапуска процесса и без доступа к файлам на сервере.
    """

    model_config = ConfigDict(frozen=True)

    source: JobSourceName
    name: str
    query: str
    is_active: bool = True
