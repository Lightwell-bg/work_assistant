"""Тесты `PollingPolicy`: джиттер, часовой лимит загрузок, circuit breaker.

Чистая логика без I/O — время подаётся через управляемый фейковый `clock`,
который двигается вручную, а не через реальный `datetime.now()`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from upwork_assistant.adapters.upwork.polling import CircuitOpenError, PollingPolicy


class FakeClock:
    """Управляемые часы: `now` двигается вручную вызовом `advance()`."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def advance(self, delta: timedelta) -> None:
        self.now += delta

    def __call__(self) -> datetime:
        return self.now


def make_policy(
    clock: FakeClock,
    *,
    interval_minutes: int = 10,
    jitter_pct: int = 20,
    max_page_loads_per_hour: int = 5,
    circuit_breaker_threshold: int = 3,
) -> PollingPolicy:
    return PollingPolicy(
        interval_minutes=interval_minutes,
        jitter_pct=jitter_pct,
        max_page_loads_per_hour=max_page_loads_per_hour,
        circuit_breaker_threshold=circuit_breaker_threshold,
        clock=clock,
    )


def test_next_delay_seconds_stays_within_jitter_bounds() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, interval_minutes=10, jitter_pct=20)
    base = 10 * 60
    spread = base * 0.20
    expected_min = base - spread
    expected_max = base + spread
    epsilon = 1e-6

    samples = [policy.next_delay_seconds() for _ in range(200)]

    assert min(samples) >= expected_min - epsilon
    assert max(samples) <= expected_max + epsilon
    # Убеждаемся, что разброс реально используется, а не вырожден в константу.
    assert max(samples) - min(samples) > 0


def test_can_load_page_true_initially() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, max_page_loads_per_hour=3)

    assert policy.can_load_page() is True


def test_can_load_page_false_after_hitting_hourly_limit() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, max_page_loads_per_hour=3)

    for _ in range(3):
        assert policy.can_load_page() is True
        policy.record_page_load()

    assert policy.can_load_page() is False


def test_can_load_page_true_again_after_window_slides() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, max_page_loads_per_hour=2)

    policy.record_page_load()
    clock.advance(timedelta(minutes=30))
    policy.record_page_load()
    assert policy.can_load_page() is False

    # Продвигаем время так, чтобы самая старая загрузка вышла из часового окна,
    # а вторая (30 минут спустя) — ещё нет.
    clock.advance(timedelta(minutes=31))
    assert policy.can_load_page() is True


def test_record_success_resets_consecutive_failures() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock)

    policy.record_failure()
    policy.record_failure()
    assert policy.consecutive_failures == 2

    policy.record_success()
    assert policy.consecutive_failures == 0


def test_circuit_closed_below_threshold() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, circuit_breaker_threshold=3)

    policy.record_failure()
    policy.record_failure()

    assert policy.is_circuit_open is False
    policy.check_circuit()  # не должно бросать


def test_circuit_open_at_threshold() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, circuit_breaker_threshold=3)

    policy.record_failure()
    policy.record_failure()
    policy.record_failure()

    assert policy.is_circuit_open is True
    with pytest.raises(CircuitOpenError):
        policy.check_circuit()


def test_circuit_closes_again_after_success() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, circuit_breaker_threshold=3)

    policy.record_failure()
    policy.record_failure()
    policy.record_failure()
    assert policy.is_circuit_open is True

    policy.record_success()

    assert policy.is_circuit_open is False
    policy.check_circuit()  # не должно бросать
