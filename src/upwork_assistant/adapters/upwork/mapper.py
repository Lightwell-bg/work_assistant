"""Маппинг `RawJob` (сырой Upwork payload) -> `domain.JobPosting` + `UpworkJobFacts`.

Строковые enum-подобные поля Upwork (`tierText`, `proposalsTier`) —
локализационные ключи вида `jsn_Intermediate_206` /
`usnuxt_JobProposalTier_418.lessThan5`, не документированный публично
формат. Нераспознанное значение — не повод падать (это не критичное поле),
но обязано быть видно в логе: молчаливый `None`/`UNKNOWN` без предупреждения
и есть тот дрейф схемы, который должен быть замечен, а не проглочен.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from upwork_assistant.adapters.upwork.payload_models import RawJob
from upwork_assistant.domain.errors import PermanentError
from upwork_assistant.domain.models import (
    ClientProfile,
    ExperienceLevel,
    JobPosting,
    JobType,
    Money,
    ProposalTier,
    RateRange,
)

logger = logging.getLogger(__name__)

_JOB_TYPE_MAP = {1: JobType.FIXED, 2: JobType.HOURLY}

_EXPERIENCE_PATTERN = re.compile(r"^jsn_([A-Za-z]+)_\d+$")
_EXPERIENCE_MAP = {
    "entrylevel": ExperienceLevel.ENTRY,
    "entry": ExperienceLevel.ENTRY,
    "intermediate": ExperienceLevel.INTERMEDIATE,
    "expert": ExperienceLevel.EXPERT,
}

_PROPOSAL_TIER_MAP = {
    "lessthan5": ProposalTier.LESS_THAN_5,
    "5to10": ProposalTier.FIVE_TO_TEN,
    "10to15": ProposalTier.TEN_TO_15,
    "15to20": ProposalTier.FIFTEEN_TO_20,
    "20to50": ProposalTier.TWENTY_TO_50,
    "50plus": ProposalTier.FIFTY_PLUS,
}


class UpworkJobFacts(BaseModel):
    """Всё специфичное для Upwork, что не протекает в доменные сервисы.

    Connects (`entry_cost`) и screening-вопросы приходят только со страницы
    вакансии, не со страницы поиска — здесь их нет; довешиваются, когда
    появится сбор деталей отдельной вакансии.
    """

    model_config = ConfigDict(frozen=True)

    ciphertext: str
    raw_payload: dict[str, object]

    def summary_lines(self) -> tuple[str, ...]:
        return (f"Upwork ciphertext: {self.ciphertext}",)


def _map_job_type(raw_type: int) -> JobType:
    try:
        return _JOB_TYPE_MAP[raw_type]
    except KeyError as exc:
        raise PermanentError(f"Неизвестный тип вакансии Upwork: {raw_type}") from exc


def _map_experience_level(tier_text: str | None) -> ExperienceLevel | None:
    if tier_text is None:
        return None
    match = _EXPERIENCE_PATTERN.match(tier_text)
    if match is None:
        logger.warning("Не удалось распознать уровень опыта Upwork: %r", tier_text)
        return None
    level = _EXPERIENCE_MAP.get(match.group(1).lower())
    if level is None:
        logger.warning("Неизвестный уровень опыта Upwork: %r", tier_text)
    return level


def _map_proposal_tier(raw: str | None) -> ProposalTier:
    if raw is None:
        return ProposalTier.UNKNOWN
    suffix = raw.rsplit(".", 1)[-1].lower()
    tier = _PROPOSAL_TIER_MAP.get(suffix)
    if tier is None:
        logger.warning("Неизвестная конкуренция по откликам Upwork: %r", raw)
        return ProposalTier.UNKNOWN
    return tier


def map_job(raw: RawJob) -> tuple[JobPosting, UpworkJobFacts]:
    """Смаппить один сырой payload вакансии в домен."""
    job_type = _map_job_type(raw.type)

    budget = (
        Money(amount=Decimal(str(raw.amount.amount)))
        if job_type is JobType.FIXED and raw.amount.amount > 0
        else None
    )
    rate_range = (
        RateRange(
            min_rate=Decimal(str(raw.hourlyBudget.min)) if raw.hourlyBudget.min > 0 else None,
            max_rate=Decimal(str(raw.hourlyBudget.max)) if raw.hourlyBudget.max > 0 else None,
        )
        if job_type is JobType.HOURLY
        else None
    )

    client = ClientProfile(
        country=raw.client.location.country if raw.client.location is not None else None,
        payment_verified=raw.client.isPaymentVerified,
        total_spend=Decimal(raw.client.totalSpent or "0"),
        avg_rating=raw.client.totalFeedback,
        reviews_count=raw.client.totalReviews,
    )

    job = JobPosting(
        external_id=raw.uid,
        url=f"https://www.upwork.com/jobs/{raw.ciphertext}",
        title=raw.title,
        description=raw.description,
        skills=tuple(skill.prefLabel for skill in raw.attrs),
        job_type=job_type,
        budget=budget,
        rate_range=rate_range,
        duration=raw.durationLabel,
        experience_level=_map_experience_level(raw.tierText),
        posted_at=raw.publishedOn,
        client=client,
        competition=_map_proposal_tier(raw.proposalsTier),
        entry_cost=0,  # Connects — только со страницы вакансии, не со страницы поиска
    )
    facts = UpworkJobFacts(ciphertext=raw.ciphertext, raw_payload=raw.model_dump(mode="json"))
    return job, facts
