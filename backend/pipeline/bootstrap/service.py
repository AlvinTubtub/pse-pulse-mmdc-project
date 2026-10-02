"""Historical bootstrap service for PSE Pulse.

Executes all-or-nothing, conflict-safe, idempotent ingestion of official
historical OHLCV CSVs into the daily_prices table with complete, verified provenance.
"""

from datetime import datetime, timezone, date
from decimal import Decimal
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.domain.company_universe import OFFICIAL_15_COMPANIES
from backend.app.models.company import Company
from backend.app.models.price import DailyPrice
from backend.app.models.market_data_import import MarketDataImport
from backend.app.services.company_sync import CompanySyncService
from backend.pipeline.bootstrap.models import (
    HistoricalQuote,
    SymbolBootstrapResult,
    BootstrapSummary,
)
from backend.pipeline.bootstrap.official_repo_csv import (
    OfficialRepoHistoricalProvider,
    HistoricalCsvValidationError,
)
from backend.pipeline.bootstrap.provenance import (
    OfficialSourceVerifier,
    VerifiedBootstrapSource,
    BootstrapSourceVerificationError,
    EXPECTED_OFFICIAL_REPOSITORY,
    EXPECTED_OFFICIAL_COMMIT,
)

logger = logging.getLogger(__name__)

OFFICIAL_SOURCE_REPOSITORY = EXPECTED_OFFICIAL_REPOSITORY
OFFICIAL_SOURCE_COMMIT = EXPECTED_OFFICIAL_COMMIT


class HistoricalPriceConflictError(ValueError):
    """Raised when an incoming historical price conflicts with existing database price."""


