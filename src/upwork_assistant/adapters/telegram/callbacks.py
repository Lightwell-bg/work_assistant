"""Callback-данные кнопки «Отклик отправлен».

Лимит Telegram на `callback_data` — 64 байта; external_id вакансий Upwork —
короткие числовые строки (~20 цифр), так что запас есть с большим отрывом.
"""

from __future__ import annotations

CALLBACK_PREFIX = "draft:sent:"


def draft_sent_callback_data(job_external_id: str) -> str:
    """Собрать callback_data для кнопки «Отклик отправлен» под конкретную вакансию."""
    return f"{CALLBACK_PREFIX}{job_external_id}"


def parse_draft_sent_callback(data: str) -> str | None:
    """Вернуть external_id вакансии, если это callback «отклик отправлен», иначе None."""
    if not data.startswith(CALLBACK_PREFIX):
        return None
    return data[len(CALLBACK_PREFIX) :]
