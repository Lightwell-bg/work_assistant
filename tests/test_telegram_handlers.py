"""Тесты логики хендлера кнопки «Отклик отправлен» — без диспетчерской машинерии aiogram.

`handle_draft_sent` — обычная async-функция, вызывается напрямую с фейковым
`CallbackQuery`-подобным объектом и реальной файловой SQLite (тот же паттерн,
что и в `tests/test_repositories.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.repositories import (
    SqlAlchemyDraftRepository,
    SqlAlchemyJobRepository,
)
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.telegram.callbacks import draft_sent_callback_data
from upwork_assistant.adapters.telegram.handlers import handle_draft_sent
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    JobPosting,
    JobType,
    RateRange,
)


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "handlers_test.db"
    engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@dataclass
class FakeMessage:
    text: str
    edited: list[tuple[str, object | None]] = field(default_factory=list)
    raise_on_edit: bool = False

    async def edit_text(self, text: str, reply_markup: object | None = None) -> None:
        if self.raise_on_edit:
            raise RuntimeError("сообщение устарело")
        self.edited.append((text, reply_markup))


@dataclass
class FakeCallbackQuery:
    data: str | None
    message: FakeMessage | None
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str = "") -> None:
        self.answers.append(text)


async def _seed_job_with_draft(
    session_factory: async_sessionmaker[AsyncSession], external_id: str
) -> None:
    job = JobPosting(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title="Python backend developer",
        description="desc",
        job_type=JobType.HOURLY,
        rate_range=RateRange(min_rate=Decimal("30"), max_rate=Decimal("60")),
        posted_at=datetime(2026, 9, 1, tzinfo=UTC),
        client=ClientProfile(),
    )
    draft = Draft(
        job_external_id=external_id,
        content="Черновик отклика",
        status=DraftStatus.READY,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    async with session_factory() as session:
        job_repo = SqlAlchemyJobRepository(session)
        draft_repo = SqlAlchemyDraftRepository(session)
        await job_repo.upsert(job)
        await draft_repo.add(external_id, draft)
        await session.commit()


async def test_handle_draft_sent_marks_draft_as_sent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    external_id = "job-1"
    await _seed_job_with_draft(session_factory, external_id)
    message = FakeMessage(text="Черновик отклика")
    callback = FakeCallbackQuery(data=draft_sent_callback_data(external_id), message=message)

    await handle_draft_sent(callback, session_factory)  # type: ignore[arg-type]

    async with session_factory() as session:
        draft_repo = SqlAlchemyDraftRepository(session)
        loaded = await draft_repo.get_by_job(external_id)
    assert loaded is not None
    assert loaded.status == DraftStatus.SENT

    assert message.edited == [("Черновик отклика\n\n✅ Отправлено", None)]
    assert callback.answers == ["Отмечено как отправленное"]


async def test_handle_draft_sent_survives_edit_text_failure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    external_id = "job-2"
    await _seed_job_with_draft(session_factory, external_id)
    message = FakeMessage(text="Черновик отклика", raise_on_edit=True)
    callback = FakeCallbackQuery(data=draft_sent_callback_data(external_id), message=message)

    await handle_draft_sent(callback, session_factory)  # type: ignore[arg-type]

    async with session_factory() as session:
        draft_repo = SqlAlchemyDraftRepository(session)
        loaded = await draft_repo.get_by_job(external_id)
    assert loaded is not None
    assert loaded.status == DraftStatus.SENT
    assert callback.answers == ["Отмечено как отправленное"]


async def test_handle_draft_sent_ignores_unrelated_callback_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    callback = FakeCallbackQuery(data="some:other:callback", message=None)

    await handle_draft_sent(callback, session_factory)  # type: ignore[arg-type]

    assert callback.answers == [""]


async def test_handle_draft_sent_ignores_none_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    callback = FakeCallbackQuery(data=None, message=None)

    await handle_draft_sent(callback, session_factory)  # type: ignore[arg-type]

    assert callback.answers == [""]
