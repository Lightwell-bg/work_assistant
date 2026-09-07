"""Порт уведомлений. Сервисы не знают, что получатель — конкретный Telegram-чат.

Разделение на два метода — не косметика: `notify_new_draft` это обычный
результат работы, а `notify_alert` — деградация, которую нельзя молча
пропустить (сбой скоринга, остановленный circuit breaker и т.п.). В
Kwork-версии сбои ИИ были не видны никому, кроме логов.
"""

from __future__ import annotations

from typing import Protocol

from upwork_assistant.domain.models import Draft, JobPosting, Score


class Notifier(Protocol):
    """Доставка результатов пайплайна и алертов человеку."""

    async def notify_new_draft(self, job: JobPosting, score: Score, draft: Draft) -> None:
        """Новый черновик готов — прошёл порог релевантности."""
        ...

    async def notify_alert(self, message: str) -> None:
        """Деградация, требующая внимания: сбой скоринга/генерации, остановленный опрос."""
        ...
