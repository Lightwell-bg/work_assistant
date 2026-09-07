"""Иерархия ошибок приложения.

Деление на временные и постоянные определяет поведение вызывающего кода:
временные имеет смысл повторить, постоянные — нет.
"""

from __future__ import annotations


class AssistantError(Exception):
    """Базовая ошибка приложения."""


class TransientError(AssistantError):
    """Сбой, который может пройти сам: таймаут, 5xx, троттлинг."""


class PermanentError(AssistantError):
    """Сбой, который не исправится повтором: неверный ключ, битая схема ответа."""


class SessionInvalidError(PermanentError):
    """Сессия браузера разлогинена или упёрлась в проверку Cloudflare.

    Требует вмешательства человека: повторного запуска `tools.login`.
    """


class BudgetExceededError(PermanentError):
    """Исчерпан дневной лимит расходов на LLM."""
