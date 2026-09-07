"""Тесты `RawJob` на реальном захвате payload'а поиска Upwork.

Основной регресс-guard — валидация всех 10 вакансий из реального фикстура:
если Upwork поменяет форму payload'а, это должно упасть здесь.
"""

from __future__ import annotations

import json
from pathlib import Path

from upwork_assistant.adapters.upwork.payload_models import RawJob
from upwork_assistant.adapters.upwork.ssr_state import extract_jobs_search

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "upwork" / "nuxt_state_search_python.json"


def _load_raw_jobs() -> list[dict[str, object]]:
    nuxt_state = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    jobs, _paging = extract_jobs_search(nuxt_state)
    return jobs  # type: ignore[return-value]


def test_all_ten_real_jobs_validate_against_raw_job_schema() -> None:
    raw_jobs = _load_raw_jobs()

    assert len(raw_jobs) == 10
    for raw in raw_jobs:
        RawJob.model_validate(raw)


def test_fixed_price_job_validates_with_exact_real_field_values() -> None:
    raw_jobs = _load_raw_jobs()
    raw = next(j for j in raw_jobs if j["uid"] == "2096947778304263398")

    job = RawJob.model_validate(raw)

    assert job.uid == "2096947778304263398"
    assert job.ciphertext == "~022096947778304263398"
    assert job.title == "Developer Needed for a Social Media Creator Discovery Tool"
    assert job.type == 1
    assert job.amount.amount == 250
    assert job.hourlyBudget.min == 0
    assert job.hourlyBudget.max == 0
    assert job.client.location is not None
    assert job.client.location.country == "France"
    assert job.client.isPaymentVerified is True
    assert job.client.totalSpent == "30031.28"
    assert job.client.totalReviews == 79
    assert job.client.totalFeedback == 4.97
    assert job.tierText == "jsn_Intermediate_206"
    assert job.proposalsTier == "usnuxt_JobProposalTier_418.lessThan5"
    assert [skill.prefLabel for skill in job.attrs] == [
        "Python",
        "API Integration",
        "Data Extraction",
        "Automation",
        "Data Mining",
    ]


def test_hourly_job_validates_with_exact_real_field_values() -> None:
    raw_jobs = _load_raw_jobs()
    raw = next(j for j in raw_jobs if j["uid"] == "2096947624213923046")

    job = RawJob.model_validate(raw)

    assert job.uid == "2096947624213923046"
    assert job.ciphertext == "~022096947624213923046"
    assert job.title == "Jr Data Analyst - Remote UTC+0 to UTC+3"
    assert job.type == 2
    assert job.amount.amount == 0
    assert job.hourlyBudget.min == 10
    assert job.hourlyBudget.max == 14
    assert job.client.location is not None
    assert job.client.location.country == "Thailand"
    assert job.client.isPaymentVerified is True
    assert job.client.totalSpent == "0.0"
    assert job.client.totalReviews == 0
    assert job.tierText == "jsn_Intermediate_206"
    assert job.proposalsTier == "usnuxt_JobProposalTier_418.lessThan5"
    assert [skill.prefLabel for skill in job.attrs] == ["SQL"]


def test_raw_job_ignores_unknown_extra_field_for_forward_compatibility() -> None:
    raw_jobs = _load_raw_jobs()
    raw = dict(raw_jobs[0])
    raw["someNewUpworkField"] = "xyz"

    job = RawJob.model_validate(raw)

    assert not hasattr(job, "someNewUpworkField")
