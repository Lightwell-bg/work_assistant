"""Политика опроса: джиттер интервала, лимит загрузок страниц в час, circuit breaker.

Каждая часть закрывает конкретный риск скрейпинга боевого аккаунта:
без джиттера регулярный интервал — узнаваемый бот-паттерн для Cloudflare;
без лимита загрузок в час цикл может создать заметную для площадки нагрузку;
без circuit breaker сбойный цикл (протухшая сессия, дрейф схемы) долбит
биржу вхолостую вместо того, чтобы остановиться и позвать на помощь.
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from upwork_assistant.domain.errors import PermanentError


class CircuitOpenError(PermanentError):
    """Опрос остановлен: слишком много подряд неудачных циклов."""


class PageLoadLimitError(PermanentError):
    """Часовой лимит загрузок страниц исчерпан — цикл нужно пропустить."""


class PollingPolicy:
    """Не хранит ничего специфичного для Upwork — только тайминг и лимиты."""

    def __init__(
        self,
        *,
        interval_minutes: int,
        jitter_pct: int,
        max_page_loads_per_hour: int,
        circuit_breaker_threshold: int = 3,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._interval_minutes = interval_minutes
        self._jitter_pct = jitter_pct
        self._max_page_loads_per_hour = max_page_loads_per_hour
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._clock = clock or (lambda: datetime.now(UTC))
        self._page_load_times: deque[datetime] = deque()
        self._consecutive_failures = 0

    def next_delay_seconds(self) -> float:
        """Интервал опроса со случайным джиттером в пределах ±`jitter_pct`%."""
        base = self._interval_minutes * 60
        spread = base * (self._jitter_pct / 100)
        return base + random.uniform(-spread, spread)

    def can_load_page(self) -> bool:
        """Есть ли ещё запас в часовом лимите загрузок страниц."""
        self._trim_old_loads(self._clock())
        return len(self._page_load_times) < self._max_page_loads_per_hour

    def record_page_load(self) -> None:
        """Учесть загрузку страницы. Не проверяет лимит сама — это `can_load_page()`."""
        self._page_load_times.append(self._clock())

    def record_success(self) -> None:
        """Успешный цикл сбрасывает счётчик подряд идущих неудач."""
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Неудачный цикл. При достижении порога следующий `check_circuit()` бросит исключение."""
        self._consecutive_failures += 1

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def is_circuit_open(self) -> bool:
        return self._consecutive_failures >= self._circuit_breaker_threshold

    def check_circuit(self) -> None:
        """Поднять `CircuitOpenError`, если порог подряд идущих неудач достигнут."""
        if self.is_circuit_open:
            raise CircuitOpenError(
                f"{self._consecutive_failures} подряд неудачных циклов опроса — "
                "остановлено, нужно вмешательство человека"
            )

    def _trim_old_loads(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=1)
        while self._page_load_times and self._page_load_times[0] < cutoff:
            self._page_load_times.popleft()
