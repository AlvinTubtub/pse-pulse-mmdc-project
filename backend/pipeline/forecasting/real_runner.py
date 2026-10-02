"""PSE Pulse Real Model Inference Pipeline CLI Runner.

Executes next-session forecasting across tracked equities using verified
production model artifacts, enforces database lineage, and ensures atomic
persistence inside a single database transaction.
"""

import argparse
import logging
from pathlib import Path
import sys
from typing import Optional, Sequence

from backend.app.config import get_settings
from backend.app.database import SessionLocal
from backend.app.forecasting.real.config import ModelId
from backend.app.services.real_forecast_service import (
    RealForecastService,
    RealForecastingError,
    RealModelsDisabledError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pse_pulse_real_inference_runner")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="PSE Pulse Real Model Production Inference Pipeline Runner"
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path(settings.MODEL_ARTIFACTS_DIR),
        help="Root directory containing versioned model artifact bundles",
    )
    parser.add_argument(
        "--bundle-version",
        type=str,
        default="2026.03.01-v1",
        help="Model artifact bundle version to load (e.g. '2026.03.01-v1')",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated subset of symbols (e.g. 'BPI,SM'). Default: all active companies",
    )
    parser.add_argument(
        "--models",
        type=str,
        default="LAG_REGRESSION,ARIMA",
        help="Comma-separated models to evaluate (e.g. 'LAG_REGRESSION,ARIMA')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full inference and validation without persisting records to database",
    )
    return parser


def run_real_pipeline(
    artifacts_dir: Path,
    bundle_version: str,
    symbols: Optional[Sequence[str]] = None,
    models: Sequence[str] = ("LAG_REGRESSION", "ARIMA"),
    dry_run: bool = False,
) -> int:
    """Run real forecasting pipeline and persist records atomically."""
    db = SessionLocal()
    try:
        service = RealForecastService(db=db)
        summary = service.generate_and_persist_forecasts(
            artifacts_root=artifacts_dir,
            bundle_version=bundle_version,
            target_symbols=symbols,
            model_codes=models,
            dry_run=dry_run,
        )

        logger.info(
            "Real inference pipeline completed successfully. "
            "Run ID: %s, Companies: %d, Generated: %d, Persisted: %d",
            summary.run_id,
            summary.total_companies,
            summary.total_forecasts_generated,
            summary.total_forecasts_persisted,
        )
        for item in summary.items:
            logger.info(
                "[%s] %s: Close=%.4f (Δ=%.4f) for target %s (Origin: %s)",
                item.symbol,
                item.model_code,
                item.predicted_close,
                item.predicted_delta,
                item.target_date,
                item.origin_date,
            )
        return 0

    except RealModelsDisabledError as exc:
        logger.warning("Real forecasting gated off: %s", exc)
        return 2

    except RealForecastingError as exc:
        logger.error("Real forecasting failed: %s", exc)
        return 1

    except Exception as exc:
        logger.error("Unexpected error during real pipeline execution: %s", exc, exc_info=True)
        return 1

    finally:
        db.close()


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else None
    )
    models = [m.strip().upper() for m in args.models.split(",") if m.strip()]

    exit_code = run_real_pipeline(
        artifacts_dir=args.artifacts_dir,
        bundle_version=args.bundle_version,
        symbols=symbols,
        models=models,
        dry_run=args.dry_run,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
