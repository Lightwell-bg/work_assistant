"""Сборка и владение зависимостями приложения.

Контейнер — единственное место, где адаптеры соединяются с сервисами.
Модульных глобалов в проекте нет: всё, что живёт дольше одного запроса,
создаётся здесь и явно передаётся дальше.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.engine import build_engine, build_session_factory
from upwork_assistant.adapters.llm.openrouter import OpenRouterClient
from upwork_assistant.adapters.telegram.bot import build_bot, build_dispatcher
from upwork_assistant.adapters.telegram.notifier import TelegramNotifier
from upwork_assistant.adapters.upwork.polling import PollingPolicy
from upwork_assistant.adapters.upwork.source import UpworkJobSource
from upwork_assistant.config import Settings
from upwork_assistant.ports.job_source import JobSource
from upwork_assistant.ports.notifier import Notifier
from upwork_assistant.scheduler.runner import PollingRunner
from upwork_assistant.services.ingest_service import IngestService
from upwork_assistant.services.proposal_service import ProposalService
from upwork_assistant.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Container:
    """Собранные зависимости приложения."""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    http_client: httpx.AsyncClient
    llm_client: OpenRouterClient
    job_source: JobSource
    notifier: Notifier
    scoring_service: ScoringService
    proposal_service: ProposalService
    ingest_service: IngestService
    bot: Bot
    dispatcher: Dispatcher
    scheduler: AsyncIOScheduler
    polling_runner: PollingRunner


@asynccontextmanager
async def build_container(settings: Settings) -> AsyncIterator[Container]:
    """Создать зависимости и корректно освободить их на выходе.

    ВАЖНО: сборка не делает I/O — не запускает long-polling бота и не
    планирует ни одного цикла опроса. Конструирование `Bot`/`Dispatcher`/
    `AsyncIOScheduler` само по себе сети не касается; фактический запуск
    (`Dispatcher.start_polling`, `scheduler.start()`, `polling_runner.start()`)
    происходит только в `__main__.py` — иначе каждый тест, строящий Container
    через `TestClient`, запускал бы реального бота и реальный браузер Upwork.
    """
    logger.info("Инициализация зависимостей")
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    http_client = httpx.AsyncClient(
        base_url=settings.openrouter_base_url,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"},
        timeout=httpx.Timeout(30.0),
    )
    llm_client = OpenRouterClient(http_client)

    # PollingPolicy — один экземпляр на процесс: лимит загрузок страниц
    # должен считаться из одного места, а не отдельно в источнике вакансий
    # и отдельно в планировщике, иначе лимит окажется фиктивным.
    policy = PollingPolicy(
        interval_minutes=settings.poll_interval_minutes,
        jitter_pct=settings.poll_jitter_pct,
        max_page_loads_per_hour=settings.max_page_loads_per_hour,
    )
    job_source = UpworkJobSource(settings, policy)
    bot = build_bot(settings.telegram_bot_token.get_secret_value())
    dispatcher = build_dispatcher(session_factory)
    notifier = TelegramNotifier(bot, settings.telegram_user_id)
    scoring_service = ScoringService(llm_client, settings.openrouter_scoring_model)
    proposal_service = ProposalService(
        llm_client, settings.openrouter_proposal_model, settings.freelancer_profile_path
    )
    ingest_service = IngestService(
        job_source,
        session_factory,
        scoring_service,
        proposal_service,
        notifier,
        settings.min_score_to_notify,
        settings.openrouter_daily_budget_usd,
    )
    scheduler = AsyncIOScheduler()
    polling_runner = PollingRunner(scheduler, ingest_service, policy, notifier)

    container = Container(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        llm_client=llm_client,
        job_source=job_source,
        notifier=notifier,
        scoring_service=scoring_service,
        proposal_service=proposal_service,
        ingest_service=ingest_service,
        bot=bot,
        dispatcher=dispatcher,
        scheduler=scheduler,
        polling_runner=polling_runner,
    )
    try:
        yield container
    finally:
        logger.info("Освобождение зависимостей")
        await container.engine.dispose()
        await container.http_client.aclose()
        await container.bot.session.close()
        if container.scheduler.running:
            container.scheduler.shutdown(wait=False)
