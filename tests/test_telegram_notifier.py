"""Тесты `TelegramNotifier` с фейковым `Bot` (без реальной сети)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from aiogram.types import InlineKeyboardMarkup

from upwork_assistant.adapters.telegram.callbacks import draft_sent_callback_data
from upwork_assistant.adapters.telegram.notifier import TelegramNotifier
from upwork_assistant.domain.models import (
    ClientProfile,
    Draft,
    DraftStatus,
    JobPosting,
    JobType,
    RateRange,
    Score,
)


@dataclass
class SentMessage:
    chat_id: int
    text: str
    reply_markup: object | None = None


@dataclass
class FakeBot:
    sent: list[SentMessage] = field(default_factory=list)

    async def send_message(
        self, chat_id: int, text: str, reply_markup: object | None = None
    ) -> None:
        self.sent.append(SentMessage(chat_id=chat_id, text=text, reply_markup=reply_markup))


def _make_job() -> JobPosting:
    return JobPosting(
        external_id="job-1",
        url="https://www.upwork.com/jobs/job-1",
        title="Python backend developer",
        description="desc",
        job_type=JobType.HOURLY,
        rate_range=RateRange(min_rate=Decimal("30"), max_rate=Decimal("60")),
        posted_at=datetime(2026, 9, 1, tzinfo=UTC),
        client=ClientProfile(),
    )


async def test_notify_new_draft_sends_summary_then_draft_with_keyboard() -> None:
    bot = FakeBot()
    notifier = TelegramNotifier(bot, chat_id=42)  # type: ignore[arg-type]
    job = _make_job()
    score = Score(value=8.0, reasoning="Подходит")
    draft = Draft(
        job_external_id=job.external_id,
        content="Здравствуйте!",
        status=DraftStatus.READY,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )

    await notifier.notify_new_draft(job, score, draft)

    assert len(bot.sent) == 2
    summary_message, draft_message = bot.sent

    assert summary_message.chat_id == 42
    assert job.title in summary_message.text
    assert summary_message.reply_markup is None

    assert draft_message.chat_id == 42
    assert draft_message.text == draft.content
    keyboard = draft_message.reply_markup
    assert isinstance(keyboard, InlineKeyboardMarkup)
    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data == draft_sent_callback_data(job.external_id)


async def test_notify_alert_sends_one_message_with_warning_prefix() -> None:
    bot = FakeBot()
    notifier = TelegramNotifier(bot, chat_id=42)  # type: ignore[arg-type]

    await notifier.notify_alert("Скоринг упал")

    assert len(bot.sent) == 1
    assert bot.sent[0].chat_id == 42
    assert bot.sent[0].text == "⚠️ Скоринг упал"
