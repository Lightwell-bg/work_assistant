# Поиски в БД и веб-панели — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести поисковые запросы из `.env` в БД и сделать их редактируемыми через веб-панель, не ломая работающий опрос Upwork.

**Architecture:** Новая таблица `search_queries` (источник + имя + запрос + флаг активности) с репозиторием в существующем `UnitOfWork`. `IngestService` читает активные поиски своего источника из БД на каждый цикл и передаёт их в `JobSource.poll(searches)` — адаптер остаётся без знания о хранилище, ровно как это уже сделано с фильтрами. Значение `UPWORK_SEARCH_URLS` из `.env` однократно засевается в пустую таблицу при старте.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async) + aiosqlite, Alembic, Pydantic v2, pytest, vanilla JS в одной HTML-странице.

**Spec:** `docs/superpowers/specs/2026-09-08-linkedin-source-design.md` (разделы «Конфигурация поисков через веб» и «Перенос UPWORK_SEARCH_URLS»)

## Global Constraints

- Комментарии и докстринги — на русском, объясняют «почему», а не «что».
- `from __future__ import annotations` в каждом Python-модуле.
- ruff line-length 100; mypy strict для `domain`, `ports`, `services`.
- `.env` и `.env.example` держать структурно идентичными (одинаковые переменные в одинаковом порядке, отличаются только значения). Проверка: `diff <(sed -E 's/=.*/=<V>/' .env) <(sed -E 's/=.*/=<V>/' .env.example)` должен быть пустым.
- Миграции пишутся руками, не автогенерацией; следующий свободный номер — `0004` (в спеке этот номер был занят `multi_source`, но поиски делаются раньше, поэтому нумерация сдвигается: `0004_search_queries`).
- Все команды запускать из корня репозитория с активированным venv: `source .venv/Scripts/activate`.
- Полная проверка перед коммитом: `ruff check src tests && mypy src tests && pytest -q`.

---

### Task 1: Доменная модель поиска

**Files:**
- Modify: `src/upwork_assistant/domain/models.py`
- Test: `tests/test_search_query_model.py`

**Interfaces:**
- Consumes: ничего (первая задача)
- Produces: `JobSourceName` (StrEnum: `UPWORK = "upwork"`, `LINKEDIN = "linkedin"`), `SearchQuery` (frozen Pydantic: `source: JobSourceName`, `name: str`, `query: str`, `is_active: bool = True`)

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_search_query_model.py`:

```python
"""Тесты доменной модели поискового запроса."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from upwork_assistant.domain.models import JobSourceName, SearchQuery


def test_search_query_holds_source_name_and_query() -> None:
    search = SearchQuery(
        source=JobSourceName.UPWORK,
        name="python_recency",
        query="https://www.upwork.com/nx/search/jobs/?q=python&sort=recency",
    )

    assert search.source is JobSourceName.UPWORK
    assert search.name == "python_recency"
    assert search.is_active is True


def test_search_query_is_frozen() -> None:
    search = SearchQuery(source=JobSourceName.LINKEDIN, name="ml", query="https://x")

    with pytest.raises(ValidationError):
        search.name = "other"  # type: ignore[misc]


def test_job_source_name_values_are_stable_strings() -> None:
    # Значения уходят в БД и в URL API — менять их нельзя без миграции.
    assert JobSourceName.UPWORK.value == "upwork"
    assert JobSourceName.LINKEDIN.value == "linkedin"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_search_query_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'JobSourceName'`

- [ ] **Step 3: Реализовать модель**

В `src/upwork_assistant/domain/models.py` дописать в конец файла:

```python
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
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `pytest tests/test_search_query_model.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Проверить весь проект и закоммитить**

Run: `ruff check src tests && mypy src tests && pytest -q`
Expected: всё зелёное

```bash
git add src/upwork_assistant/domain/models.py tests/test_search_query_model.py
git commit -m "feat: доменная модель сохранённого поиска"
```

---

### Task 2: Таблица `search_queries` и миграция

**Files:**
- Modify: `src/upwork_assistant/adapters/db/tables.py`
- Create: `migrations/versions/0004_search_queries.py`
- Test: `tests/test_migrations.py`

**Interfaces:**
- Consumes: `JobSourceName` из Task 1
- Produces: `SearchQueryRow` (таблица `search_queries`, колонки `id`, `source`, `name`, `query`, `is_active`, `created_at`, `updated_at`; уникальный индекс по паре `(source, name)`)

- [ ] **Step 1: Написать падающий тест**

В `tests/test_migrations.py` уже есть `test_upgrade_head_creates_all_tables` со списком ожидаемых таблиц. Дописать в его множество строку `"search_queries",` — оно проверяется через `<= tables`, так что добавление строки его ужесточает:

```python
    assert {
        "job_postings",
        "filter_sets",
        "filter_rules",
        "drafts",
        "llm_usage",
        "upwork_job_facts",
        "search_queries",
    } <= tables
```

И следом в том же файле добавить отдельный тест на колонки. Хелпер `_alembic_config` в файле уже есть, он принимает **строку URL**, а не путь:

```python
def test_upgrade_head_creates_search_queries_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "search_queries_test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(cfg, "head")

    inspector = inspect(create_engine(f"sqlite:///{db_path}"))
    columns = {col["name"] for col in inspector.get_columns("search_queries")}
    assert columns == {
        "id",
        "source",
        "name",
        "query",
        "is_active",
        "created_at",
        "updated_at",
    }
```

Импорты `Path`, `command`, `inspect`, `create_engine` в файле уже есть — новых не нужно.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_migrations.py -q`
Expected: FAIL — `assert 'search_queries' in [...]`

- [ ] **Step 3: Добавить таблицу**

В `src/upwork_assistant/adapters/db/tables.py` дописать (стиль — как у существующих `DraftRow`/`LLMUsageRow`):

```python
class SearchQueryRow(Base):
    """Сохранённый поиск. Пара `(source, name)` уникальна: имя — это то, чем
    пользователь адресует поиск в панели и в API, и оно не должно
    пересекаться внутри одного источника."""

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("source", "name", name="uq_search_queries_source_name"),)
```

В импорты этого файла добавить `UniqueConstraint` к уже импортируемым именам из `sqlalchemy`.

- [ ] **Step 4: Написать миграцию**

Создать `migrations/versions/0004_search_queries.py` (стиль — как `0003_upwork_job_facts.py`):

```python
"""search queries table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08

