"""Фабрика приложения FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from upwork_assistant import __version__
from upwork_assistant.api.routes import admin, filters, health, jobs, searches, stats
from upwork_assistant.config import Settings, get_settings
from upwork_assistant.container import Container, build_container

_STATIC_DIR = Path(__file__).parent / "api" / "static"


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Собрать приложение.

    Настройки принимаются аргументом, чтобы тесты могли подставить свои
    без обращения к `.env`. Готовый `container` принимается отдельно —
    им пользуется `__main__.py`, который уже собрал зависимости сам и
    запустил фоновые воркеры (бота, планировщик) вокруг uvicorn; без него
    (как во всех существующих тестах) приложение строит контейнер само.
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if container is not None:
            app.state.container = container
            yield
            app.state.container = None
        else:
            async with build_container(resolved) as built:
                app.state.container = built
                yield
                app.state.container = None

    app = FastAPI(
        title="Upwork AI Assistant",
        description="Мониторинг вакансий Upwork, скоринг и черновики откликов",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(filters.router)
    app.include_router(jobs.router)
    app.include_router(stats.router)
    app.include_router(admin.router)
    app.include_router(searches.router)

    @app.exception_handler(ValidationError)
    async def handle_domain_validation_error(
        _request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Доменные модели (например, `SearchQuery` — находка 3) валидируют
        свои инварианты сами в конструкторе, а не через тело запроса FastAPI.
        Без этого хендлера их `pydantic.ValidationError` дошёл бы до клиента
        как 500, хотя по сути это такая же ошибка данных запроса, как и
        обычная валидация тела — клиент должен увидеть 422, а не 500."""
        errors = jsonable_encoder(exc.errors(include_url=False))
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def dashboard() -> str:
        """Веб-панель: одна самодостаточная HTML-страница без сборки и npm."""
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

    return app
