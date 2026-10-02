"""PSE trading-session calendar helpers for real model inference."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from backend.app.forecasting.real.pse_holidays import PSE_CLOSURES

MANILA_TZ = timezone(timedelta(hours=8), name="Asia/Manila")


@dataclass(frozen=True, slots=True)
class PSETradingCalendar:
    """Weekend-aware calendar using reviewed PSE closures by default."""

    holidays: frozenset[date] = field(default_factory=lambda: PSE_CLOSURES)

    @classmethod
    def with_holidays(cls, holidays: Iterable[date]) -> "PSETradingCalendar":
        """Add emergency/caller closures without discarding configured dates."""
        return cls(PSE_CLOSURES | frozenset(holidays))

    def is_trading_day(self, candidate: date) -> bool:
        """Check if candidate date is an active trading session (Mon-Fri, non-closure)."""
        return candidate.weekday() < 5 and candidate not in self.holidays

    def next_trading_day(self, origin: date) -> date:
        """Return the first configured PSE session strictly after origin."""
        candidate = origin + timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate += timedelta(days=1)
        return candidate


def next_pse_trading_day(
    origin: date,
    *,
    holidays: Iterable[date] = (),
) -> date:
    """Convenience wrapper for one-off next-session calculations."""
    return PSETradingCalendar.with_holidays(holidays).next_trading_day(origin)


def manila_now() -> datetime:
    """Return the current timezone-aware timestamp in Asia/Manila."""
    return datetime.now(timezone.utc).astimezone(MANILA_TZ)
