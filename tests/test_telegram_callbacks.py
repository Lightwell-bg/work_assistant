"""Тесты round-trip callback_data кнопки «Отклик отправлен»."""

from __future__ import annotations

from upwork_assistant.adapters.telegram.callbacks import (
    draft_sent_callback_data,
    parse_draft_sent_callback,
)


def test_round_trip() -> None:
    data = draft_sent_callback_data("12345678901234567")
    assert parse_draft_sent_callback(data) == "12345678901234567"


def test_parse_returns_none_for_unrelated_callback_data() -> None:
    assert parse_draft_sent_callback("some:other:callback") is None
    assert parse_draft_sent_callback("") is None