Написана руками (не автогенерацией), как и 0001-0003 — таблица должна точно
соответствовать `adapters/db/tables.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "name", name="uq_search_queries_source_name"),
    )
    op.create_index("ix_search_queries_source", "search_queries", ["source"])


def downgrade() -> None:
    op.drop_table("search_queries")
```

- [ ] **Step 5: Убедиться, что тест проходит**

Run: `pytest tests/test_migrations.py -q`
Expected: PASS

- [ ] **Step 6: Проверить и закоммитить**

Run: `ruff check src tests && mypy src tests && pytest -q`

```bash
git add src/upwork_assistant/adapters/db/tables.py migrations/versions/0004_search_queries.py tests/test_migrations.py
git commit -m "feat: таблица search_queries и миграция 0004"
```

---

### Task 3: Порт и репозиторий поисков

**Files:**
- Modify: `src/upwork_assistant/ports/repositories.py`
- Modify: `src/upwork_assistant/adapters/db/repositories.py`
- Modify: `src/upwork_assistant/adapters/db/uow.py`
- Test: `tests/test_search_query_repository.py`

**Interfaces:**
- Consumes: `SearchQuery`, `JobSourceName` (Task 1), `SearchQueryRow` (Task 2)
- Produces: `SearchQueryRepository` Protocol и `SqlAlchemySearchQueryRepository` с методами `save(search: SearchQuery) -> None` (upsert по паре `(source, name)`), `list_all() -> list[SearchQuery]`, `list_active(source: JobSourceName) -> list[SearchQuery]`, `delete(source: JobSourceName, name: str) -> None` (кидает `UnknownSearchQueryError`), `count() -> int`. Доступен как `uow.searches`.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_search_query_repository.py`. Фикстура ниже — тот же паттерн временной SQLite, что уже используется в `tests/test_ingest_service.py` и `tests/test_repositories.py`. `asyncio_mode = "auto"` в `pyproject.toml` уже включён, поэтому `async def`-тесты и async-фикстуры не требуют маркеров:

```python
"""Round-trip тесты репозитория сохранённых поисков на файловой SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.repositories import UnknownSearchQueryError
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'searches_test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_save_and_list_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    search = SearchQuery(
        source=JobSourceName.UPWORK,
        name="python",
        query="https://www.upwork.com/nx/search/jobs/?q=python",
    )

    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(search)

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert stored == [search]


async def test_save_twice_with_same_name_replaces_not_duplicates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="python", query="https://old")
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="python", query="https://new")
        )

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert len(stored) == 1
    assert stored[0].query == "https://new"


async def test_same_name_under_different_sources_coexist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="python", query="https://upwork")
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.LINKEDIN, name="python", query="https://linkedin")
        )

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert len(stored) == 2


async def test_list_active_filters_by_source_and_flag(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="on", query="https://a")
        )
        await uow.searches.save(
            SearchQuery(
                source=JobSourceName.UPWORK, name="off", query="https://b", is_active=False
            )
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.LINKEDIN, name="other", query="https://c")
        )

    async with unit_of_work(session_factory) as uow:
        active = await uow.searches.list_active(JobSourceName.UPWORK)

    assert [search.name for search in active] == ["on"]


async def test_delete_removes_only_that_search(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="a", query="https://a")
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="b", query="https://b")
        )

    async with unit_of_work(session_factory) as uow:
        await uow.searches.delete(JobSourceName.UPWORK, "a")

    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()

    assert [search.name for search in stored] == ["b"]


async def test_delete_unknown_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(UnknownSearchQueryError):
        async with unit_of_work(session_factory) as uow:
            await uow.searches.delete(JobSourceName.UPWORK, "missing")


async def test_count_reflects_saved_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 0
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="a", query="https://a")
        )

    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 1
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_search_query_repository.py -q`
Expected: FAIL — `ImportError: cannot import name 'UnknownSearchQueryError'`

- [ ] **Step 3: Добавить порт**

В `src/upwork_assistant/ports/repositories.py` дописать (импорт `JobSourceName`, `SearchQuery` добавить к существующему импорту из `domain.models`):

```python
class SearchQueryRepository(Protocol):
    """Хранение сохранённых поисков.

    Раньше это был `UPWORK_SEARCH_URLS` в `.env`: правка требовала доступа к
    файлам на сервере и перезапуска. Теперь — обычные строки в БД, которые
    сервисы перечитывают на каждый цикл.
    """

    async def save(self, search: SearchQuery) -> None:
        """Создать поиск или заменить существующий по паре `(source, name)`."""
        ...

    async def list_all(self) -> list[SearchQuery]: ...

    async def list_active(self, source: JobSourceName) -> list[SearchQuery]: ...

    async def delete(self, source: JobSourceName, name: str) -> None: ...

    async def count(self) -> int:
        """Сколько всего поисков — по этому числу решается разовый засев из `.env`."""
        ...
```

- [ ] **Step 4: Реализовать репозиторий**

В `src/upwork_assistant/adapters/db/repositories.py` дописать (рядом с существующими `UnknownJobError`/`UnknownFilterSetError`):

```python
class UnknownSearchQueryError(PermanentError):
    """Операция адресована поиску, которого нет в БД."""


def _search_to_domain(row: SearchQueryRow) -> SearchQuery:
    return SearchQuery(
        source=JobSourceName(row.source),
        name=row.name,
        query=row.query,
        is_active=row.is_active,
    )


class SqlAlchemySearchQueryRepository:
    """Реализация `SearchQueryRepository` поверх одной `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_row(self, source: JobSourceName, name: str) -> SearchQueryRow | None:
        result = await self._session.execute(
            select(SearchQueryRow).where(
                SearchQueryRow.source == source.value, SearchQueryRow.name == name
            )
        )
        return result.scalar_one_or_none()

    async def save(self, search: SearchQuery) -> None:
        row = await self._get_row(search.source, search.name)
        if row is None:
            self._session.add(
                SearchQueryRow(
                    source=search.source.value,
                    name=search.name,
                    query=search.query,
                    is_active=search.is_active,
                )
            )
        else:
            row.query = search.query
            row.is_active = search.is_active
        await self._session.flush()

    async def list_all(self) -> list[SearchQuery]:
        result = await self._session.execute(
            select(SearchQueryRow).order_by(SearchQueryRow.source, SearchQueryRow.name)
        )
        return [_search_to_domain(row) for row in result.scalars().all()]

    async def list_active(self, source: JobSourceName) -> list[SearchQuery]:
        result = await self._session.execute(
            select(SearchQueryRow)
            .where(SearchQueryRow.source == source.value, SearchQueryRow.is_active)
            .order_by(SearchQueryRow.name)
        )
        return [_search_to_domain(row) for row in result.scalars().all()]

    async def delete(self, source: JobSourceName, name: str) -> None:
        row = await self._get_row(source, name)
        if row is None:
            raise UnknownSearchQueryError(f"Поиск {name!r} источника {source.value!r} не найден")
        await self._session.delete(row)
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(SearchQueryRow))
        return int(result.scalar_one())
```

