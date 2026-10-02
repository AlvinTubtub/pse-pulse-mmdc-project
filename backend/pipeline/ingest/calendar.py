"""Trading calendar and market session abstraction."""

from datetime import date


class TradingCalendar:
    """Trading session calendar abstraction.

    Preliminary checks verify standard weekday operations (Monday-Friday),
    while the definitive signal for a session is the successful arrival and
    verification of an official market report.
    """

    @staticmethod
    def is_possible_trading_day(target_date: date) -> bool:
        """Preliminary check: Philippine Stock Exchange sessions occur on weekdays."""
        return target_date.weekday() < 5
