"""Настройка логирования: консоль + файл с ротацией, опционально JSON."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PLAIN_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d %(message)s"

_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


def setup_logging(level: str, log_file: Path, json_format: bool = False) -> None:
    """Сконфигурировать корневой логгер.

    Идемпотентна: повторный вызов заменяет обработчики, а не добавляет вторые.
    Это важно под `uvicorn --reload` и при импорте модуля в тестах.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    if json_format:
        from pythonjsonlogger.json import JsonFormatter

        formatter: logging.Formatter = JsonFormatter(_JSON_FORMAT)
    else:
        formatter = logging.Formatter(_PLAIN_FORMAT)

    console = logging.StreamHandler()
    # Консоль Windows по умолчанию в cp866: без этого кириллица в логах — мусор.
    if hasattr(console.stream, "reconfigure"):
        console.stream.reconfigure(encoding="utf-8", errors="replace")
    console.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)

    # Библиотеки слишком разговорчивы на DEBUG.
    for noisy in ("httpx", "httpcore", "aiogram", "apscheduler", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