В импорты файла добавить: `SearchQueryRow` к именам из `adapters.db.tables`, `JobSourceName` и `SearchQuery` к именам из `domain.models`, `func` к именам из `sqlalchemy`.

- [ ] **Step 5: Подключить в UnitOfWork**

В `src/upwork_assistant/adapters/db/uow.py` добавить `SqlAlchemySearchQueryRepository` в импорт и в конструктор:

```python
        self.searches = SqlAlchemySearchQueryRepository(session)
```

- [ ] **Step 6: Убедиться, что тесты проходят**

Run: `pytest tests/test_search_query_repository.py -q`
Expected: PASS (7 passed)

- [ ] **Step 7: Проверить и закоммитить**

Run: `ruff check src tests && mypy src tests && pytest -q`

```bash
git add src/upwork_assistant/ports/repositories.py src/upwork_assistant/adapters/db/repositories.py src/upwork_assistant/adapters/db/uow.py tests/test_search_query_repository.py
git commit -m "feat: репозиторий сохранённых поисков"
```

---

### Task 4: Разовый засев поисков из `.env`

**Files:**
- Create: `src/upwork_assistant/services/search_seed.py`
- Modify: `src/upwork_assistant/__main__.py`
- Test: `tests/test_search_seed.py`

**Interfaces:**
- Consumes: `uow.searches` (Task 3), `Settings.search_urls`
- Produces: `async def seed_searches_from_env(session_factory, search_urls: Sequence[str]) -> int` — возвращает число созданных записей; ничего не делает, если таблица непуста или список пуст.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_search_seed.py`:

```python
"""Тесты разового засева поисков из `.env` в БД."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.db.tables import Base
from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery
from upwork_assistant.services.search_seed import seed_searches_from_env


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed_test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_seeds_urls_into_empty_table(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    created = await seed_searches_from_env(
        session_factory, ["https://www.upwork.com/a", "https://www.upwork.com/b"]
    )

    assert created == 2
    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_active(JobSourceName.UPWORK)
    assert [search.query for search in stored] == [
        "https://www.upwork.com/a",
        "https://www.upwork.com/b",
    ]


async def test_does_nothing_when_table_not_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="mine", query="https://mine")
        )

    created = await seed_searches_from_env(session_factory, ["https://www.upwork.com/a"])

    assert created == 0
    async with unit_of_work(session_factory) as uow:
        stored = await uow.searches.list_all()
    assert [search.name for search in stored] == ["mine"]


async def test_does_nothing_when_env_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    created = await seed_searches_from_env(session_factory, [])

    assert created == 0
    async with unit_of_work(session_factory) as uow:
        assert await uow.searches.count() == 0
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_search_seed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'upwork_assistant.services.search_seed'`

- [ ] **Step 3: Реализовать засев**

Создать `src/upwork_assistant/services/search_seed.py`:

```python
"""Разовый перенос поисков из `.env` в БД.

Поиски переехали из `UPWORK_SEARCH_URLS` в таблицу, чтобы правиться через
веб-панель. Чтобы старые установки не остались без поисков после обновления,
при старте пустая таблица один раз наполняется значениями из `.env`. Условие
«таблица пуста» намеренно грубое: как только пользователь завёл хоть один
поиск сам, `.env` больше не вмешивается и не воскрешает удалённое.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.domain.models import JobSourceName, SearchQuery

logger = logging.getLogger(__name__)


async def seed_searches_from_env(
    session_factory: async_sessionmaker[AsyncSession],
    search_urls: Sequence[str],
) -> int:
    """Засеять поиски Upwork из `.env`. Возвращает число созданных записей."""
    if not search_urls:
        return 0

    async with unit_of_work(session_factory) as uow:
        if await uow.searches.count() > 0:
            return 0

        for index, url in enumerate(search_urls, start=1):
            await uow.searches.save(
                SearchQuery(
                    source=JobSourceName.UPWORK,
                    name=f"upwork_{index}",
                    query=url,
                    is_active=True,
                )
            )

    logger.info("Перенесено поисков из .env в БД: %d", len(search_urls))
    return len(search_urls)
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_search_seed.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Вызвать засев при старте**

В `src/upwork_assistant/__main__.py`, внутри `async with build_container(settings) as container:`, **перед** `container.scheduler.start()`, добавить:

```python
        await seed_searches_from_env(container.session_factory, settings.search_urls)
```

и импорт наверху файла:

```python
from upwork_assistant.services.search_seed import seed_searches_from_env
```

