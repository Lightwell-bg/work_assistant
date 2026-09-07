"""Обработчики апдейтов Telegram-бота.

Логика вынесена в обычную async-функцию `handle_draft_sent`, а не размазана
по декорированному хендлеру внутри `build_router` — так её можно вызвать
напрямую в тестах с фейковым `CallbackQuery`-подобным объектом, без запуска
диспетчерской машинерии aiogram.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from upwork_assistant.adapters.db.uow import unit_of_work
from upwork_assistant.adapters.telegram.callbacks import CALLBACK_PREFIX, parse_draft_sent_callback
from upwork_assistant.domain.models import DraftStatus

logger = logging.getLogger(__name__)


async def handle_draft_sent(
    callback: CallbackQuery, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Пометить черновик отправленным и обновить сообщение под кнопкой."""
    if callback.data is None:
        await callback.answer()
        return

    external_id = parse_draft_sent_callback(callback.data)
    if external_id is None:
        await callback.answer()
        return

    async with unit_of_work(session_factory) as uow:
        await uow.drafts.set_status(external_id, DraftStatus.SENT)

    message = callback.message
    # `message` типизирован aiogram как `Message | InaccessibleMessage | None` —
    # у `InaccessibleMessage` (сообщение старше 48ч/из недоступного чата) нет
    # ни `.text`, ни `.edit_text`. В рантайме сюда почти всегда приходит
    # обычный `Message`; на редкий недоступный случай и на устаревшее
    # сообщение (edit_text бросает) реагируем одинаково — логируем и не
    # роняем хендлер.
    if message is not None:
        try:
            new_text = f"{message.text}\n\n✅ Отправлено"  # type: ignore[union-attr]
            await message.edit_text(new_text, reply_markup=None)  # type: ignore[union-attr]
        except Exception:
            logger.exception("Не удалось обновить сообщение для вакансии %s", external_id)

    await callback.answer("Отмечено как отправленное")


def build_router(session_factory: async_sessionmaker[AsyncSession]) -> Router:
    """Собрать роутер aiogram с единственным хендлером кнопки «Отклик отправлен»."""
    router = Router()

    @router.callback_query(F.data.startswith(CALLBACK_PREFIX))
    async def _on_draft_sent(callback: CallbackQuery) -> None:
        await handle_draft_sent(callback, session_factory)

    return router
