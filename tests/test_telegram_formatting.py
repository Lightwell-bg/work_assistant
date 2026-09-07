"""Тесты форматирования Telegram-сообщений: только plain-text, без разметки."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from upwork_assistant.adapters.telegram.formatting import format_draft_message, format_job_summary
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    ExperienceLevel,
    JobPosting,
    JobType,
    Money,
    ProposalTier,
    RateRange,
    Score,
)


def _make_job(**overrides: object) -> JobPosting:
    defaults: dict[str, object] = {
        "external_id": "12345678901234567",
        "url": "https://www.upwork.com/jobs/12345678901234567",
        "title": "Python backend developer needed",
        "description": "Long description " * 50,
        "skills": ("python", "fastapi"),
        "job_type": JobType.HOURLY,
        "budget": None,
        "rate_range": RateRange(min_rate=Decimal("30"), max_rate=Decimal("60"), currency="USD"),
        "duration": "1 to 3 months",
        "experience_level": ExperienceLevel.EXPERT,
        "posted_at": datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        "client": ClientProfile(
            country="Germany",
            payment_verified=True,
            total_spend=Decimal("15000.50"),
            hire_rate=0.75,
            avg_rating=4.9,
            reviews_count=32,
        ),
        "competition": ProposalTier.FIVE_TO_TEN,
        "entry_cost": 2,
    }
    defaults.update(overrides)
    return JobPosting(**defaults)


def test_format_job_summary_includes_title_url_and_score_for_hourly_job() -> None:
    job = _make_job()
    score = Score(value=8.5, reasoning="Хорошее совпадение по стеку")

    summary = format_job_summary(job, score)

    assert job.title in summary
    assert job.url in summary
    assert "8.5" in summary
    assert "Хорошее совпадение по стеку" in summary
    assert "30" in summary and "60" in summary
    assert job.description not in summary
    assert len(summary) < 1500


def test_format_job_summary_includes_budget_for_fixed_job() -> None:
    job = _make_job(
        job_type=JobType.FIXED,
        rate_range=None,
        budget=Money(amount=Decimal("500.00"), currency="USD"),
    )
    score = Score(value=6.0, reasoning="Средняя релевантность")

    summary = format_job_summary(job, score)

    assert job.title in summary
    assert job.url in summary
    assert "500.00" in summary
    assert "6.0" in summary


def test_format_draft_message_returns_content_as_is_when_short() -> None:
    draft = Draft(
        job_external_id="job-1",
        content="Здравствуйте! Готов взяться за проект.",
        status=DraftStatus.READY,
        created_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
    )

    assert format_draft_message(draft) == draft.content


def test_format_draft_message_truncates_long_content() -> None:
    long_content = "x" * 5000
    draft = Draft(
        job_external_id="job-1",
        content=long_content,
        status=DraftStatus.READY,
        created_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
    )

    formatted = format_draft_message(draft)

    assert len(formatted) < len(long_content)
    assert formatted.endswith("[обрезано, полный текст в БД]")