class HistoricalBootstrapService:
    """Orchestrates 15-company historical OHLCV bootstrap with verified provenance."""

    def __init__(
        self,
        db: Session,
        allow_conflict_updates: bool = False,
        verifier: Optional[OfficialSourceVerifier] = None,
    ):
        self.db = db
        self.provider = OfficialRepoHistoricalProvider()
        self.allow_conflict_updates = allow_conflict_updates
        self.verifier = verifier or OfficialSourceVerifier()

    def bootstrap_official_repo(
        self,
        raw_data_dir: Optional[Path] = None,
        source_root: Optional[Path] = None,
        verified_source: Optional[VerifiedBootstrapSource] = None,
        dry_run: bool = False,
    ) -> BootstrapSummary:
        """Run all-or-nothing historical bootstrap from official raw CSV directory.

        Guarantees:
        1. Source repository, commit, and SHA-256 hashes must be verified before any DB interaction.
        2. All 15 official CSV files must be present, parsed, and validated in memory.
        3. Synchronizes company and sector metadata.
        4. Identical rows are counted as unchanged (idempotent).
        5. Conflicting rows trigger immediate ABORT and ROLLBACK (no silent overwrite).
        6. Writes immutable MarketDataImport provenance for each symbol derived from verified source.
        7. Entire 15-company operation commits in a SINGLE atomic database transaction.
        8. In dry_run mode, transaction is rolled back; zero mutations persist.
        """
        # Step 0: Fail-closed source provenance verification gate
        if verified_source is None:
            logger.info("Executing fail-closed provenance verification for historical bootstrap...")
            verified_source = self.verifier.verify(
                source_root=source_root,
                raw_data_dir=raw_data_dir,
            )

        active_raw_dir = verified_source.raw_data_dir

        logger.info(
            "Starting 15-company historical bootstrap from %s (source_root=%s, commit=%s, dry_run=%s)...",
            active_raw_dir,
            verified_source.source_root,
            verified_source.commit,
            dry_run,
        )

        # Step 1 & 2: Pre-validate all 15 files in memory before touching DB
        parsed_data: Dict[str, Tuple[List[HistoricalQuote], str, Path]] = {}

        for conf in sorted(OFFICIAL_15_COMPANIES, key=lambda c: c.symbol):
            fpath = active_raw_dir / conf.raw_filename
            if not fpath.exists():
                raise FileNotFoundError(
                    f"Official repository file for {conf.symbol} missing: {fpath}. "
                    "All 15 official CSV files are required for bootstrap."
                )

            quotes, sha256_hash = self.provider.parse_file(fpath, expected_symbol=conf.symbol)
            parsed_data[conf.symbol] = (quotes, sha256_hash, fpath)

        logger.info("Successfully validated all 15 historical CSV files in memory.")

        # Step 3: Transaction Boundary begins
        try:
            # Synchronize companies into database
            company_syncer = CompanySyncService(self.db)
            company_syncer.sync_companies(commit=False)

            active_companies = (
                self.db.query(Company)
                .filter(Company.is_active == True)
                .all()
            )
            company_map = {c.symbol.upper(): c for c in active_companies}

            symbol_results: List[SymbolBootstrapResult] = []
            total_seen = 0
            total_valid = 0
            total_inserted = 0
            total_updated = 0
            total_unchanged = 0
            overall_start_date: Optional[date] = None
            overall_end_date: Optional[date] = None

            for conf in sorted(OFFICIAL_15_COMPANIES, key=lambda c: c.symbol):
                sym = conf.symbol
                quotes, sha256_hash, fpath = parsed_data[sym]
                comp = company_map[sym]

                sym_inserted = 0
                sym_updated = 0
                sym_unchanged = 0

                # Query existing prices for this company
                existing_prices = (
                    self.db.query(DailyPrice)
                    .filter(DailyPrice.company_id == comp.id)
                    .all()
                )
                existing_by_date = {p.trade_date: p for p in existing_prices}

                for q in quotes:
                    existing = existing_by_date.get(q.trade_date)
                    if existing is None:
                        # Insert new
                        if not dry_run:
                            new_price = DailyPrice(
                                company_id=comp.id,
                                trade_date=q.trade_date,
                                open_price=q.open_price,
                                high_price=q.high_price,
                                low_price=q.low_price,
                                close_price=q.close_price,
                                volume=q.volume,
                                value=q.value,
                            )
                            self.db.add(new_price)
                        sym_inserted += 1
                    else:
                        # Compare existing with incoming
                        is_same = (
                            self._dec_equal(existing.open_price, q.open_price)
                            and self._dec_equal(existing.high_price, q.high_price)
                            and self._dec_equal(existing.low_price, q.low_price)
                            and self._dec_equal(existing.close_price, q.close_price)
                            and self._dec_equal(existing.volume, q.volume)
                        )

                        if is_same:
                            sym_unchanged += 1
                        else:
                            # CONFLICT DETECTED
                            if not self.allow_conflict_updates:
                                conflict_msg = (
                                    f"Historical price conflict for {sym} on {q.trade_date}: "
                                    f"DB(O={existing.open_price}, H={existing.high_price}, L={existing.low_price}, C={existing.close_price}, V={existing.volume}) vs "
                                    f"CSV(O={q.open_price}, H={q.high_price}, L={q.low_price}, C={q.close_price}, V={q.volume}). "
                                    "Aborting bootstrap to preserve historical integrity."
                                )
                                logger.error(conflict_msg)
                                raise HistoricalPriceConflictError(conflict_msg)

                            # If conflict updates explicitly allowed
                            if not dry_run:
                                existing.open_price = q.open_price
                                existing.high_price = q.high_price
                                existing.low_price = q.low_price
                                existing.close_price = q.close_price
                                existing.volume = q.volume
                                existing.value = q.value
                            sym_updated += 1

                first_dt = quotes[0].trade_date if quotes else None
                last_dt = quotes[-1].trade_date if quotes else None

                if overall_start_date is None or (first_dt and first_dt < overall_start_date):
                    overall_start_date = first_dt
                if overall_end_date is None or (last_dt and last_dt > overall_end_date):
                    overall_end_date = last_dt

                # Stage provenance audit record for this symbol using verified source
                if not dry_run:
                    import_record = MarketDataImport(
                        source_type="OFFICIAL_REPO_BOOTSTRAP",
                        source_repository=verified_source.repository,
                        source_commit=verified_source.commit,
                        source_path=f"backend/data/raw/{conf.raw_filename}",
                        source_filename=conf.raw_filename,
                        symbol=sym,
                        trade_date=last_dt,
                        first_trade_date=first_dt,
                        last_trade_date=last_dt,
                        sha256=sha256_hash,
                        imported_at=datetime.now(timezone.utc),
                        status="COMPLETED",
                        records_seen=len(quotes),
                        records_valid=len(quotes),
                        records_inserted=sym_inserted,
                        records_updated=sym_updated,
                        records_unchanged=sym_unchanged,
                        records_rejected=0,
                        error_message=None,
                    )
                    self.db.add(import_record)

                total_seen += len(quotes)
                total_valid += len(quotes)
                total_inserted += sym_inserted
                total_updated += sym_updated
                total_unchanged += sym_unchanged

                symbol_results.append(
                    SymbolBootstrapResult(
                        symbol=sym,
                        source_filename=conf.raw_filename,
                        sha256=sha256_hash,
                        first_trade_date=first_dt,
                        last_trade_date=last_dt,
                        rows_seen=len(quotes),
                        rows_valid=len(quotes),
                        rows_inserted=sym_inserted,
                        rows_updated=sym_updated,
                        rows_unchanged=sym_unchanged,
                        status="DRY_RUN" if dry_run else "COMPLETED",
                    )
                )

            # Atomic Commit / Rollback
            if dry_run:
                self.db.rollback()
                status = "DRY_RUN"
                logger.info("Dry-run complete: all changes rolled back; zero mutations committed.")
            else:
                self.db.commit()
                status = "COMPLETED"
                logger.info(
                    "Atomically committed 15-company bootstrap: inserted=%d, updated=%d, unchanged=%d",
                    total_inserted,
                    total_updated,
                    total_unchanged,
                )

            return BootstrapSummary(
                total_symbols=len(symbol_results),
                total_rows_seen=total_seen,
                total_rows_valid=total_valid,
                total_rows_inserted=total_inserted,
                total_rows_updated=total_updated,
                total_rows_unchanged=total_unchanged,
                date_range_start=overall_start_date,
                date_range_end=overall_end_date,
                status=status,
                symbol_results=symbol_results,
            )

        except Exception as e:
            self.db.rollback()
            logger.error("Historical bootstrap transaction failed and was rolled back: %s", e, exc_info=True)
            raise

    @staticmethod
    def _dec_equal(a: Optional[Decimal], b: Optional[Decimal], precision: str = "0.0001") -> bool:
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        return Decimal(str(a)).quantize(Decimal(precision)) == Decimal(str(b)).quantize(Decimal(precision))
