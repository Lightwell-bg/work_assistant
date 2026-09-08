"""SQLAlchemy-таблицы: единственное место, где домен превращается в строки БД.

Домен (`domain.models`, `domain.filters`) остаётся Pydantic-моделями без
знания о хранилище — маппинг строка<->домен живёт в `repositories.py`, а не
здесь, чтобы таблицы можно было менять (типы колонок, индексы) не трогая
доменные объекты.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Общий базовый класс для всех таблиц приложения."""


class JobPostingRow(Base):
    """Вакансия. `external_id` — естественный ключ биржи, используется для upsert."""

    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    job_type: Mapped[str] = mapped_column(String, nullable=False)

    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String, nullable=True)

    rate_min: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    rate_max: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    rate_currency: Mapped[str | None] = mapped_column(String, nullable=True)

    duration: Mapped[str | None] = mapped_column(String, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String, nullable=True)
    posted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    client_country: Mapped[str | None] = mapped_column(String, nullable=True)
    client_payment_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    client_total_spend: Mapped[Decimal] = mapped_column(Numeric, default=0, nullable=False)
    client_hire_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_reviews_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    competition: Mapped[str] = mapped_column(String, default="unknown", nullable=False)
    entry_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String, default="new", nullable=False)

    score_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LLMUsageRow(Base):
    """Учёт одного вызова LLM. Без внешнего ключа на `job_postings` — строки
    расхода должны переживать вакансию (и её возможный маппинг в будущем),
    а `job_external_id` уже естественный ключ для join при необходимости."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    job_external_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UpworkJobFactsRow(Base):
    """Сырой payload источника по вакансии — материал для реплея при дрейфе
    схемы. Без внешнего ключа на `job_postings` по той же причине, что и
    у `LLMUsageRow`: строка должна переживать вакансию."""

    __tablename__ = "upwork_job_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_external_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FilterSetRow(Base):
    """Именованный пресет фильтров пользователя."""

    __tablename__ = "filter_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    match_mode: Mapped[str] = mapped_column(String, default="all", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # order_by гарантирует, что порядок правил при чтении совпадает с порядком
    # применения (FilterSet.rules — упорядоченный tuple, а не множество).
    rules: Mapped[list[FilterRuleRow]] = relationship(
        "FilterRuleRow",
        back_populates="filter_set",
        order_by="FilterRuleRow.position",
        cascade="all, delete-orphan",
    )


class FilterRuleRow(Base):
    """Одно условие пресета. `position` хранит порядок внутри пресета явно —
    без него SQL не гарантирует порядок строк при повторном чтении."""

    __tablename__ = "filter_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filter_set_id: Mapped[int] = mapped_column(
        ForeignKey("filter_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[object] = mapped_column(JSON, nullable=False)

    filter_set: Mapped[FilterSetRow] = relationship("FilterSetRow", back_populates="rules")


class DraftRow(Base):
    """Черновик отклика. 1:1 с вакансией — `job_posting_id` уникален."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


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


class AppStateRow(Base):
    """Общая key/value-таблица системных отметок процесса — например, факт
    разового переноса поисков из `.env` (`services/search_seed.py`). Заведена
    как общая, а не отдельной колонкой/таблицей под каждый такой факт, чтобы
    следующая подобная отметка не требовала новой миграции под один флаг."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
