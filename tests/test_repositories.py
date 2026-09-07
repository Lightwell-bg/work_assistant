"""Round-trip тесты репозиториев на файловой SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.repositories import (
    SqlAlchemyDraftRepository,
    SqlAlchemyFilterSetRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyUpworkJobFactsRepository,
)
from upwork_assistant.adapters.db.tables import Base, JobPostingRow, UpworkJobFactsRow
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.filters import (
    FilterField,
    FilterMatchMode,
    FilterOperator,
    FilterRule,
    FilterSet,
)
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    ExperienceLevel,
    JobPosting,
    JobStatus,
    JobType,
    Money,
    ProposalTier,
    RateRange,
    Score,
)


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Файловая SQLite, изолированная на каждый тест, со свежей схемой."""
    db_path = tmp_path / "repositories_test.db"
    engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


def _make_job(external_id: str = "job-1", status: JobStatus = JobStatus.NEW) -> JobPosting:
    return JobPosting(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title="Python backend developer",
        description="Нужен бэкенд-разработчик на FastAPI",
        skills=("python", "fastapi", "postgresql"),
        job_type=JobType.HOURLY,
        budget=None,
        rate_range=RateRange(min_rate=Decimal("30"), max_rate=Decimal("60"), currency="USD"),
        duration="1 to 3 months",
        experience_level=ExperienceLevel.EXPERT,
        posted_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        client=ClientProfile(
            country="Germany",
            payment_verified=True,
            total_spend=Decimal("15000.50"),
            hire_rate=0.75,
            avg_rating=4.9,
            reviews_count=32,
        ),
        competition=ProposalTier.FIVE_TO_TEN,
        entry_cost=2,
        status=status,
    )


