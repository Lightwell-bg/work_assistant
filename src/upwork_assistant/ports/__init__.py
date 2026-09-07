"""Порты: границы, через которые сервисы видят внешний мир.

Сервисный слой импортирует только эти `Protocol`-интерфейсы, никогда
`adapters.db` напрямую — конкретные реализации связываются в `container.py`
(инверсия зависимостей). Это позволяет подменять хранилище в тестах без
подмены сервисов.
"""

from __future__ import annotations

from upwork_assistant.ports.repositories import (
    DraftRepository,
    FilterSetRepository,
    JobRepository,
)

__all__ = [
    "DraftRepository",
    "FilterSetRepository",
    "JobRepository",
]
