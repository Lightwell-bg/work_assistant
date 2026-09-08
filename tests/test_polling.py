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


def test_interval_minutes_and_jitter_pct_reflect_construction_values() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, interval_minutes=10, jitter_pct=20)

    assert policy.interval_minutes == 10
    assert policy.jitter_pct == 20


def test_set_interval_minutes_changes_next_delay_bounds() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, interval_minutes=10, jitter_pct=0)

    policy.set_interval_minutes(30)

    assert policy.interval_minutes == 30
    assert policy.next_delay_seconds() == pytest.approx(30 * 60)


def test_set_interval_minutes_rejects_less_than_one() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock)

    with pytest.raises(ValueError, match="1"):
        policy.set_interval_minutes(0)

    # Значение не тронуто неудачной попыткой.
    assert policy.interval_minutes == 10


def test_set_jitter_pct_changes_next_delay_spread() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, interval_minutes=10, jitter_pct=0)

    policy.set_jitter_pct(50)

    assert policy.jitter_pct == 50
    base = 10 * 60
    spread = base * 0.5
    samples = [policy.next_delay_seconds() for _ in range(200)]
    assert max(samples) - min(samples) > 0
    assert min(samples) >= base - spread - 1e-6
    assert max(samples) <= base + spread + 1e-6


@pytest.mark.parametrize("value", [-1, 101])
def test_set_jitter_pct_rejects_outside_0_to_100(value: int) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, jitter_pct=20)

    with pytest.raises(ValueError, match=r"0\.\.100"):
        policy.set_jitter_pct(value)

    assert policy.jitter_pct == 20


def test_reset_circuit_closes_it_without_a_successful_cycle() -> None:
    """Человек подтвердил, что причину устранили (например, добавил прокси) —
    в отличие от record_success(), реального удачного цикла для этого не было."""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    policy = make_policy(clock, circuit_breaker_threshold=3)

    policy.record_failure()
    policy.record_failure()
    policy.record_failure()
    assert policy.is_circuit_open is True

    policy.reset_circuit()

    assert policy.is_circuit_open is False
    assert policy.consecutive_failures == 0
    policy.check_circuit()  # не должно бросать