class TestJobRepository:
    async def test_upsert_and_get_round_trips_all_fields(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            loaded = await repo.get_by_external_id(job.external_id)

        assert loaded is not None
        assert loaded.external_id == job.external_id
        assert loaded.url == job.url
        assert loaded.title == job.title
        assert loaded.description == job.description
        assert loaded.skills == job.skills
        assert isinstance(loaded.skills, tuple)
        assert loaded.job_type == job.job_type
        assert loaded.budget is None
        assert loaded.rate_range is not None
        assert job.rate_range is not None
        assert loaded.rate_range.min_rate == job.rate_range.min_rate
        assert loaded.rate_range.max_rate == job.rate_range.max_rate
        assert loaded.duration == job.duration
        assert loaded.experience_level == job.experience_level
        # SQLite не хранит tzinfo даже в DateTime(timezone=True) — колонка
        # возвращает наивный datetime, поэтому сравниваем со снятым tzinfo.
        assert loaded.posted_at.replace(tzinfo=UTC) == job.posted_at
        assert loaded.client == job.client
        assert loaded.competition == job.competition
        assert loaded.entry_cost == job.entry_cost
        assert loaded.status == job.status

    async def test_upsert_with_budget_round_trips_money(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job(external_id="job-budget").model_copy(
            update={"budget": Money(amount=Decimal("500.00"), currency="EUR"), "rate_range": None}
        )
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            loaded = await repo.get_by_external_id(job.external_id)

        assert loaded is not None
        assert loaded.budget == job.budget
        assert loaded.rate_range is None

    async def test_get_by_external_id_missing_returns_none(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            assert await repo.get_by_external_id("missing") is None

    async def test_upsert_twice_updates_instead_of_duplicating(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        updated = job.model_copy(update={"title": "Senior Python backend developer"})

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job)
            await repo.upsert(updated)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            all_new = await repo.list_by_status(JobStatus.NEW)

        assert len(all_new) == 1
        assert all_new[0].title == "Senior Python backend developer"

    async def test_list_by_status_filters(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        new_job = _make_job(external_id="job-new", status=JobStatus.NEW)
        scored_job = _make_job(external_id="job-scored", status=JobStatus.SCORED)

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(new_job)
            await repo.upsert(scored_job)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            scored = await repo.list_by_status(JobStatus.SCORED)

        assert [job.external_id for job in scored] == ["job-scored"]

    async def test_exists(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        job = _make_job()
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            assert await repo.exists(job.external_id) is False
            await repo.upsert(job)
            await session.commit()
            assert await repo.exists(job.external_id) is True

    async def test_set_status_persists(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job)
            await repo.set_status(job.external_id, JobStatus.FILTERED_OUT)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            loaded = await repo.get_by_external_id(job.external_id)

        assert loaded is not None
        assert loaded.status == JobStatus.FILTERED_OUT

    async def test_save_score_persists(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        score = Score(value=8.5, reasoning="Хороший бюджет и понятное ТЗ")
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job)
            await repo.save_score(job.external_id, score)
            await session.commit()

        async with session_factory() as session:
            result = await session.get(JobPostingRow, 1)
        assert result is not None
        assert result.score_value == score.value
        assert result.score_reasoning == score.reasoning

    async def test_get_score_returns_saved_score(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        score = Score(value=8.5, reasoning="Хороший бюджет и понятное ТЗ")
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job)
            await repo.save_score(job.external_id, score)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            loaded = await repo.get_score(job.external_id)

        assert loaded == score

    async def test_get_score_returns_none_when_not_scored(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            assert await repo.get_score(job.external_id) is None

    async def test_get_score_returns_none_for_missing_job(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            assert await repo.get_score("missing") is None

    async def test_list_all_returns_every_job(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job_a = _make_job(external_id="job-a")
        job_b = _make_job(external_id="job-b", status=JobStatus.SCORED)

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            await repo.upsert(job_a)
            await repo.upsert(job_b)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            all_jobs = await repo.list_all()

        assert {job.external_id for job in all_jobs} == {"job-a", "job-b"}


class TestFilterSetRepository:
    def _make_filter_set(self, name: str = "preset-1") -> FilterSet:
        return FilterSet(
            name=name,
            rules=(
                FilterRule(field=FilterField.JOB_TYPE, operator=FilterOperator.EQ, value="hourly"),
                FilterRule(
                    field=FilterField.SKILLS,
                    operator=FilterOperator.CONTAINS_ANY,
                    value=("python", "django"),
                ),
                FilterRule(
                    field=FilterField.CLIENT_TOTAL_SPEND, operator=FilterOperator.GTE, value=1000
                ),
            ),
            match_mode=FilterMatchMode.ALL,
            is_active=True,
        )

    async def test_save_and_get_round_trips_rules_in_order(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        filter_set = self._make_filter_set()
        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            await repo.save(filter_set)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            loaded = await repo.get_by_name(filter_set.name)

        assert loaded is not None
        assert loaded.name == filter_set.name
        assert loaded.match_mode == filter_set.match_mode
        assert loaded.is_active == filter_set.is_active
        assert loaded.rules == filter_set.rules
        # Правило со skills должно вернуться tuple, а не list.
        assert isinstance(loaded.rules[1].value, tuple)

    async def test_save_again_replaces_rules_without_duplicates(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        filter_set = self._make_filter_set()
        replaced = FilterSet(
            name=filter_set.name,
            rules=(
                FilterRule(
                    field=FilterField.TITLE, operator=FilterOperator.CONTAINS, value="python"
                ),
            ),
            match_mode=filter_set.match_mode,
            is_active=False,
        )

        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            await repo.save(filter_set)
            await repo.save(replaced)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            loaded = await repo.get_by_name(filter_set.name)
            all_active = await repo.list_active()

        assert loaded is not None
        assert loaded.rules == replaced.rules
        assert loaded.is_active is False
        assert all_active == []

    async def test_list_active_excludes_inactive(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        active = self._make_filter_set(name="active-preset")
        inactive = FilterSet(name="inactive-preset", rules=(), is_active=False)

        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            await repo.save(active)
            await repo.save(inactive)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            names = {fs.name for fs in await repo.list_active()}

        assert names == {"active-preset"}

    async def test_delete_removes_filter_set(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        filter_set = self._make_filter_set()
        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            await repo.save(filter_set)
            await repo.delete(filter_set.name)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyFilterSetRepository(session)
            assert await repo.get_by_name(filter_set.name) is None


class TestDraftRepository:
    async def test_add_and_get_round_trips(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        draft = Draft(
            job_external_id=job.external_id,
            content="Здравствуйте! Готов взяться за проект...",
            status=DraftStatus.PENDING,
            created_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        )

        async with session_factory() as session:
            job_repo = SqlAlchemyJobRepository(session)
            draft_repo = SqlAlchemyDraftRepository(session)
            await job_repo.upsert(job)
            await draft_repo.add(job.external_id, draft)
            await session.commit()

        async with session_factory() as session:
            draft_repo = SqlAlchemyDraftRepository(session)
            loaded = await draft_repo.get_by_job(job.external_id)

        assert loaded is not None
        assert loaded.job_external_id == job.external_id
        assert loaded.content == draft.content
        assert loaded.status == draft.status

    async def test_set_status_persists(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()
        draft = Draft(
            job_external_id=job.external_id,
            content="Черновик отклика",
            status=DraftStatus.PENDING,
            created_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        )

        async with session_factory() as session:
            job_repo = SqlAlchemyJobRepository(session)
            draft_repo = SqlAlchemyDraftRepository(session)
            await job_repo.upsert(job)
            await draft_repo.add(job.external_id, draft)
            await draft_repo.set_status(job.external_id, DraftStatus.READY)
            await session.commit()

        async with session_factory() as session:
            draft_repo = SqlAlchemyDraftRepository(session)
            loaded = await draft_repo.get_by_job(job.external_id)

        assert loaded is not None
        assert loaded.status == DraftStatus.READY

    async def test_get_by_job_missing_returns_none(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            job_repo = SqlAlchemyJobRepository(session)
            draft_repo = SqlAlchemyDraftRepository(session)
            await job_repo.upsert(_make_job(external_id="job-no-draft"))
            await session.commit()
            assert await draft_repo.get_by_job("job-no-draft") is None


class TestUnitOfWork:
    async def test_failure_mid_transaction_rolls_back_everything(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()

        with pytest.raises(RuntimeError):
            async with unit_of_work(session_factory) as uow:
                await uow.jobs.upsert(job)
                raise RuntimeError("сбой пайплайна после сохранения вакансии")

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            assert await repo.get_by_external_id(job.external_id) is None

    async def test_success_commits(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        job = _make_job()

        async with unit_of_work(session_factory) as uow:
            await uow.jobs.upsert(job)

        async with session_factory() as session:
            repo = SqlAlchemyJobRepository(session)
            assert await repo.get_by_external_id(job.external_id) is not None


class TestUpworkJobFactsRepository:
    async def test_add_and_get_by_job_round_trips(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        payload: dict[str, object] = {"uid": "123", "title": "Python dev"}
        async with session_factory() as session:
            repo = SqlAlchemyUpworkJobFactsRepository(session)
            await repo.add("job-1", payload)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyUpworkJobFactsRepository(session)
            loaded = await repo.get_by_job("job-1")

        assert loaded == payload

    async def test_add_twice_upserts_instead_of_duplicating(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyUpworkJobFactsRepository(session)
            await repo.add("job-1", {"title": "First payload"})
            await repo.add("job-1", {"title": "Second payload"})
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyUpworkJobFactsRepository(session)
            loaded = await repo.get_by_job("job-1")
            rows = (
                (await session.execute(select(UpworkJobFactsRow))).scalars().all()
            )

        assert loaded == {"title": "Second payload"}
        assert len(rows) == 1

    async def test_get_by_job_returns_none_for_unknown_id(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyUpworkJobFactsRepository(session)
            assert await repo.get_by_job("missing") is None
