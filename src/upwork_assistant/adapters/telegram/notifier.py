"""`TelegramNotifier` — реализация `ports.notifier.Notifier` поверх aiogram `Bot`."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from upwork_assistant.adapters.telegram.callbacks import draft_sent_callback_data
from upwork_assistant.adapters.telegram.formatting import format_draft_message, format_job_summary
from upwork_assistant.domain.models import Draft, JobPosting, Score


class TelegramNotifier:
    """Шлёт уведомления в один Telegram-чат (личный чат владельца бота)."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def notify_new_draft(self, job: JobPosting, score: Score, draft: Draft) -> None:
        """Сводка вакансии отдельным сообщением, черновик — вторым, с кнопкой отметки."""
        await self._bot.send_message(self._chat_id, format_job_summary(job, score))
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Отклик отправлен",
                        callback_data=draft_sent_callback_data(job.external_id),
                    )
                ]
            ]
        )
        await self._bot.send_message(
            self._chat_id, format_draft_message(draft), reply_markup=keyboard
        )

    async def notify_alert(self, message: str) -> None:
        """Деградация — сообщение с предупреждающим эмодзи."""
        await self._bot.send_message(self._chat_id, f"⚠️ {message}")