Засев именно здесь, а не в `build_container`: контейнер собирается и в тестах, а обращаться к БД при сборке он не должен (то же правило, по которому там не запускаются бот и планировщик).

- [ ] **Step 6: Проверить и закоммитить**

Run: `ruff check src tests && mypy src tests && pytest -q`

```bash
git add src/upwork_assistant/services/search_seed.py src/upwork_assistant/__main__.py tests/test_search_seed.py
git commit -m "feat: разовый перенос поисков из .env в БД"
```

---

### Task 5: REST API поисков

**Files:**
- Modify: `src/upwork_assistant/api/schemas.py`
- Create: `src/upwork_assistant/api/routes/searches.py`
- Modify: `src/upwork_assistant/app.py`
- Test: `tests/test_api_searches.py`

**Interfaces:**
- Consumes: `uow.searches` (Task 3), `UowDep` из `api/deps.py`
- Produces: `SearchQueryIn` (`query: str`, `is_active: bool = True`), `SearchQueryOut` (`source`, `name`, `query`, `is_active`); эндпоинты `GET /searches` (опционально `?source=`), `PUT /searches/{source}/{name}`, `DELETE /searches/{source}/{name}`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_api_searches.py`. Способ поднять клиент — ровно тот же, что в существующем `tests/test_api_filters.py`: фикстуры `settings` и `api_container` из `tests/conftest.py` плюс `create_app(settings, container=api_container)` внутри `with TestClient(app)`. Готовой фикстуры, отдающей `TestClient`, в проекте нет и заводить её не нужно — новых фикстур этот план не добавляет.

```python
"""Тесты REST-эндпоинтов сохранённых поисков."""

from __future__ import annotations

from fastapi.testclient import TestClient

from upwork_assistant.app import create_app
from upwork_assistant.config import Settings
from upwork_assistant.container import Container


