"""Тесты `map_job` на реальном захвате поиска Upwork + синтетические тесты хелперов.

Табличные значения для семи вакансий взяты из ручной проверки реального
фикстура `nuxt_state_search_python.json` — используются как эталон.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from upwork_assistant.adapters.upwork.mapper import (
    _map_experience_level,
    _map_job_type,
    _map_proposal_tier,
    map_job,
)
from upwork_assistant.adapters.upwork.payload_models import RawJob
from upwork_assistant.adapters.upwork.ssr_state import extract_jobs_search
from upwork_assistant.domain.errors import PermanentError
from upwork_assistant.domain.models import ExperienceLevel, JobType, ProposalTier

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "upwork" / "nuxt_state_search_python.json"


def _load_raw_jobs() -> list[dict[str, object]]:
    nuxt_state = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    jobs, _paging = extract_jobs_search(nuxt_state)
    result: list[dict[str, object]] = jobs  # type: ignore[assignment]
    return result


@dataclass(frozen=True)
class _Expected:
    uid: str
    job_type: JobType
    budget_amount: Decimal | None
    rate_range: tuple[Decimal, Decimal] | None
    experience_level: ExperienceLevel | None
    competition: ProposalTier
    country: str | None
    total_spend: Decimal


# Эталон, вручную сверенный по реальному фикстуру от 2026-09-07.
EXPECTED: list[_Expected] = [
    _Expected(
        uid="2096947778304263398",
        job_type=JobType.FIXED,
        budget_amount=Decimal("250"),
        rate_range=None,
        experience_level=ExperienceLevel.INTERMEDIATE,
        competition=ProposalTier.LESS_THAN_5,
        country="France",
        total_spend=Decimal("30031.28"),
    ),
    _Expected(
        uid="2096947624213923046",
        job_type=JobType.HOURLY,
        budget_amount=None,
        rate_range=(Decimal("10"), Decimal("14")),
        experience_level=ExperienceLevel.INTERMEDIATE,
        competition=ProposalTier.LESS_THAN_5,
        country="Thailand",
        total_spend=Decimal("0.0"),
    ),
    _Expected(
        uid="2096947185026739546",
        job_type=JobType.HOURLY,
        budget_amount=None,
        rate_range=(Decimal("15"), Decimal("35")),
        experience_level=ExperienceLevel.INTERMEDIATE,
        competition=ProposalTier.TEN_TO_15,
        country="Israel",
        total_spend=Decimal("0.0"),
    ),
    _Expected(
        uid="2096943114821035425",
        job_type=JobType.HOURLY,
        budget_amount=None,
        rate_range=(Decimal("50"), Decimal("90")),
        experience_level=ExperienceLevel.EXPERT,
        competition=ProposalTier.FIFTY_PLUS,
        country="United States",
        total_spend=Decimal("0.0"),
    ),
    _Expected(
        uid="2096930437957381037",
        job_type=JobType.FIXED,
        budget_amount=Decimal("1800"),
        rate_range=None,
        experience_level=ExperienceLevel.INTERMEDIATE,
        competition=ProposalTier.TWENTY_TO_50,
        country="United Kingdom",
        total_spend=Decimal("0.0"),
    ),
    _Expected(
        uid="2096927543065537453",
        job_type=JobType.FIXED,
        budget_amount=Decimal("15"),
        rate_range=None,
        experience_level=ExperienceLevel.INTERMEDIATE,
        competition=ProposalTier.TWENTY_TO_50,
        country="United States",
        total_spend=Decimal("15192.75"),
    ),
    _Expected(
        uid="2096874654681407285",
        job_type=JobType.FIXED,
        budget_amount=Decimal("50"),
        rate_range=None,
        experience_level=ExperienceLevel.EXPERT,
        competition=ProposalTier.LESS_THAN_5,
        country="Australia",
        total_spend=Decimal("12953.67"),
    ),
]


@pytest.fixture(scope="module")
def raw_jobs_by_uid() -> dict[str, dict[str, object]]:
    by_uid: dict[str, dict[str, object]] = {}
    for raw in _load_raw_jobs():
        uid = raw["uid"]
        assert isinstance(uid, str)
        by_uid[uid] = raw
    return by_uid


@pytest.mark.parametrize("expected", EXPECTED, ids=lambda e: e.uid)
def test_map_job_matches_hand_verified_real_fixture_values(
    raw_jobs_by_uid: dict[str, dict[str, object]], expected: _Expected
) -> None:
    raw_dict = raw_jobs_by_uid[expected.uid]
    raw = RawJob.model_validate(raw_dict)

    job, facts = map_job(raw)

    assert job.external_id == expected.uid
    assert job.url == f"https://www.upwork.com/jobs/{raw_dict['ciphertext']}"
    assert job.job_type == expected.job_type
    if expected.budget_amount is None:
        assert job.budget is None
    else:
        assert job.budget is not None
        assert job.budget.amount == expected.budget_amount
        assert job.budget.currency == "USD"
    if expected.rate_range is None:
        assert job.rate_range is None
    else:
        assert job.rate_range is not None
        min_rate, max_rate = expected.rate_range
        assert job.rate_range.min_rate == min_rate
        assert job.rate_range.max_rate == max_rate
    assert job.experience_level == expected.experience_level
    assert job.competition == expected.competition
    assert job.client.country == expected.country
    assert job.client.total_spend == expected.total_spend
    assert job.entry_cost == 0
    assert facts.ciphertext == raw_dict["ciphertext"]
    summary = facts.summary_lines()
    assert len(summary) > 0
    assert any(str(raw_dict["ciphertext"]) in line for line in summary)


def test_map_job_returns_nonempty_skills_tuple_for_job_with_attrs(
    raw_jobs_by_uid: dict[str, dict[str, object]],
) -> None:
    raw = RawJob.model_validate(raw_jobs_by_uid["2096947778304263398"])

    job, _facts = map_job(raw)

    assert isinstance(job.skills, tuple)
    assert len(job.skills) > 0
    assert all(isinstance(skill, str) for skill in job.skills)


# --- _map_experience_level ---


def test_map_experience_level_recognizes_entry_pattern_not_present_in_fixture() -> None:
    assert _map_experience_level("jsn_EntryLevel_999") == ExperienceLevel.ENTRY


def test_map_experience_level_returns_none_for_none_input() -> None:
    assert _map_experience_level(None) is None


def test_map_experience_level_returns_none_for_unrecognized_string() -> None:
    assert _map_experience_level("garbage") is None


# --- _map_proposal_tier ---


def test_map_proposal_tier_recognizes_tier_not_present_in_fixture() -> None:
    assert (
        _map_proposal_tier("usnuxt_JobProposalTier_418.15to20") == ProposalTier.FIFTEEN_TO_20
    )


def test_map_proposal_tier_returns_unknown_for_none_input() -> None:
    assert _map_proposal_tier(None) == ProposalTier.UNKNOWN


def test_map_proposal_tier_returns_unknown_for_unrecognized_suffix() -> None:
    assert _map_proposal_tier("usnuxt_JobProposalTier_418.garbage") == ProposalTier.UNKNOWN


# --- _map_job_type ---


def test_map_job_type_maps_one_to_fixed() -> None:
    assert _map_job_type(1) == JobType.FIXED


def test_map_job_type_maps_two_to_hourly() -> None:
    assert _map_job_type(2) == JobType.HOURLY


def test_map_job_type_raises_permanent_error_for_unknown_int() -> None:
    with pytest.raises(PermanentError):
        _map_job_type(99)
