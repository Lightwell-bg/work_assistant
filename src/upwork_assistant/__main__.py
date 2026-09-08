"""Точка входа: `python -m upwork_assistant`.

Единственное место, которое реально запускает фоновые воркеры (long-polling
Telegram и планировщик опроса) — конструирование Container в build_container()
намеренно не делает этого само (см. container.py), чтобы тесты, строящие
Container/приложение, не запускали ни бота, ни реальный опрос Upwork.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import uvicorn

from upwork_assistant.app import create_app
from upwork_assistant.config import get_settings
from upwork_assistant.container import build_container
from upwork_assistant.logging import setup_logging
from upwork_assistant.services.polling_settings import load_polling_overrides
from upwork_assistant.services.search_seed import seed_searches_from_env

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_file, settings.log_json)

    async with build_container(settings) as container:
        await seed_searches_from_env(container.session_factory, settings.search_urls)
        await load_polling_overrides(container.session_factory, container.polling_runner.policy)
        container.scheduler.start()
        container.polling_runner.start()
        polling_task = asyncio.create_task(
            container.dispatcher.start_polling(
                container.bot, handle_signals=False, close_bot_session=False
            )
        )

        app = create_app(settings, container=container)
        config = uvicorn.Config(
            app, host=settings.api_host, port=settings.api_port, log_config=None
        )
        server = uvicorn.Server(config)

        try:
            await server.serve()
        finally:
            container.scheduler.shutdown(wait=False)
            polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling_task


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