def test_list_is_empty_initially(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.get("/searches")

    assert response.status_code == 200
    assert response.json() == []


def test_put_creates_and_get_returns_it(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put(
            "/searches/upwork/python",
            json={
                "query": "https://www.upwork.com/nx/search/jobs/?q=python",
                "is_active": True,
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "source": "upwork",
            "name": "python",
            "query": "https://www.upwork.com/nx/search/jobs/?q=python",
            "is_active": True,
        }

        listed = client.get("/searches").json()

    assert [item["name"] for item in listed] == ["python"]


def test_put_twice_replaces_not_duplicates(
    settings: Settings, api_container: Container
) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/searches/upwork/python", json={"query": "https://old"})
        client.put("/searches/upwork/python", json={"query": "https://new"})

        listed = client.get("/searches").json()

    assert len(listed) == 1
    assert listed[0]["query"] == "https://new"


def test_list_filters_by_source(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/searches/upwork/a", json={"query": "https://a"})
        client.put("/searches/linkedin/b", json={"query": "https://b"})

        listed = client.get("/searches", params={"source": "linkedin"}).json()

    assert [item["name"] for item in listed] == ["b"]


def test_delete_removes_it(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        client.put("/searches/upwork/python", json={"query": "https://a"})

        response = client.delete("/searches/upwork/python")

        assert response.status_code == 204
        assert client.get("/searches").json() == []


def test_delete_unknown_returns_404(settings: Settings, api_container: Container) -> None:
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.delete("/searches/upwork/missing")

    assert response.status_code == 404


def test_put_with_unknown_source_returns_422(
    settings: Settings, api_container: Container
) -> None:
    """`JobSourceName` в пути — enum, поэтому чужая площадка отсекается
    валидацией FastAPI, а не долетает строкой до репозитория."""
    app = create_app(settings, container=api_container)
    with TestClient(app) as client:
        response = client.put("/searches/hh/python", json={"query": "https://a"})

    assert response.status_code == 422
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_api_searches.py -q`
Expected: FAIL — 404 на `/searches` (роутер ещё не подключён)

- [ ] **Step 3: Добавить схемы**

В `src/upwork_assistant/api/schemas.py` дописать (импорт `JobSourceName` добавить к существующему импорту из `domain.models`):

```python
class SearchQueryIn(BaseModel):
    """Тело запроса на создание/замену поиска. Источник и имя — в пути URL."""

    query: str
    is_active: bool = True


class SearchQueryOut(BaseModel):
    """Сохранённый поиск на выходе."""

    source: JobSourceName
    name: str
    query: str
    is_active: bool


def search_query_out_from_domain(search: SearchQuery) -> SearchQueryOut:
    """Собрать выходной DTO поиска из доменной модели."""
    return SearchQueryOut(
        source=search.source,
        name=search.name,
        query=search.query,
        is_active=search.is_active,
    )
```

`SearchQuery` добавить к импорту из `domain.models`.

- [ ] **Step 4: Добавить роутер**

Создать `src/upwork_assistant/api/routes/searches.py`:

```python
"""Управление сохранёнными поисками.

Источник и имя адресуют поиск в пути (`/searches/{source}/{name}`), поэтому
`PUT` — это идемпотентное «создать или заменить», как и у пресетов фильтров.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from upwork_assistant.adapters.db.repositories import UnknownSearchQueryError
from upwork_assistant.api.deps import UowDep
from upwork_assistant.api.schemas import (
    SearchQueryIn,
    SearchQueryOut,
    search_query_out_from_domain,
)
from upwork_assistant.domain.models import JobSourceName, SearchQuery

router = APIRouter(prefix="/searches", tags=["searches"])


@router.get("", response_model=list[SearchQueryOut])
async def list_searches(
    uow: UowDep,
    source: JobSourceName | None = Query(default=None),
) -> list[SearchQueryOut]:
    """Все поиски, опционально только одного источника (включая выключенные)."""
    searches = await uow.searches.list_all()
    if source is not None:
        searches = [search for search in searches if search.source is source]
    return [search_query_out_from_domain(search) for search in searches]


@router.put("/{source}/{name}", response_model=SearchQueryOut)
async def put_search(
    source: JobSourceName, name: str, body: SearchQueryIn, uow: UowDep
) -> SearchQueryOut:
    """Создать поиск или полностью заменить существующий."""
    search = SearchQuery(
        source=source, name=name, query=body.query, is_active=body.is_active
    )
    await uow.searches.save(search)
    return search_query_out_from_domain(search)


@router.delete("/{source}/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(source: JobSourceName, name: str, uow: UowDep) -> None:
    try:
        await uow.searches.delete(source, name)
    except UnknownSearchQueryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
```

- [ ] **Step 5: Подключить роутер**

В `src/upwork_assistant/app.py` добавить `searches` в импорт роутеров и строку рядом с остальными:

```python
    app.include_router(searches.router)
```

- [ ] **Step 6: Убедиться, что тесты проходят**

Run: `pytest tests/test_api_searches.py -q`
Expected: PASS (7 passed)

- [ ] **Step 7: Проверить и закоммитить**

Run: `ruff check src tests && mypy src tests && pytest -q`

```bash
git add src/upwork_assistant/api/schemas.py src/upwork_assistant/api/routes/searches.py src/upwork_assistant/app.py tests/test_api_searches.py
git commit -m "feat: REST-эндпоинты сохранённых поисков"
```

---

### Task 6: Источник получает поиски из БД

**Files:**
- Modify: `src/upwork_assistant/ports/job_source.py`
- Modify: `src/upwork_assistant/adapters/upwork/source.py`
- Modify: `src/upwork_assistant/services/ingest_service.py`
- Test: `tests/test_ingest_service.py`

**Interfaces:**
- Consumes: `uow.searches.list_active` (Task 3)
- Produces: `JobSource.poll(searches: Sequence[str]) -> list[PolledJob]` — сигнатура порта меняется; `UpworkJobSource.poll` принимает список URL и больше не читает `settings.search_urls`

- [ ] **Step 1: Написать падающий тест**

В `tests/test_ingest_service.py` фейк `FakeJobSource` уже есть в таком виде:

```python
class FakeJobSource:
    """Возвращает заранее заданный список вакансий на каждый `poll()`."""

    def __init__(self, jobs: list[JobPosting]) -> None:
        self._jobs = jobs
        self.poll_calls = 0

    async def poll(self) -> list[PolledJob]:
        self.poll_calls += 1
        return [PolledJob(job=job, raw_payload=None) for job in self._jobs]
```

Заменить его на версию, принимающую поиски и запоминающую их (конструктор не меняется — все существующие тесты продолжают собирать фейк как `FakeJobSource(jobs)`):

```python
class FakeJobSource:
    """Возвращает заранее заданный список вакансий на каждый `poll()`.

    Полученные поиски запоминаются: `IngestService` обязан взять их из БД и
    передать сюда, а не источник — сходить за ними самостоятельно.
    """

    def __init__(self, jobs: list[JobPosting]) -> None:
        self._jobs = jobs
        self.poll_calls = 0
        self.received_searches: list[list[str]] = []

    async def poll(self, searches: Sequence[str]) -> list[PolledJob]:
        self.poll_calls += 1
        self.received_searches.append(list(searches))
        return [PolledJob(job=job, raw_payload=None) for job in self._jobs]
```

В импортах файла `from collections.abc import AsyncIterator` заменить на `from collections.abc import AsyncIterator, Sequence`.

Существующие тесты этого файла поисков в БД не заводят, поэтому после смены поведения `run_once()` они получат пустой список поисков и перестанут вызывать `poll()` вовсе. Чтобы они продолжали проверять то, что проверяли, засев поиска нужно добавить в общий хелпер сборки сервиса. Заменить существующий `_make_service` на:

```python
async def _make_service(
    job_source: FakeJobSource,
    notifier: FakeNotifier,
    session_factory: async_sessionmaker[AsyncSession],
) -> IngestService:
    """Собрать сервис и завести один активный поиск: без поисков в БД
    `run_once()` теперь честно нечего опрашивать."""
    async with unit_of_work(session_factory) as uow:
        if not await uow.searches.list_active(JobSourceName.UPWORK):
            await uow.searches.save(
                SearchQuery(
                    source=JobSourceName.UPWORK, name="default", query="https://default"
                )
            )
    return IngestService(
        job_source,
        session_factory,
        FakeScoringService(),  # type: ignore[arg-type]
        FakeProposalService(),  # type: ignore[arg-type]
        notifier,
        MIN_SCORE,
        DAILY_BUDGET,
    )
```

Хелпер стал асинхронным, поэтому во всех существующих тестах файла строку вида
`service = _make_service(source, notifier, session_factory)` заменить на
`service = await _make_service(source, notifier, session_factory)` (их четыре).

И дописать два новых теста:

```python
async def test_run_once_passes_active_searches_from_db_to_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with unit_of_work(session_factory) as uow:
        await uow.searches.save(
            SearchQuery(source=JobSourceName.UPWORK, name="on", query="https://on")
        )
        await uow.searches.save(
            SearchQuery(
                source=JobSourceName.UPWORK, name="off", query="https://off", is_active=False
            )
        )
        await uow.searches.save(
            SearchQuery(source=JobSourceName.LINKEDIN, name="other", query="https://other")
        )

    source = FakeJobSource([])
    service = await _make_service(source, FakeNotifier(), session_factory)

    await service.run_once()

    # Только активные и только своего источника.
    assert source.received_searches == [["https://on"]]


async def test_run_once_without_searches_does_not_poll_at_all(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Пустая таблица поисков — не повод открывать браузер: опрос пропускается."""
    source = FakeJobSource([_make_job("job-good", title="good python job")])
    service = IngestService(
        source,
        session_factory,
        FakeScoringService(),  # type: ignore[arg-type]
        FakeProposalService(),  # type: ignore[arg-type]
        FakeNotifier(),
        MIN_SCORE,
        DAILY_BUDGET,
    )

    processed = await service.run_once()

    assert processed == 0
    assert source.poll_calls == 0
```

В импорты файла добавить `JobSourceName` и `SearchQuery` к именам из `upwork_assistant.domain.models` (`unit_of_work` там уже импортирован).

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_ingest_service.py -q`
Expected: FAIL — `TypeError: FakeJobSource.poll() missing 1 required positional argument: 'searches'` (`IngestService` пока зовёт `poll()` без аргументов)

- [ ] **Step 3: Изменить порт**

В `src/upwork_assistant/ports/job_source.py` заменить сигнатуру:

```python
class JobSource(Protocol):
    """Источник вакансий для одного цикла опроса."""

    async def poll(self, searches: Sequence[str]) -> list[PolledJob]:
        """Получить вакансии по переданным сохранённым поискам.

        Поиски приходят снаружи, а не читаются адаптером: они лежат в БД, а
        адаптер площадки не должен знать про наше хранилище — ровно так же,
        как пресеты фильтров загружает `IngestService`, а не сам источник.
        """
        ...
```

и добавить импорт `from collections.abc import Sequence`.

- [ ] **Step 4: Изменить адаптер Upwork**

В `src/upwork_assistant/adapters/upwork/source.py`:
- в `poll` заменить сигнатуру на `async def poll(self, searches: Sequence[str]) -> list[PolledJob]:`;
- заменить `for url in self._settings.search_urls:` на `for url in searches:`;
- добавить импорт `from collections.abc import Sequence`;
- в докстринге модуля (строка 4) заменить упоминание `settings.upwork_search_urls` на «переданным сохранённым поискам» — иначе докстринг будет врать про источник адресов.

Остальное тело `poll` не трогать.

- [ ] **Step 5: Изменить IngestService**

В `src/upwork_assistant/services/ingest_service.py`, в `run_once`, заменить начало метода:

```python
    async def run_once(self) -> int:
        """Выполнить один цикл. Возвращает число новых вакансий, дошедших до пайплайна."""
        async with unit_of_work(self._session_factory) as uow:
            searches = await uow.searches.list_active(JobSourceName.UPWORK)
            active_filter_sets = await uow.filter_sets.list_active()

        if not searches:
            logger.warning("Нет активных поисков — цикл пропущен")
            return 0

        jobs = await self._job_source.poll([search.query for search in searches])
        logger.info("Опрос вернул %d вакансий", len(jobs))
```

(существующий блок, который отдельно читал `active_filter_sets`, при этом удаляется — чтение объединено в одну транзакцию выше). Добавить импорт `JobSourceName` из `domain.models`.

- [ ] **Step 6: Убедиться, что тесты проходят**

Run: `pytest tests/test_ingest_service.py -q`
Expected: PASS

- [ ] **Step 7: Прогнать весь набор**

Run: `pytest -q`

На момент написания плана `poll()` вызывается ровно в двух местах — `IngestService.run_once` и `FakeJobSource` в тестах; `tests/test_source_pagination.py` и `tests/test_source_rate_limiting.py` работают с `_poll_search`/`_poll_one` напрямую и смены сигнатуры не замечают. Если что-то всё же упало — проверить `grep -rn "\.poll(" tests/ src/` и привести к новой сигнатуре, ничего больше не меняя.

- [ ] **Step 8: Проверить и закоммитить**

Run: `ruff check src tests && mypy src tests && pytest -q`

```bash
git add src/upwork_assistant/ports/job_source.py src/upwork_assistant/adapters/upwork/source.py src/upwork_assistant/services/ingest_service.py tests/
git commit -m "feat: источник получает поиски из БД, а не из .env"
```

---

### Task 7: Раздел «Поиски» в веб-панели

**Files:**
- Modify: `src/upwork_assistant/api/static/index.html`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `GET/PUT/DELETE /searches` (Task 5)
- Produces: раздел панели; смоук-тест наличия секции в отдаваемом HTML

- [ ] **Step 1: Написать падающий тест**

В `tests/test_dashboard.py` дописать (файл ходит в приложение через `httpx.ASGITransport`, фикстуры `api_client` в проекте нет — повторить приём существующего теста в этом же файле):

```python
async def test_dashboard_contains_searches_section(settings: Settings) -> None:
    """Смоук: раздел «Поиски» реально отдаётся страницей.

    Разметка и JS панели лежат в одном статическом файле без сборки, поэтому
    единственное, что здесь можно проверить автоматически, — что секция не
    потерялась при правке. Поведение раздела проверяется руками (Step 6).
    """
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert 'id="searches-section"' in response.text
    assert 'id="searches-tbody"' in response.text
```

Импорты `httpx`, `create_app`, `Settings` в файле уже есть.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_dashboard.py -q`
Expected: FAIL — `assert 'id="searches-section"' in body`

- [ ] **Step 3: Добавить разметку раздела**

В `src/upwork_assistant/api/static/index.html` вставить новую секцию **между** `<section class="card" id="stats-section">` и `<section class="card" id="filters-section">` — то есть прямо перед строкой `<section class="card" id="filters-section">`:

```html
  <section class="card" id="searches-section">
    <h2>Поиски</h2>
    <p class="hint-text">
      Адреса сохранённых поисков площадки. Настройте фильтры прямо на сайте
      площадки, скопируйте URL из адресной строки и вставьте сюда.
    </p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Источник</th>
            <th>Имя</th>
            <th>Запрос</th>
            <th>Активен</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody id="searches-tbody"></tbody>
      </table>
    </div>
    <div id="searches-list-error" class="error-text" hidden></div>

    <hr style="margin: 20px 0; border: none; border-top: 1px solid var(--color-border);">

    <div id="search-form">
      <div id="search-form-title">Новый поиск</div>
      <div class="filters-form-fields">
        <div class="filters-form-top">
          <label>Источник
            <select id="search-source">
              <option value="upwork">Upwork</option>
              <option value="linkedin">LinkedIn</option>
            </select>
          </label>
          <label>Имя поиска
            <input type="text" id="search-name" placeholder="например, python">
          </label>
          <label class="checkbox-label">
            <input type="checkbox" id="search-is-active" checked>
            Активен
          </label>
        </div>

        <label>Запрос (URL поиска)
          <input type="text" id="search-query" placeholder="https://...">
        </label>

        <div class="form-actions">
          <button id="btn-save-search" class="primary">💾 Сохранить поиск</button>
          <button id="btn-clear-search">Очистить форму / Новый поиск</button>
        </div>
        <div id="search-form-message" hidden></div>
      </div>
    </div>
  </section>
```

Все использованные классы (`card`, `hint-text`, `table-wrap`, `error-text`, `filters-form-fields`, `filters-form-top`, `checkbox-label`, `form-actions`, `primary`) уже определены в `<style>` этой страницы для раздела фильтров — новых CSS-правил не нужно. Разметка намеренно повторяет структуру секции фильтров: одинаковые секции должны выглядеть одинаково.

- [ ] **Step 4: Добавить логику раздела**

Сначала расширить существующее CSS-правило заголовка формы (строка 164) — иначе заголовок новой формы будет без стиля:

```css
  #filter-form-title, #search-form-title { font-weight: 600; margin-bottom: 4px; }
```

Затем в `<script>` той же страницы, **перед** комментарием `// ---------- Вакансии ----------`, добавить новый блок:

```javascript
  // ---------- Поиски ----------

  var SOURCE_LABELS = { upwork: "Upwork", linkedin: "LinkedIn" };
  var editingSearch = null;  // {source, name} правящегося поиска или null

  function showSearchMessage(text, isError) {
    var el = document.getElementById("search-form-message");
    el.hidden = false;
    el.className = isError ? "error-text" : "success-text";
    el.textContent = text;
  }

  function hideSearchMessage() {
    var el = document.getElementById("search-form-message");
    el.hidden = true;
    el.textContent = "";
  }

  function resetSearchForm() {
    editingSearch = null;
    document.getElementById("search-source").disabled = false;
    document.getElementById("search-source").value = "upwork";
    var nameInput = document.getElementById("search-name");
    nameInput.value = "";
    nameInput.readOnly = false;
    document.getElementById("search-query").value = "";
    document.getElementById("search-is-active").checked = true;
    document.getElementById("search-form-title").textContent = "Новый поиск";
    hideSearchMessage();
  }

  function loadSearchIntoForm(search) {
    editingSearch = { source: search.source, name: search.name };
    // Источник и имя вместе адресуют поиск в URL: сменить их — значит создать
    // другой поиск, а не переименовать этот. Поэтому при правке они заперты.
    var sourceSelect = document.getElementById("search-source");
    sourceSelect.value = search.source;
    sourceSelect.disabled = true;
    var nameInput = document.getElementById("search-name");
    nameInput.value = search.name;
    nameInput.readOnly = true;
    document.getElementById("search-query").value = search.query;
    document.getElementById("search-is-active").checked = search.is_active;
    document.getElementById("search-form-title").textContent =
      'Изменение поиска «' + search.name + '»';
    hideSearchMessage();
    document.getElementById("search-form").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function deleteSearch(search) {
    if (!window.confirm('Удалить поиск «' + search.name + '»?')) return;
    fetch("/searches/" + search.source + "/" + encodeURIComponent(search.name), { method: "DELETE" })
      .then(function (resp) {
        if (!resp.ok && resp.status !== 404) throw new Error("HTTP " + resp.status);
        return loadSearches();
      })
      .catch(function () {
        alert("Не удалось удалить поиск. Попробуйте ещё раз.");
      });
  }

  function renderSearchesList(searches) {
    var tbody = document.getElementById("searches-tbody");
    tbody.innerHTML = "";
    if (!searches.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-row">Поисков пока нет</td></tr>';
      return;
    }
    searches.forEach(function (s) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + escapeHtml(SOURCE_LABELS[s.source] || s.source) + "</td>" +
        "<td>" + escapeHtml(s.name) + "</td>" +
        '<td><a href="' + escapeHtml(s.query) + '" target="_blank" rel="noopener">' + escapeHtml(s.query) + "</a></td>" +
        "<td>" + (s.is_active ? "✅" : "❌") + "</td>" +
        '<td><button class="btn-edit-search">Изменить</button> <button class="btn-delete-search danger">Удалить</button></td>';
      tr.querySelector(".btn-edit-search").addEventListener("click", function () { loadSearchIntoForm(s); });
      tr.querySelector(".btn-delete-search").addEventListener("click", function () { deleteSearch(s); });
      tbody.appendChild(tr);
    });
  }

  function loadSearches() {
    var errEl = document.getElementById("searches-list-error");
    errEl.hidden = true;
    return fetch("/searches")
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (searches) {
        renderSearchesList(searches);
      })
      .catch(function () {
        errEl.hidden = false;
        errEl.textContent = "Не удалось загрузить список поисков.";
      });
  }

  function saveSearch() {
    var source = editingSearch ? editingSearch.source : document.getElementById("search-source").value;
    var name = editingSearch ? editingSearch.name : document.getElementById("search-name").value.trim();
    var query = document.getElementById("search-query").value.trim();
    if (!name) {
      showSearchMessage("Введите имя поиска.", true);
      return;
    }
    if (!query) {
      showSearchMessage("Введите URL поиска.", true);
      return;
    }
    var body = {
      query: query,
      is_active: document.getElementById("search-is-active").checked
    };
    var btn = document.getElementById("btn-save-search");
    btn.disabled = true;
    fetch("/searches/" + source + "/" + encodeURIComponent(name), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function () {
        showSearchMessage("Поиск сохранён.", false);
        return loadSearches();
      })
      .then(function () {
        resetSearchForm();
      })
      .catch(function () {
        showSearchMessage("Не удалось сохранить поиск. Проверьте URL и попробуйте снова.", true);
      })
      .then(function () {
        btn.disabled = false;
      });
  }
```

Функция `escapeHtml` в файле уже есть — переиспользовать её, новую не заводить.

- [ ] **Step 5: Подключить раздел к инициализации**

В том же файле, в блоке `document.addEventListener("DOMContentLoaded", ...)` в самом конце скрипта, добавить три строки к уже существующим — рядом с их аналогами для фильтров:

```javascript
    resetSearchForm();          // рядом с существующим resetFilterForm();
    loadSearches();             // рядом с существующим loadFilters();
    document.getElementById("btn-clear-search").addEventListener("click", resetSearchForm);
    document.getElementById("btn-save-search").addEventListener("click", saveSearch);
```

Регистрация именно здесь, а не сразу при разборе скрипта: весь остальной код панели инициализируется по `DOMContentLoaded`, и обработчик, повешенный в обход этого, сломается при любой перестановке `<script>`.

- [ ] **Step 6: Убедиться, что тест проходит**

Run: `pytest tests/test_dashboard.py -q`
Expected: PASS

- [ ] **Step 7: Проверить вручную в браузере**

```bash
source .venv/Scripts/activate && python -m upwork_assistant
```

Открыть `http://127.0.0.1:8077/`, затем проверить руками:
1. Раздел «Поиски» виден, в таблице — перенесённые из `.env` поиски.
2. Создать новый поиск → появляется в таблице.
3. «Изменить» → форма заполняется, имя недоступно для правки, сохранение меняет запрос, а не создаёт дубль.
4. «Удалить» → спрашивает подтверждение и убирает строку.
5. В консоли браузера (F12) нет ошибок.

Остановить процесс после проверки.

- [ ] **Step 8: Закоммитить**

Run: `ruff check src tests && mypy src tests && pytest -q`

```bash
git add src/upwork_assistant/api/static/index.html tests/test_dashboard.py
git commit -m "feat: раздел управления поисками в веб-панели"
```

---

### Task 8: Документация

**Files:**
- Modify: `.env`, `.env.example`
- Modify: `README.md`
- Modify: `USER_GUIDE.md`

**Interfaces:**
- Consumes: всё готовое из задач 1–7
- Produces: актуальная документация; поведение кода не меняется

- [ ] **Step 1: Пометить переменную устаревшей**

В `.env.example` сейчас лежит одна строка комментария:

```ini
# URL сохранённого поиска. Несколько адресов разделяются символом ";"
UPWORK_SEARCH_URLS=https://www.upwork.com/nx/search/jobs/?q=python&sort=recency
```

Заменить её на три:

```ini
# УСТАРЕЛО: поиски теперь живут в БД и правятся через веб-панель (раздел «Поиски»).
# Значение отсюда переносится в БД один раз при первом старте, если таблица пуста.
# Оставлено ради обновления старых установок; кодом больше не читается.
UPWORK_SEARCH_URLS=https://www.upwork.com/nx/search/jobs/?q=python&sort=recency
```

Ровно те же три строки комментария (со своим реальным значением переменной) продублировать в `.env` — файлы обязаны остаться структурно идентичными, включая число строк. **`.env` не перезаписывать целиком** — только заменить строку комментария: в файле лежат настоящие секреты.

Саму переменную и свойство `Settings.search_urls` не удалять: на них держится засев из Task 4.

- [ ] **Step 2: Проверить синхронность файлов**

Run: `diff <(sed -E 's/=.*/=<V>/' .env) <(sed -E 's/=.*/=<V>/' .env.example)`
Expected: пустой вывод

- [ ] **Step 3: Обновить README**

В `README.md`, в разделе `### Upwork`, есть абзац:

> `UPWORK_SEARCH_URLS` — адреса ваших сохранённых поисков; несколько разделяются `;`. Настройте фильтры прямо на сайте Upwork, скопируйте URL из адресной строки.

Заменить его на:

```markdown
Поиски живут в БД и правятся через веб-панель (раздел «Поиски») — настройте фильтры прямо на сайте Upwork, скопируйте URL из адресной строки и вставьте в панель. `UPWORK_SEARCH_URLS` оставлен только для первого запуска: значение оттуда (несколько адресов разделяются `;`) один раз переносится в БД, если таблица поисков пуста, и больше не читается.
```

В разделе `## Статус` дописать в список готового:

```markdown
- **поиски в БД** — адреса сохранённых поисков хранятся в таблице `search_queries` и правятся в веб-панели без перезапуска; `UPWORK_SEARCH_URLS` из `.env` переносится однократно при первом старте;
```

- [ ] **Step 4: Обновить USER_GUIDE**

В `USER_GUIDE.md`, в разделе `## Панель в браузере — с этого стоит начать`, в маркированном списке разделов панели, вставить новый пункт **перед** пунктом `- **Фильтры**` (порядок пунктов должен совпадать с порядком секций на самой странице):

```markdown
- **Поиски** — адреса поисков, по которым ассистент ходит за вакансиями. Настройте
  фильтры прямо на сайте площадки, скопируйте URL из адресной строки и вставьте
  сюда. Галочка «Активен» позволяет временно выключить поиск, не удаляя его.
  Раньше эти адреса лежали в файле настроек на сервере — теперь править их можно
  прямо отсюда, перезапуск не нужен.
```

- [ ] **Step 5: Закоммитить**

```bash
git add .env.example README.md USER_GUIDE.md
git commit -m "docs: поиски настраиваются через панель, UPWORK_SEARCH_URLS устарел"
```

Файл `.env` не коммитить — он в `.gitignore` и содержит реальные секреты.

---

## Проверка плана целиком

После всех задач:

```bash
source .venv/Scripts/activate
ruff check src tests && mypy src tests && pytest -q
```

Затем накатить миграцию на рабочую БД и убедиться, что перенос сработал:

```bash
alembic upgrade head
python -m upwork_assistant   # в логах: "Перенесено поисков из .env в БД: N"
curl -s http://127.0.0.1:8077/searches
```

Ожидаемо: в ответе — поиски из `.env`; в панели они же видны в разделе «Поиски»; следующий цикл опроса использует их из БД.
