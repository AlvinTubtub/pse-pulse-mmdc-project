"""Unit tests for PSE trading calendar, official holidays, and next session logic."""

from datetime import date
import pytest

from backend.app.forecasting.real.calendar import (
    PSETradingCalendar,
    manila_now,
    next_pse_trading_day,
)
from backend.app.forecasting.real.pse_holidays import PSE_CLOSURES


def test_manila_now_timezone():
    """Verify manila_now returns Asia/Manila (UTC+8) timezone-aware datetime."""
    now = manila_now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 8 * 3600


def test_weekend_closures():
    """Verify Saturday and Sunday are always marked non-trading days."""
    cal = PSETradingCalendar()
    saturday = date(2025, 3, 1)  # Saturday
    sunday = date(2025, 3, 2)    # Sunday
    monday = date(2025, 3, 3)    # Monday

    assert not cal.is_trading_day(saturday)
    assert not cal.is_trading_day(sunday)
    assert cal.is_trading_day(monday)


def test_official_pse_holidays():
    """Verify known Philippine official market holidays are closed."""
    cal = PSETradingCalendar()
    # New Year's Day 2025
    ny_2025 = date(2025, 1, 1)
    assert ny_2025 in PSE_CLOSURES
    assert not cal.is_trading_day(ny_2025)

    # Rizal Day 2024 (Dec 30)
    rizal_day = date(2024, 12, 30)
    assert rizal_day in PSE_CLOSURES
    assert not cal.is_trading_day(rizal_day)


def test_next_pse_trading_day_roll():
    """Verify next_trading_day rolls correctly over weekends and holidays."""
    cal = PSETradingCalendar()
    # Friday to Monday
    friday = date(2025, 2, 28)
    expected_monday = date(2025, 3, 3)
    assert cal.next_trading_day(friday) == expected_monday
    assert next_pse_trading_day(friday) == expected_monday

    # If day before holiday
    aug20_2025 = date(2025, 8, 20)  # Wednesday
    next_day = cal.next_trading_day(aug20_2025)
    if date(2025, 8, 21) in PSE_CLOSURES:
        assert next_day == date(2025, 8, 22)
    else:
        assert next_day == date(2025, 8, 21)
