"""Market data provider abstract interface."""

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import List, Optional

from backend.pipeline.ingest.models import EODQuote


class EODMarketDataProvider(ABC):
    """Abstract interface for End-of-Day market data providers."""

    @abstractmethod
    def load_quotes(
        self,
        source: Path,
        target_date: Optional[date] = None,
    ) -> List[EODQuote]:
        """Load, parse, and normalize EOD quotes from a source file or provider feed.

        Args:
            source: Path to the local market data report file (e.g. PDF or text).
            target_date: Optional expected trade date for validation and verification.

        Returns:
            List of normalized EODQuote records.
        """
        pass
