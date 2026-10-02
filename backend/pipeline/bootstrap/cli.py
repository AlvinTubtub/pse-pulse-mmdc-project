"""CLI tool for official repository historical OHLCV bootstrap."""

import argparse
import logging
from pathlib import Path
import sys

from backend.app.database import SessionLocal
from backend.pipeline.bootstrap.service import HistoricalBootstrapService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pse_pulse_bootstrap")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap the PSE Pulse database from official 15-company historical CSVs"
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        required=True,
        help="Path to directory containing the 15 official raw CSVs (e.g. /tmp/pse-pulse-official-source/backend/data/raw)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and simulate bootstrap without committing database changes",
    )
    parser.add_argument(
        "--allow-conflict-updates",
        action="store_true",
        help="Allow updating differing existing records instead of aborting on conflict",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    db = SessionLocal()
    try:
        service = HistoricalBootstrapService(
            db=db,
            allow_conflict_updates=args.allow_conflict_updates,
        )
        summary = service.bootstrap_official_repo(
            raw_data_dir=args.raw_dir,
            dry_run=args.dry_run,
        )

        logger.info(
            "Bootstrap finished successfully. Status: %s. Symbols: %d, Rows seen: %d, Inserted: %d, Unchanged: %d, Date range: %s to %s",
            summary.status,
            summary.total_symbols,
            summary.total_rows_seen,
            summary.total_rows_inserted,
            summary.total_rows_unchanged,
            summary.date_range_start,
            summary.date_range_end,
        )
        return 0
    except Exception as e:
        logger.error("Bootstrap execution failed: %s", e, exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
