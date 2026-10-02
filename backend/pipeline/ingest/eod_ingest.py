"""EOD Ingestion service for PSE Pulse.

Provides ingestion coordination, file hashing, duplicate detection,
and market session verification.
"""

from datetime import date
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from sqlalchemy.orm import Session

from backend.pipeline.ingest.calendar import TradingCalendar
from backend.pipeline.ingest.models import EODQuote
from backend.pipeline.ingest.providers.pse_dqr_file import PSEDQRFileProvider
from backend.pipeline.persistence.db_saver import DatabaseSaver

logger = logging.getLogger(__name__)


class EODIngestionService:
    """Service handling end-of-day market quote ingestion and file management."""

    def __init__(self, provider: Optional[PSEDQRFileProvider] = None):
        self.provider = provider or PSEDQRFileProvider()

    @staticmethod
    def calculate_file_sha256(file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def check_eod_availability(self, target_date: date) -> bool:
        """Verify whether PSE market was in session for target date.

        Philippine Stock Exchange trading hours close at 15:00 PHT (UTC+8).
        Regular trading sessions occur Monday through Friday.
        """
        is_trading_day = TradingCalendar.is_possible_trading_day(target_date)
        logger.info("Checked market session availability for %s: %s", target_date, is_trading_day)
        return is_trading_day

    def ingest_from_file(
        self,
        source_file: Path,
        target_date: Optional[date] = None,
        force: bool = False,
        db: Optional[Session] = None,
    ) -> Tuple[List[EODQuote], str]:
        """Ingest and normalize quotes from an official PSE market data file.

        Args:
            source_file: Path to official report file (PDF or text).
            target_date: Optional expected trade date for report validation.
            force: If True, bypass SHA-256 duplicate import check.
            db: Optional database session to check import history.

        Returns:
            Tuple of (List[EODQuote], sha256_hash).

        Raises:
            FileNotFoundError: If source_file does not exist.
            ValueError: If duplicate import detected or file is invalid.
        """
        path = Path(source_file)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")

        sha256_hash = self.calculate_file_sha256(path)
        logger.info("Computed SHA-256 for %s: %s", path.name, sha256_hash)

        if db is not None and not force:
            saver = DatabaseSaver(db)
            existing = saver.get_import_by_sha256(sha256_hash)
            if existing:
                raise ValueError(
                    f"File '{path.name}' with SHA-256 {sha256_hash[:12]}... was already successfully imported "
                    f"on {existing.imported_at.isoformat()} (import ID: {existing.id}). "
                    f"Use --force to override."
                )

        quotes = self.provider.load_quotes(path, target_date=target_date)
        return quotes, sha256_hash

    def fetch_eod_quotes(self, target_date: date, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch daily quote records (scaffold fallback for legacy calls)."""
        logger.info("Scaffold fetch_eod_quotes called for %d symbols on %s", len(symbols), target_date)
        return []
